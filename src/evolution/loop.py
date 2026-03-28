"""Main evolution loop — Section 7 of the spec.

Wires together evaluation, fitness, selection, mutation, safeguards,
and monitoring into the generational loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from pathlib import Path
from typing import Any, Optional

from src.config import EvolutionConfig
from src.evaluation.arena import evaluate_all
from src.evaluation.episode import run_attack_episode
from src.evaluation.fitness import compute_attacker_fitness, compute_bank_fitness
from src.evolution.crossover import crossover_attackers
from src.evolution.initialization import initialize_attacker_population, initialize_bank_population
from src.evolution.mutation import EvolutionContext, mutate_attacker, mutate_bank
from src.evolution.selection import assign_pareto_ranks_and_crowding, pareto_rank, select_parent
from src.genomes.attacker_genome import AttackerGenome
from src.genomes.bank_genome import BankGenome
from src.genomes.legitimate_tx import load_legitimate_transactions
from src.llm.client import LLMClient, get_llm_client
from src.llm.sandbox import AttackerSandbox
from src.models import EpisodeOutcome, EpisodeResult, EpisodeType, GenerationStats
from src.monitoring.diagnostics import check_pathologies, compute_diagnostics
from src.monitoring.metrics import (
    MetricsLogger,
    compute_generation_stats,
    print_generation_summary,
    summarize_fitness,
)
from src.safeguards.curriculum import CurriculumManager
from src.safeguards.hall_of_fame import HallOfFame
from src.safeguards.minimal_criterion import apply_minimal_criterion
from src.safeguards.novelty import (
    apply_fitness_sharing,
    compute_bank_behavior_descriptors_from_results,
    compute_behavior_descriptors_from_results,
    compute_novelty,
    enforce_archetype_minimums,
    update_archetype_centroids,
)
from src.safeguards.speciation import Species, speciate

logger = logging.getLogger(__name__)


async def run_evolution(config: EvolutionConfig, resume_from: Optional[str | Path] = None) -> None:
    """Main evolutionary loop."""
    api_key = os.environ.get(config.llm_api_key_env, "")
    llm_client = get_llm_client(
        max_concurrent=config.max_concurrent_llm_calls,
        api_base=config.llm_api_base,
        api_key=api_key,
    )
    sandbox = AttackerSandbox(timeout=5.0)

    # Initialize or resume
    if resume_from:
        state = load_checkpoint(resume_from)
        bank_population = state["banks"]
        attacker_population = state["attackers"]
        hall_of_fame = state["hall_of_fame"]
        curriculum = state["curriculum"]
        bank_species = state["bank_species"]
        attacker_species = state["attacker_species"]
        start_generation = state["generation"] + 1
        previous_best = state.get("previous_best_attack_rate", 0.0)
        stagnation_counter = state.get("stagnation_counter", 0)
        logger.info("Resumed from generation %d", start_generation - 1)
    else:
        bank_population = initialize_bank_population(config.bank_pop_size)
        attacker_population = initialize_attacker_population(config.attacker_pop_size)
        hall_of_fame = HallOfFame(max_size=config.hof_max_size)
        curriculum = CurriculumManager()
        bank_species: list[Species] = []
        attacker_species: list[Species] = []
        start_generation = 0
        previous_best = 0.0
        stagnation_counter = 0

    legitimate_transactions = load_legitimate_transactions()
    metrics_logger = MetricsLogger(config.output_dir)

    # ─── BOOTSTRAPPING PHASE ───
    if start_generation == 0 and config.bootstrap_generations > 0:
        attacker_population = await _run_bootstrap(
            config=config,
            bank_population=bank_population,
            attacker_population=attacker_population,
            hall_of_fame=hall_of_fame,
            legitimate_transactions=legitimate_transactions,
            llm_client=llm_client,
            sandbox=sandbox,
        )

    for generation in range(start_generation, config.max_generations):
        # --- Phase 1: Evaluation ---
        results = await evaluate_all(
            banks=bank_population,
            attackers=attacker_population,
            legitimate_tx=legitimate_transactions,
            hof_attacks=hall_of_fame.get_attack_test_set(),
            llm_client=llm_client,
            sandbox=sandbox,
            config=config,
        )

        # --- Phase 2: Compute Fitness ---
        for bank in bank_population:
            bank_results = results.get(bank.genome_id, [])
            bank.fitness = compute_bank_fitness(bank.genome_id, bank_results)
            compute_bank_behavior_descriptors_from_results(bank, bank_results)

        for attacker in attacker_population:
            atk_results = results.get(attacker.genome_id, [])
            compute_behavior_descriptors_from_results(attacker, atk_results)
            novelty = compute_novelty(attacker, attacker_population, hall_of_fame.attack_archive)
            attacker.fitness = compute_attacker_fitness(attacker.genome_id, atk_results, novelty_score=novelty)

        # --- Phase 3: Minimal Criterion ---
        viable_banks, viable_attackers = apply_minimal_criterion(
            bank_population,
            attacker_population,
            results,
            mc_bank_min_legit_rate=config.mc_bank_min_legit_rate,
            relaxation_threshold=config.mc_relaxation_threshold,
        )

        # --- Phase 4: Update Archives ---
        hall_of_fame.update_attack_archive(attacker_population, results)
        hall_of_fame.update_bank_archive(bank_population, results)

        # --- Phase 4.5: Fitness Sharing (niche-based) ---
        update_archetype_centroids(viable_attackers)
        apply_fitness_sharing(viable_attackers, sigma_share=config.fitness_sharing_sigma)
        apply_fitness_sharing(viable_banks, sigma_share=config.fitness_sharing_sigma)

        # Pareto ranking uses shared_fitness for both populations
        _swap_to_shared_fitness(viable_attackers)
        _swap_to_shared_fitness(viable_banks)

        # --- Phase 5: Pareto Ranking ---
        bank_fronts = pareto_rank(viable_banks)
        attacker_fronts = pareto_rank(viable_attackers)
        assign_pareto_ranks_and_crowding(bank_fronts)
        assign_pareto_ranks_and_crowding(attacker_fronts)

        _restore_raw_fitness(viable_attackers)
        _restore_raw_fitness(viable_banks)

        # --- Phase 6: Speciation ---
        attacker_species = speciate(viable_attackers, attacker_species, config.speciation_threshold)
        bank_species = speciate(viable_banks, bank_species, config.speciation_threshold)

        # --- Phase 7: Reproduction ---
        new_banks: list[BankGenome] = []
        new_attackers: list[AttackerGenome] = []

        # Elitism
        if bank_fronts:
            bank_elites = bank_fronts[0][:config.elite_count]
            new_banks.extend(bank_elites)
        if attacker_fronts:
            attacker_elites = attacker_fronts[0][:config.elite_count]
            new_attackers.extend(attacker_elites)

        # Fill banks via mutation
        bank_mutation_tasks = []
        while len(new_banks) + len(bank_mutation_tasks) < config.bank_pop_size:
            parent = select_parent(viable_banks, config.tournament_size)
            ctx = EvolutionContext(
                generation=generation,
                current_defense_rate=parent.fitness.current_defense_rate if parent.fitness else 0.0,
                historical_defense_rate=parent.fitness.historical_defense_rate if parent.fitness else 0.0,
                legitimate_approval_rate=parent.fitness.legitimate_approval_rate if parent.fitness else 0.0,
                successful_attacks=_get_successful_attacks_against(parent, results),
            )
            bank_mutation_tasks.append(mutate_bank(parent, ctx, llm_client, config.llm_model_mutation))

        # Fill attackers via mutation + crossover
        attacker_mutation_tasks = []
        while len(new_attackers) + len(attacker_mutation_tasks) < config.attacker_pop_size:
            if random.random() < config.crossover_rate and len(viable_attackers) >= 2:
                parent_a = select_parent(viable_attackers, config.tournament_size)
                parent_b = select_parent(viable_attackers, config.tournament_size)
                attacker_mutation_tasks.append(
                    crossover_attackers(parent_a, parent_b, llm_client, config.llm_model_mutation, generation, sandbox)
                )
            else:
                parent = select_parent(viable_attackers, config.tournament_size)
                ctx = EvolutionContext(
                    generation=generation,
                    success_rate=parent.fitness.success_rate if parent.fitness else 0.0,
                    blocking_defenses=_get_blocking_defenses(parent, results),
                    other_successful=_get_other_successful_strategies(viable_attackers),
                )
                attacker_mutation_tasks.append(
                    mutate_attacker(parent, ctx, llm_client, config.llm_model_mutation, sandbox)
                )

        # Run all mutations concurrently
        if bank_mutation_tasks:
            bank_children = await asyncio.gather(*bank_mutation_tasks, return_exceptions=True)
            for child in bank_children:
                if isinstance(child, Exception):
                    logger.error("Bank mutation failed: %s", child)
                else:
                    new_banks.append(child)

        if attacker_mutation_tasks:
            attacker_children = await asyncio.gather(*attacker_mutation_tasks, return_exceptions=True)
            for child in attacker_children:
                if isinstance(child, Exception):
                    logger.error("Attacker mutation failed: %s", child)
                else:
                    new_attackers.append(child)

        # Trim to population size
        new_banks = new_banks[:config.bank_pop_size]
        new_attackers = new_attackers[:config.attacker_pop_size]

        # --- Archetype Protection ---
        new_attackers = enforce_archetype_minimums(
            new_attackers,
            min_per_archetype=config.min_per_archetype,
            generation=generation,
            protection_generations=config.archetype_protection_generations,
        )

        # Record lineage for new genomes
        _record_lineage(generation + 1, new_banks, new_attackers, bank_population, attacker_population, config.output_dir)

        # --- Phase 8: Update Curriculum ---
        gen_stats = compute_generation_stats(
            results, generation, previous_best, stagnation_counter
        )
        gen_stats.hof_size = len(hall_of_fame.attack_archive)
        gen_stats.bank_species_count = len(bank_species)
        gen_stats.attacker_species_count = len(attacker_species)
        curriculum.update_complexity(gen_stats)

        stagnation_counter = gen_stats.generations_since_improvement
        previous_best = max(previous_best, gen_stats.attack_success_rate)

        # --- Phase 9: Diagnostics & Monitoring ---
        diag = compute_diagnostics(
            results, bank_population, attacker_population,
            bank_species_count=len(bank_species),
            attacker_species_count=len(attacker_species),
        )
        alerts = check_pathologies(diag)

        metrics_logger.log_generation(
            generation=generation,
            bank_fitness_stats=summarize_fitness(bank_population),
            attacker_fitness_stats=summarize_fitness(attacker_population),
            hof_size=len(hall_of_fame.attack_archive),
            attack_success_rate=gen_stats.attack_success_rate,
            legitimate_approval_rate=gen_stats.legitimate_approval_rate,
            species_count_banks=len(bank_species),
            species_count_attackers=len(attacker_species),
            complexity_caps=curriculum.get_current_caps(),
            pathology_alerts=alerts,
        )

        print_generation_summary(
            generation, gen_stats,
            hof_size=len(hall_of_fame.attack_archive),
            bank_species_count=len(bank_species),
            attacker_species_count=len(attacker_species),
            alerts=alerts,
        )

        # --- Phase 10: Stagnation Detection ---
        if gen_stats.is_stagnant(window=config.stagnation_window):
            logger.warning("STAGNATION DETECTED at generation %d — injecting random immigrants", generation)
            print("!! STAGNATION DETECTED — injecting random immigrants")
            try:
                immigrant_banks = initialize_bank_population(config.random_immigrant_count_banks)
                immigrant_attackers = initialize_attacker_population(config.random_immigrant_count_attackers)
                new_banks[-config.random_immigrant_count_banks:] = immigrant_banks
                new_attackers[-config.random_immigrant_count_attackers:] = immigrant_attackers
            except Exception as e:
                logger.error("Failed to inject immigrants: %s", e)

        # --- Phase 11: Replace populations ---
        bank_population = new_banks
        attacker_population = new_attackers

        # --- Checkpoint ---
        if (generation + 1) % config.save_every_n_generations == 0:
            save_checkpoint(
                generation=generation,
                banks=bank_population,
                attackers=attacker_population,
                hall_of_fame=hall_of_fame,
                curriculum=curriculum,
                bank_species=bank_species,
                attacker_species=attacker_species,
                previous_best_attack_rate=previous_best,
                stagnation_counter=stagnation_counter,
                output_dir=config.output_dir,
            )

        # Save genomes and episodes per generation
        if config.save_full_genomes:
            _save_generation_genomes(generation, bank_population, attacker_population, config.output_dir)
            _save_generation_episodes(generation, results, config.output_dir)

    # --- Final Output ---
    metrics_logger.save_full_log()
    save_checkpoint(
        generation=config.max_generations - 1,
        banks=bank_population,
        attackers=attacker_population,
        hall_of_fame=hall_of_fame,
        curriculum=curriculum,
        bank_species=bank_species,
        attacker_species=attacker_species,
        previous_best_attack_rate=previous_best,
        stagnation_counter=stagnation_counter,
        output_dir=config.output_dir,
    )
    _save_final_report(bank_population, hall_of_fame, metrics_logger, config.output_dir)
    print("\nEvolution complete. Results saved to", config.output_dir)


def _swap_to_shared_fitness(population: list) -> None:
    """Temporarily replace fitness with shared_fitness for Pareto ranking."""
    for ind in population:
        if hasattr(ind, "shared_fitness") and ind.shared_fitness is not None:
            ind._raw_fitness = ind.fitness
            ind.fitness = ind.shared_fitness


def _restore_raw_fitness(population: list) -> None:
    """Restore raw fitness after Pareto ranking."""
    for ind in population:
        if hasattr(ind, "_raw_fitness"):
            ind.fitness = ind._raw_fitness
            del ind._raw_fitness


def _get_successful_attacks_against(bank: BankGenome, results: dict[str, list[EpisodeResult]]) -> list[str]:
    """Get summaries of attacks that succeeded against this bank."""
    bank_results = results.get(bank.genome_id, [])
    summaries = []
    for r in bank_results:
        if r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED and r.attacker_id:
            first_msg = ""
            if r.conversation_log:
                first_msg = r.conversation_log[0].get("content", "")[:200]
            summaries.append(f"Attacker {r.attacker_id}: {first_msg}")
    return summaries[:5]


def _get_blocking_defenses(attacker: AttackerGenome, results: dict[str, list[EpisodeResult]]) -> list[str]:
    """Get summaries of bank defenses that blocked this attacker."""
    atk_results = results.get(attacker.genome_id, [])
    summaries = []
    for r in atk_results:
        if r.outcome == EpisodeOutcome.ATTACK_BLOCKED:
            summaries.append(f"Bank {r.bank_id} blocked attack")
    return summaries[:5]


def _get_other_successful_strategies(attackers: list[AttackerGenome]) -> list[str]:
    """Get code snippets from other successful attackers."""
    successful = [a for a in attackers if a.fitness and a.fitness.success_rate > 0]
    successful.sort(key=lambda a: a.fitness.success_rate, reverse=True)
    return [a.code[:300] for a in successful[:3]]


async def _validate_seeds(
    banks: list[BankGenome],
    attackers: list[AttackerGenome],
    llm_client: LLMClient,
    sandbox: AttackerSandbox,
    config: EvolutionConfig,
) -> None:
    """Validate that at least 30% of seed attackers break the weakest banks.

    Per spec Section 2.4: run each seed attacker against the first two
    banks (deliberately weakest). If fewer than 30% succeed against
    either, log a warning.
    """
    weak_banks = banks[:2]
    semaphore = asyncio.Semaphore(config.max_concurrent_llm_calls)

    async def _run(bank, attacker):
        async with semaphore:
            return await run_attack_episode(
                bank=bank, attacker=attacker,
                llm_client=llm_client, sandbox=sandbox,
                model=config.llm_model_bank,
                max_turns=config.max_turns_per_episode,
            )

    tasks = []
    for bank in weak_banks:
        for attacker in attackers:
            tasks.append((bank.genome_id, attacker.genome_id, _run(bank, attacker)))

    results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)

    succeeded_attackers: set[str] = set()
    for (bank_id, atk_id, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.warning("Seed validation episode failed: %s vs %s — %s", bank_id, atk_id, result)
            continue
        if result.outcome == EpisodeOutcome.ATTACK_SUCCEEDED:
            succeeded_attackers.add(atk_id)

    ratio = len(succeeded_attackers) / max(len(attackers), 1)
    print(f"\n  Seed validation: {len(succeeded_attackers)}/{len(attackers)} "
          f"attackers ({ratio:.0%}) broke at least one weak bank")

    if ratio < 0.30:
        logger.warning(
            "Seed validation FAILED: only %.0f%% of attackers broke a weak bank "
            "(need >=30%%). Seed banks may be too strong or attackers too weak.",
            ratio * 100,
        )
        print("  !! WARNING: fewer than 30% of seed attackers broke the weakest bank.")
        print("     Consider weakening seed_bank_00/seed_bank_01 or strengthening seed attackers.")
    else:
        print("  ✓ Seed validation passed")


async def _run_bootstrap(
    config: EvolutionConfig,
    bank_population: list[BankGenome],
    attacker_population: list[AttackerGenome],
    hall_of_fame: HallOfFame,
    legitimate_transactions: list,
    llm_client: LLMClient,
    sandbox: AttackerSandbox,
) -> list[AttackerGenome]:
    """Bootstrap phase: evolve attackers against frozen weak banks.

    Returns the evolved attacker population.
    """
    print("=" * 60)
    print("BOOTSTRAPPING PHASE: Evolving attackers against frozen weak bank")
    print(f"Running up to {config.bootstrap_generations} generations, banks are FROZEN")
    print("=" * 60)

    # Validate seeds first
    await _validate_seeds(bank_population, attacker_population, llm_client, sandbox, config)

    frozen_banks = bank_population[:2]

    for boot_gen in range(config.bootstrap_generations):
        print(f"\n  Bootstrap generation {boot_gen}")

        results = await evaluate_all(
            banks=frozen_banks,
            attackers=attacker_population,
            legitimate_tx=legitimate_transactions,
            hof_attacks=[],
            llm_client=llm_client,
            sandbox=sandbox,
            config=config,
        )

        for attacker in attacker_population:
            atk_results = results.get(attacker.genome_id, [])
            compute_behavior_descriptors_from_results(attacker, atk_results)
            novelty = compute_novelty(attacker, attacker_population, [])
            attacker.fitness = compute_attacker_fitness(
                attacker.genome_id, atk_results, novelty_score=novelty
            )

        attack_episodes = [
            r for r_list in results.values() for r in r_list
            if r.type in (EpisodeType.ATTACK,)
        ]
        seen_ep_ids: set[str] = set()
        unique_attacks = []
        for ep in attack_episodes:
            if ep.episode_id not in seen_ep_ids:
                seen_ep_ids.add(ep.episode_id)
                unique_attacks.append(ep)

        total_atk = len(unique_attacks) or 1
        successes = sum(1 for ep in unique_attacks if ep.outcome == EpisodeOutcome.ATTACK_SUCCEEDED)
        boot_success_rate = successes / total_atk

        avg_depth = 0.0
        if unique_attacks:
            from src.evaluation.fitness import compute_attack_penetration_depth
            avg_depth = sum(compute_attack_penetration_depth(ep) for ep in unique_attacks) / len(unique_attacks)

        print(f"  Attack success rate: {boot_success_rate:.1%}  |  Avg penetration depth: {avg_depth:.2f}")

        if boot_success_rate >= config.bootstrap_target_success_rate:
            print(f"  ✓ Bootstrap target reached ({boot_success_rate:.1%} >= "
                  f"{config.bootstrap_target_success_rate:.0%})")
            break

        # Evolve attackers only (banks stay frozen)
        attacker_fronts = pareto_rank(attacker_population)
        assign_pareto_ranks_and_crowding(attacker_fronts)

        new_attackers: list[AttackerGenome] = []
        if attacker_fronts:
            new_attackers.extend(attacker_fronts[0][:config.elite_count])

        mutation_tasks = []
        while len(new_attackers) + len(mutation_tasks) < config.attacker_pop_size:
            parent = select_parent(attacker_population, config.tournament_size)
            ctx = EvolutionContext(
                generation=boot_gen,
                success_rate=parent.fitness.success_rate if parent.fitness else 0.0,
                blocking_defenses=_get_blocking_defenses(parent, results),
                other_successful=_get_other_successful_strategies(attacker_population),
            )
            mutation_tasks.append(
                mutate_attacker(parent, ctx, llm_client, config.llm_model_mutation, sandbox)
            )

        if mutation_tasks:
            children = await asyncio.gather(*mutation_tasks, return_exceptions=True)
            for child in children:
                if isinstance(child, Exception):
                    logger.error("Bootstrap mutation failed: %s", child)
                else:
                    new_attackers.append(child)

        attacker_population = new_attackers[:config.attacker_pop_size]

    # Seed the Hall of Fame with any successful bootstrap attacks
    final_results = await evaluate_all(
        banks=frozen_banks,
        attackers=attacker_population,
        legitimate_tx=[],
        hof_attacks=[],
        llm_client=llm_client,
        sandbox=sandbox,
        config=config,
    )
    hall_of_fame.update_attack_archive(attacker_population, final_results)

    print(f"\nBootstrapping complete. HoF seeded with {len(hall_of_fame.attack_archive)} attacks.")
    print(f"Starting coevolution with both populations active.\n")

    return attacker_population


def save_checkpoint(
    generation: int,
    banks: list[BankGenome],
    attackers: list[AttackerGenome],
    hall_of_fame: HallOfFame,
    curriculum: CurriculumManager,
    bank_species: list[Species],
    attacker_species: list[Species],
    previous_best_attack_rate: float,
    stagnation_counter: int,
    output_dir: str | Path,
) -> None:
    """Save full evolutionary state for resuming."""
    output_dir = Path(output_dir)
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "generation": generation,
        "banks": [b.to_dict() for b in banks],
        "attackers": [a.to_dict() for a in attackers],
        "hall_of_fame": hall_of_fame.to_dict(),
        "curriculum": curriculum.to_dict(),
        "previous_best_attack_rate": previous_best_attack_rate,
        "stagnation_counter": stagnation_counter,
    }

    path = checkpoint_dir / f"checkpoint_gen_{generation:03d}.json"
    with open(path, "w") as f:
        json.dump(state, f, indent=2)

    # Also save as "latest"
    latest_path = checkpoint_dir / "latest.json"
    with open(latest_path, "w") as f:
        json.dump(state, f, indent=2)

    logger.info("Checkpoint saved: %s", path)


def load_checkpoint(path: str | Path) -> dict:
    """Load evolutionary state from checkpoint."""
    path = Path(path)
    if path.is_dir():
        path = path / "checkpoints" / "latest.json"

    with open(path) as f:
        state = json.load(f)

    return {
        "generation": state["generation"],
        "banks": [BankGenome.from_dict(b) for b in state["banks"]],
        "attackers": [AttackerGenome.from_dict(a) for a in state["attackers"]],
        "hall_of_fame": HallOfFame.from_dict(state["hall_of_fame"]),
        "curriculum": CurriculumManager.from_dict(state["curriculum"]),
        "bank_species": [],
        "attacker_species": [],
        "previous_best_attack_rate": state.get("previous_best_attack_rate", 0.0),
        "stagnation_counter": state.get("stagnation_counter", 0),
    }


def _save_generation_genomes(
    generation: int,
    banks: list[BankGenome],
    attackers: list[AttackerGenome],
    output_dir: str | Path,
) -> None:
    gen_dir = Path(output_dir) / f"generation_{generation:03d}"
    banks_dir = gen_dir / "banks"
    attackers_dir = gen_dir / "attackers"
    banks_dir.mkdir(parents=True, exist_ok=True)
    attackers_dir.mkdir(parents=True, exist_ok=True)

    for bank in banks:
        with open(banks_dir / f"{bank.genome_id}.json", "w") as f:
            json.dump(bank.to_dict(), f, indent=2)

    for attacker in attackers:
        with open(attackers_dir / f"{attacker.genome_id}.json", "w") as f:
            json.dump(attacker.to_dict(), f, indent=2)


def _record_lineage(
    generation: int,
    new_banks: list[BankGenome],
    new_attackers: list[AttackerGenome],
    old_banks: list[BankGenome],
    old_attackers: list[AttackerGenome],
    output_dir: str | Path,
) -> None:
    """Append lineage entries to lineage.jsonl for the Observatory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    lineage_path = output_dir / "lineage.jsonl"

    old_bank_map = {b.genome_id: b for b in old_banks}
    old_atk_map = {a.genome_id: a for a in old_attackers}

    entries = []
    for bank in new_banks:
        if not bank.lineage:
            continue
        parent_id = bank.lineage[-1]
        parent = old_bank_map.get(parent_id)
        entries.append({
            "child_id": bank.genome_id,
            "parent_ids": [parent_id],
            "generation": generation,
            "genome_type": "bank",
            "operation": "mutation",
            "fitness_before": parent.fitness.to_dict() if parent and parent.fitness else {},
            "fitness_after": bank.fitness.to_dict() if bank.fitness else {},
        })

    for atk in new_attackers:
        if not atk.lineage:
            continue
        parent_ids = [atk.lineage[-1]] if len(atk.lineage) == 1 or atk.lineage[-1] == atk.lineage[-2] else atk.lineage[-2:]
        parent = old_atk_map.get(parent_ids[0])
        op = "crossover" if len(parent_ids) > 1 else "mutation"
        entries.append({
            "child_id": atk.genome_id,
            "parent_ids": parent_ids,
            "generation": generation,
            "genome_type": "attacker",
            "operation": op,
            "fitness_before": parent.fitness.to_dict() if parent and parent.fitness else {},
            "fitness_after": atk.fitness.to_dict() if atk.fitness else {},
        })

    with open(lineage_path, "a") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _save_generation_episodes(
    generation: int,
    results: dict[str, list],
    output_dir: str | Path,
) -> None:
    """Save all episode results for a generation, including full conversation logs."""
    gen_dir = Path(output_dir) / f"generation_{generation:03d}"
    episodes_dir = gen_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    seen_ids: set[str] = set()
    for episode_list in results.values():
        for ep in episode_list:
            if ep.episode_id in seen_ids:
                continue
            seen_ids.add(ep.episode_id)
            ep_data = ep.to_dict()
            ep_data["generation"] = generation
            with open(episodes_dir / f"{ep.episode_id}.json", "w") as f:
                json.dump(ep_data, f, indent=2)


def _save_final_report(
    banks: list[BankGenome],
    hall_of_fame: HallOfFame,
    metrics_logger: MetricsLogger,
    output_dir: str | Path,
) -> None:
    output_dir = Path(output_dir)

    # Save HoF
    hof_dir = output_dir / "hall_of_fame"
    hof_attacks_dir = hof_dir / "attacks"
    hof_banks_dir = hof_dir / "banks"
    hof_attacks_dir.mkdir(parents=True, exist_ok=True)
    hof_banks_dir.mkdir(parents=True, exist_ok=True)

    for atk in hall_of_fame.attack_archive:
        with open(hof_attacks_dir / f"{atk.genome_id}.json", "w") as f:
            json.dump(atk.to_dict(), f, indent=2)

    for bank in hall_of_fame.bank_archive:
        with open(hof_banks_dir / f"{bank.genome_id}.json", "w") as f:
            json.dump(bank.to_dict(), f, indent=2)

    # Save final report
    best_banks = sorted(
        [b for b in banks if b.fitness],
        key=lambda b: b.fitness.current_defense_rate,
        reverse=True,
    )
    report = {
        "best_bank": best_banks[0].to_dict() if best_banks else None,
        "hof_attack_count": len(hall_of_fame.attack_archive),
        "hof_bank_count": len(hall_of_fame.bank_archive),
        "evolution_summary": metrics_logger.get_full_log()[-1] if metrics_logger.get_full_log() else {},
    }
    with open(output_dir / "final_report.json", "w") as f:
        json.dump(report, f, indent=2)
