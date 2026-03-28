"""Multi-objective fitness computation — Section 4 of the spec."""

from __future__ import annotations

import numpy as np

from src.models import AttackerFitness, BankFitness, EpisodeOutcome, EpisodeResult, EpisodeType

_PIPELINE_STAGES = ["pre_processing", "classification", "verification", "post_processing", "transfer"]


def compute_attack_penetration_depth(episode: EpisodeResult) -> float:
    """Score how far the attack penetrated the bank's defense pipeline.

    Provides gradient even when no attacks fully succeed — critical for
    preventing disengagement in early generations.

    0.0 = blocked by pre-processing (trivially detected)
    0.25 = passed pre-processing, blocked by classification
    0.50 = classified as legitimate, blocked by verification
    0.75 = passed verification, blocked by post-processing
    1.0 = full penetration (attack succeeded, transfer executed)
    """
    triggered = episode.bank_pipeline_stages_triggered
    if not triggered:
        return 0.0
    for i, stage in enumerate(_PIPELINE_STAGES):
        if stage not in triggered:
            return i / len(_PIPELINE_STAGES)
    return 1.0


def compute_bank_fitness(bank_id: str, results: list[EpisodeResult]) -> BankFitness:
    attack_results = [r for r in results if r.type == EpisodeType.ATTACK]
    legit_results = [r for r in results if r.type == EpisodeType.LEGITIMATE]
    hof_results = [r for r in results if r.type == EpisodeType.HALL_OF_FAME]

    current_defense_rate = (
        sum(1 for r in attack_results if r.outcome == EpisodeOutcome.ATTACK_BLOCKED) / len(attack_results)
        if attack_results else 0.0
    )
    historical_defense_rate = (
        sum(1 for r in hof_results if r.outcome == EpisodeOutcome.ATTACK_BLOCKED) / max(len(hof_results), 1)
    )
    legitimate_approval_rate = (
        sum(1 for r in legit_results if r.outcome == EpisodeOutcome.LEGITIMATE_APPROVED) / len(legit_results)
        if legit_results else 0.0
    )

    all_calls = [r.llm_call_count for r in results if r.llm_call_count > 0]
    avg_llm_calls = float(np.mean(all_calls)) if all_calls else 0.0

    return BankFitness(
        current_defense_rate=current_defense_rate,
        historical_defense_rate=historical_defense_rate,
        legitimate_approval_rate=legitimate_approval_rate,
        avg_llm_calls_per_episode=avg_llm_calls,
    )


def compute_attacker_fitness(
    attacker_id: str,
    results: list[EpisodeResult],
    novelty_score: float = 0.0,
) -> AttackerFitness:
    if not results:
        return AttackerFitness(novelty_score=novelty_score)

    success_count = sum(1 for r in results if r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED)
    success_rate = success_count / len(results)

    avg_depth = float(np.mean([compute_attack_penetration_depth(r) for r in results]))

    total_extracted = sum(
        r.amount_transferred for r in results if r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED
    )

    successful_turns = [
        r.turn_count for r in results if r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED
    ]
    avg_turns = float(np.mean(successful_turns)) if successful_turns else float("inf")

    return AttackerFitness(
        success_rate=success_rate,
        avg_penetration_depth=avg_depth,
        total_extracted=total_extracted,
        novelty_score=novelty_score,
        avg_turns_to_success=avg_turns,
    )
