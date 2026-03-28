"""Minimal Criterion filter — Section 6.3 of the spec.

Forces both populations to remain at the productive frontier.
"""

from __future__ import annotations

import logging

from src.genomes.attacker_genome import AttackerGenome
from src.genomes.bank_genome import BankGenome
from src.models import EpisodeOutcome, EpisodeResult, EpisodeType

logger = logging.getLogger(__name__)


def apply_minimal_criterion(
    banks: list[BankGenome],
    attackers: list[AttackerGenome],
    results: dict[str, list[EpisodeResult]],
    mc_bank_min_legit_rate: float = 0.5,
    relaxation_threshold: float = 0.2,
) -> tuple[list[BankGenome], list[AttackerGenome]]:
    """Apply the minimal criterion filter.

    A bank is viable if:
    - It blocks at least one current attacker
    - It is broken by at least one current attacker
    - It approves at least mc_bank_min_legit_rate of legitimate transactions

    An attacker is viable if:
    - It succeeds against at least one current bank
    - It fails against at least one current bank

    If MC would eliminate >80% of a population, relax it for that generation.
    """
    viable_banks = []
    for bank in banks:
        bank_results = results.get(bank.genome_id, [])
        attack_results = [r for r in bank_results if r.type in (EpisodeType.ATTACK, EpisodeType.HALL_OF_FAME)]
        legit_results = [r for r in bank_results if r.type == EpisodeType.LEGITIMATE]

        blocks_at_least_one = any(r.outcome == EpisodeOutcome.ATTACK_BLOCKED for r in attack_results)
        broken_by_at_least_one = any(r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED for r in attack_results)

        legit_rate = (
            sum(1 for r in legit_results if r.outcome == EpisodeOutcome.LEGITIMATE_APPROVED)
            / len(legit_results)
            if legit_results else 0.0
        )
        approves_legit = legit_rate >= mc_bank_min_legit_rate

        if blocks_at_least_one and broken_by_at_least_one and approves_legit:
            viable_banks.append(bank)

    viable_attackers = []
    for attacker in attackers:
        attacker_results = results.get(attacker.genome_id, [])
        succeeds_at_least_one = any(r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED for r in attacker_results)
        fails_at_least_one = any(r.outcome == EpisodeOutcome.ATTACK_BLOCKED for r in attacker_results)

        if succeeds_at_least_one and fails_at_least_one:
            viable_attackers.append(attacker)

    # Relaxation: if MC is too restrictive, skip it
    if len(viable_banks) < len(banks) * relaxation_threshold:
        logger.warning(
            "MC too restrictive for banks: %d/%d viable (threshold=%.0f%%). Relaxing.",
            len(viable_banks), len(banks), relaxation_threshold * 100,
        )
        viable_banks = list(banks)

    if len(viable_attackers) < len(attackers) * relaxation_threshold:
        logger.warning(
            "MC too restrictive for attackers: %d/%d viable (threshold=%.0f%%). Relaxing.",
            len(viable_attackers), len(attackers), relaxation_threshold * 100,
        )
        viable_attackers = list(attackers)

    return viable_banks, viable_attackers
