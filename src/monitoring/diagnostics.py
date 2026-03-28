"""Pathology detection and alert system — Section 10.2 of the spec."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from src.models import (
    AttackerFitness,
    BankFitness,
    EngagementDiagnostics,
    EpisodeOutcome,
    EpisodeResult,
    EpisodeType,
)


def compute_diagnostics(
    results: dict[str, list[EpisodeResult]],
    bank_population: list[Any],
    attacker_population: list[Any],
    bank_species_count: int,
    attacker_species_count: int,
) -> EngagementDiagnostics:
    """Compute engagement diagnostics from a generation's results."""
    all_results = []
    seen = set()
    for result_list in results.values():
        for r in result_list:
            if r.episode_id not in seen:
                seen.add(r.episode_id)
                all_results.append(r)

    attack_results = [r for r in all_results if r.type == EpisodeType.ATTACK]
    hof_results = [r for r in all_results if r.type == EpisodeType.HALL_OF_FAME]

    attack_success_rate = (
        sum(1 for r in attack_results if r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED) / len(attack_results)
        if attack_results else 0.0
    )
    hof_success_rate = (
        sum(1 for r in hof_results if r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED) / len(hof_results)
        if hof_results else 0.0
    )

    bank_variances = _fitness_variance(bank_population, BankFitness)
    attacker_variances = _fitness_variance(attacker_population, AttackerFitness)

    entropy = _strategy_entropy(attacker_population)

    all_fitness_values = []
    for ind in bank_population + attacker_population:
        if ind.fitness is None:
            continue
        for name, val in ind.fitness.objectives():
            if np.isfinite(val):
                all_fitness_values.append(val)
    fitness_std = float(np.std(all_fitness_values)) if all_fitness_values else 0.0

    return EngagementDiagnostics(
        attack_success_rate=attack_success_rate,
        hof_attack_success_rate=hof_success_rate,
        bank_fitness_variance=bank_variances,
        attacker_fitness_variance=attacker_variances,
        bank_species_count=bank_species_count,
        attacker_species_count=attacker_species_count,
        attacker_strategy_entropy=entropy,
        fitness_reward_std=fitness_std,
    )


def check_pathologies(diag: EngagementDiagnostics) -> list[str]:
    """Check for coevolutionary pathologies and return alert strings."""
    alerts = []

    if diag.attack_success_rate < 0.05:
        alerts.append(
            "DISENGAGEMENT: Bank is too strong. "
            "Increase attacker complexity cap or inject diverse attackers."
        )
    if diag.attack_success_rate > 0.95:
        alerts.append(
            "DISENGAGEMENT: Attackers are too strong. "
            "Increase bank complexity cap or inject diverse banks."
        )
    if diag.bank_fitness_variance < 0.01:
        alerts.append(
            "LOSS OF GRADIENT: All banks have similar fitness. Inject random immigrants."
        )
    if diag.attacker_fitness_variance < 0.01:
        alerts.append(
            "LOSS OF GRADIENT: All attackers have similar fitness. Inject random immigrants."
        )
    if abs(diag.attack_success_rate - diag.hof_attack_success_rate) > 0.3:
        alerts.append(
            "CYCLING: Current banks handle current attackers but fail on historical ones. "
            "Hall of Fame pressure insufficient."
        )
    if diag.bank_species_count <= 1:
        alerts.append("DIVERSITY COLLAPSE (banks): Lower speciation threshold.")
    if diag.attacker_species_count <= 1:
        alerts.append("DIVERSITY COLLAPSE (attackers): Lower speciation threshold.")
    if diag.attacker_strategy_entropy < 0.5:
        alerts.append(
            "ECHO TRAP: Attackers converging on single strategy template. "
            "Increase novelty weight or inject random immigrants."
        )

    return alerts


def _fitness_variance(population: list[Any], fitness_cls: type) -> float:
    """Compute mean variance across fitness objectives."""
    if not population:
        return 0.0
    values_per_obj: dict[str, list[float]] = {}
    for ind in population:
        if ind.fitness is None:
            continue
        for name, val in ind.fitness.objectives():
            if np.isfinite(val):
                values_per_obj.setdefault(name, []).append(val)
    if not values_per_obj:
        return 0.0
    variances = [float(np.var(vals)) for vals in values_per_obj.values() if vals]
    return float(np.mean(variances)) if variances else 0.0


def _strategy_entropy(attackers: list[Any]) -> float:
    """Shannon entropy over discretized behavior descriptors."""
    if not attackers:
        return 0.0

    from src.safeguards.novelty import compute_behavior_descriptor

    descriptors = []
    for a in attackers:
        desc = compute_behavior_descriptor(a)
        discretized = tuple(round(float(v), 1) for v in desc)
        descriptors.append(discretized)

    from collections import Counter
    counts = Counter(descriptors)
    total = len(descriptors)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy
