"""Evaluation arena — Section 3.2 of the spec.

Runs the full evaluation matrix: each bank vs each attacker, HoF attacks,
legitimate transactions, and random perturbations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import textwrap
from typing import Optional

from src.config import EvolutionConfig
from src.genomes.bank_genome import BankGenome
from src.genomes.attacker_genome import AttackerGenome
from src.llm.client import LLMClient
from src.llm.sandbox import AttackerSandbox
from src.models import EpisodeResult, EpisodeType, LegitimateTransaction
from src.evaluation.episode import run_attack_episode, run_legitimate_episode

logger = logging.getLogger(__name__)

VERBOSE = os.environ.get("SIEGE_VERBOSE", "0") == "1"

_OUTCOME_SYMBOLS = {
    "ATTACK_SUCCEEDED": "\033[91m✗ BREACHED\033[0m",
    "ATTACK_BLOCKED": "\033[92m✓ BLOCKED\033[0m",
    "LEGITIMATE_APPROVED": "\033[92m✓ APPROVED\033[0m",
    "LEGITIMATE_REJECTED": "\033[93m✗ REJECTED\033[0m",
}


def _print_episode(result: EpisodeResult, task_type: str) -> None:
    """Print a human-readable episode summary to stdout."""
    outcome_str = _OUTCOME_SYMBOLS.get(result.outcome.value, result.outcome.value)
    opponent = result.attacker_id or result.legitimate_tx_id or "?"

    print(f"\n{'─' * 70}")
    print(f"  {task_type.upper()} │ {result.bank_id} vs {opponent}")
    print(f"  Outcome: {outcome_str}  │  Turns: {result.turn_count}  │  LLM calls: {result.llm_call_count}")
    print(f"{'─' * 70}")

    for msg in result.conversation_log:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        truncated = textwrap.shorten(content, width=300, placeholder="...")
        if role == "user":
            label = "  ATTACKER" if task_type != "legit" else "  REQUEST "
            print(f"  {label} │ {truncated}")
        else:
            print(f"  BANK     │ {truncated}")

    if result.bank_internal_reasoning:
        print(f"  {'─' * 66}")
        print(f"  REASONING│", end="")
        for i, note in enumerate(result.bank_internal_reasoning[:5]):
            prefix = " " if i == 0 else "           │ "
            print(f"{prefix}{textwrap.shorten(note, width=200, placeholder='...')}")
        if len(result.bank_internal_reasoning) > 5:
            print(f"           │ ... and {len(result.bank_internal_reasoning) - 5} more")
    print()


async def evaluate_all(
    banks: list[BankGenome],
    attackers: list[AttackerGenome],
    legitimate_tx: list[LegitimateTransaction],
    hof_attacks: list[AttackerGenome],
    llm_client: LLMClient,
    sandbox: AttackerSandbox,
    config: EvolutionConfig,
) -> dict[str, list[EpisodeResult]]:
    """Run the full evaluation matrix for one generation.

    Returns a dict mapping genome_id -> list of EpisodeResults for that genome.
    Results appear under both the bank_id and attacker_id keys.
    """
    results: dict[str, list[EpisodeResult]] = {b.genome_id: [] for b in banks}
    for a in attackers:
        results.setdefault(a.genome_id, [])
    for a in hof_attacks:
        results.setdefault(a.genome_id, [])

    semaphore = asyncio.Semaphore(config.max_concurrent_llm_calls)

    async def _bounded_attack(bank, attacker, ep_type):
        async with semaphore:
            return await run_attack_episode(
                bank=bank,
                attacker=attacker,
                llm_client=llm_client,
                sandbox=sandbox,
                model=config.llm_model_bank,
                max_turns=config.max_turns_per_episode,
                episode_type=ep_type,
            )

    async def _bounded_legit(bank, tx):
        async with semaphore:
            return await run_legitimate_episode(
                bank=bank,
                tx=tx,
                llm_client=llm_client,
                model=config.llm_model_bank,
            )

    tasks = []

    # Current attacker population vs each bank
    for bank in banks:
        for attacker in attackers:
            tasks.append(("attack", bank, attacker, _bounded_attack(bank, attacker, EpisodeType.ATTACK)))

    # Hall of Fame attacks vs each bank
    hof_sample = hof_attacks
    if len(hof_sample) > config.hof_eval_sample_size:
        hof_sample = random.sample(hof_attacks, config.hof_eval_sample_size)
    for bank in banks:
        for attacker in hof_sample:
            tasks.append(("hof", bank, attacker, _bounded_attack(bank, attacker, EpisodeType.HALL_OF_FAME)))

    # Legitimate transactions vs each bank
    tx_sample = legitimate_tx
    if len(tx_sample) > config.legitimate_tx_count:
        tx_sample = random.sample(legitimate_tx, config.legitimate_tx_count)
    for bank in banks:
        for tx in tx_sample:
            tasks.append(("legit", bank, tx, _bounded_legit(bank, tx)))

    total = len(tasks)
    logger.info("Evaluation arena: %d total episodes to run", total)

    # Gather all coroutines
    coros = [t[3] for t in tasks]
    episode_results = await asyncio.gather(*coros, return_exceptions=True)

    attack_count = 0
    success_count = 0

    for (task_type, bank, counterpart, _), result in zip(tasks, episode_results):
        if isinstance(result, Exception):
            logger.error("Episode failed: %s vs %s — %s", bank.genome_id, getattr(counterpart, 'genome_id', getattr(counterpart, 'id', '?')), result)
            continue
        results[bank.genome_id].append(result)
        if task_type == "attack" or task_type == "hof":
            attacker_id = counterpart.genome_id
            results.setdefault(attacker_id, [])
            results[attacker_id].append(result)
            attack_count += 1
            if result.outcome.value == "ATTACK_SUCCEEDED":
                success_count += 1

        if VERBOSE:
            _print_episode(result, task_type)
        elif result.outcome.value == "ATTACK_SUCCEEDED":
            _print_episode(result, task_type)

    if not VERBOSE and attack_count > 0:
        blocked = attack_count - success_count
        print(f"  Episodes: {attack_count} attacks ({success_count} breached, {blocked} blocked), "
              f"{total - attack_count} legitimate")

    return results
