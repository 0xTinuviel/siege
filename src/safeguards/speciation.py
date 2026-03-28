"""NEAT-style speciation — Section 6.5 of the spec.

Protects innovative but initially weak strategies from immediate elimination.
Uses behavioral descriptors (12D for attackers, 10D for banks) for species
compatibility.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.safeguards.novelty import compute_behavior_descriptor


@dataclass
class Species:
    representative: Any
    members: list[Any] = field(default_factory=list)
    avg_fitness_history: list[float] = field(default_factory=list)
    generations_without_improvement: int = 0
    archetype: str = "unclassified"

    def is_compatible(self, individual: Any, threshold: float = 0.3) -> bool:
        desc_a = compute_behavior_descriptor(self.representative)
        desc_b = compute_behavior_descriptor(individual)
        return float(np.linalg.norm(desc_a - desc_b)) < threshold


def speciate(
    population: list[Any],
    existing_species: list[Species],
    threshold: float = 0.3,
) -> list[Species]:
    """Assign individuals to species. Create new species for unmatched individuals."""
    for sp in existing_species:
        sp.members = []

    for individual in population:
        matched = False
        for sp in existing_species:
            if sp.is_compatible(individual, threshold):
                sp.members.append(individual)
                matched = True
                break
        if not matched:
            new_sp = Species(representative=individual)
            new_sp.members.append(individual)
            existing_species.append(new_sp)

    existing_species = [s for s in existing_species if len(s.members) > 0]

    for sp in existing_species:
        sp.representative = random.choice(sp.members)

    for sp in existing_species:
        if sp.members and sp.members[0].fitness is not None:
            avg_fit = _avg_primary_fitness(sp.members)
            if sp.avg_fitness_history and avg_fit <= sp.avg_fitness_history[-1]:
                sp.generations_without_improvement += 1
            else:
                sp.generations_without_improvement = 0
            sp.avg_fitness_history.append(avg_fit)

    return existing_species


def _avg_primary_fitness(members: list[Any]) -> float:
    """Average of the first fitness objective across members."""
    values = []
    for m in members:
        if m.fitness is None:
            continue
        objectives = m.fitness.objectives()
        if objectives:
            values.append(objectives[0][1])
    return float(np.mean(values)) if values else 0.0
