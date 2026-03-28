"""Generation-level metrics logging — Section 10 of the spec."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from src.evaluation.fitness import compute_attack_penetration_depth
from src.models import (
    AttackerFitness,
    BankFitness,
    EpisodeOutcome,
    EpisodeResult,
    EpisodeType,
    GenerationStats,
)

logger = logging.getLogger(__name__)


class MetricsLogger:
    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.generations: list[dict] = []

    def log_generation(
        self,
        generation: int,
        bank_fitness_stats: dict,
        attacker_fitness_stats: dict,
        hof_size: int,
        attack_success_rate: float,
        legitimate_approval_rate: float,
        species_count_banks: int,
        species_count_attackers: int,
        complexity_caps: dict,
        pathology_alerts: list[str] | None = None,
    ) -> None:
        entry = {
            "generation": generation,
            "attack_success_rate": attack_success_rate,
            "legitimate_approval_rate": legitimate_approval_rate,
            "hof_size": hof_size,
            "species_count_banks": species_count_banks,
            "species_count_attackers": species_count_attackers,
            "bank_fitness": bank_fitness_stats,
            "attacker_fitness": attacker_fitness_stats,
            "complexity_caps": complexity_caps,
            "pathology_alerts": pathology_alerts or [],
        }
        self.generations.append(entry)

        gen_dir = self.output_dir / f"generation_{generation:03d}"
        gen_dir.mkdir(parents=True, exist_ok=True)
        with open(gen_dir / "metrics.json", "w") as f:
            json.dump(entry, f, indent=2, default=_json_default)

    def get_full_log(self) -> list[dict]:
        return list(self.generations)

    def save_full_log(self) -> None:
        with open(self.output_dir / "evolution_log.json", "w") as f:
            json.dump(self.generations, f, indent=2, default=_json_default)


def summarize_fitness(population: list[Any]) -> dict:
    """Compute summary statistics for a population's fitness vectors."""
    if not population or population[0].fitness is None:
        return {}

    fitness_sample = population[0].fitness
    summary = {}
    for name in fitness_sample.__dataclass_fields__:
        if name == "LOWER_IS_BETTER":
            continue
        values = [getattr(ind.fitness, name) for ind in population if ind.fitness is not None]
        finite_values = [v for v in values if np.isfinite(v)]
        if finite_values:
            summary[name] = {
                "mean": float(np.mean(finite_values)),
                "std": float(np.std(finite_values)),
                "min": float(np.min(finite_values)),
                "max": float(np.max(finite_values)),
            }
        else:
            summary[name] = {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return summary


def compute_generation_stats(
    results: dict[str, list[EpisodeResult]],
    generation: int,
    previous_best_attack_rate: float = 0.0,
    generations_since_improvement: int = 0,
) -> GenerationStats:
    """Compute aggregate stats for a generation from all episode results."""
    all_results = []
    for result_list in results.values():
        all_results.extend(result_list)

    # Deduplicate by episode_id
    seen = set()
    unique = []
    for r in all_results:
        if r.episode_id not in seen:
            seen.add(r.episode_id)
            unique.append(r)

    attack_results = [r for r in unique if r.type in (EpisodeType.ATTACK, EpisodeType.HALL_OF_FAME)]
    legit_results = [r for r in unique if r.type == EpisodeType.LEGITIMATE]

    attack_success = sum(1 for r in attack_results if r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED)
    attack_total = len(attack_results) or 1
    attack_success_rate = attack_success / attack_total

    avg_depth = 0.0
    if attack_results:
        avg_depth = float(np.mean([compute_attack_penetration_depth(r) for r in attack_results]))

    legit_approved = sum(1 for r in legit_results if r.outcome == EpisodeOutcome.LEGITIMATE_APPROVED)
    legit_total = len(legit_results) or 1
    legit_approval_rate = legit_approved / legit_total

    if attack_success_rate > previous_best_attack_rate + 0.01:
        generations_since_improvement = 0
    else:
        generations_since_improvement += 1

    return GenerationStats(
        generation=generation,
        attack_success_rate=attack_success_rate,
        legitimate_approval_rate=legit_approval_rate,
        avg_penetration_depth=avg_depth,
        avg_bank_defense_rate=1.0 - attack_success_rate,
        avg_attacker_success_rate=attack_success_rate,
        generations_since_improvement=generations_since_improvement,
    )


def print_generation_summary(
    generation: int,
    stats: GenerationStats,
    hof_size: int,
    bank_species_count: int,
    attacker_species_count: int,
    alerts: list[str],
) -> None:
    """Print a concise generation summary to stdout."""
    print(f"\n{'='*60}")
    print(f"GENERATION {generation}")
    print(f"{'='*60}")
    print(f"  Attack success rate:       {stats.attack_success_rate:.1%}")
    print(f"  Avg penetration depth:     {stats.avg_penetration_depth:.2f}")
    print(f"  Legitimate approval rate:  {stats.legitimate_approval_rate:.1%}")
    print(f"  Hall of Fame size:         {hof_size}")
    print(f"  Bank species:              {bank_species_count}")
    print(f"  Attacker species:          {attacker_species_count}")
    print(f"  Stagnation counter:        {stats.generations_since_improvement}")
    if alerts:
        print(f"  ALERTS:")
        for alert in alerts:
            print(f"    !! {alert}")
    print(f"{'='*60}")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return str(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
