"""Pareto ranking (NSGA-II style) + tournament selection — Sections 4.3, 5.1 of the spec."""

from __future__ import annotations

import math
import random
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HasFitness(Protocol):
    fitness: Any
    pareto_rank: int
    crowding_distance: float


def dominates(fitness_a: Any, fitness_b: Any) -> bool:
    """A dominates B if A is >= B on all objectives and strictly > on at least one.

    Handles LOWER_IS_BETTER objectives by inverting comparisons.
    """
    lower_is_better = getattr(fitness_a, "LOWER_IS_BETTER", set())
    at_least_one_strictly_better = False

    for name in fitness_a.__dataclass_fields__:
        if name in ("LOWER_IS_BETTER",):
            continue
        val_a = getattr(fitness_a, name)
        val_b = getattr(fitness_b, name)

        if math.isnan(val_a) or math.isnan(val_b):
            continue

        # Both inf on same sign → equal, skip
        if math.isinf(val_a) and math.isinf(val_b):
            if (val_a > 0) == (val_b > 0):
                continue

        if name in lower_is_better:
            val_a, val_b = -val_a, -val_b

        # After inversion: -inf is worst, +inf is best
        if val_a < val_b:
            return False
        if val_a > val_b:
            at_least_one_strictly_better = True

    return at_least_one_strictly_better


def pareto_rank(population: list[Any]) -> list[list[Any]]:
    """Non-dominated sorting. Returns list of Pareto fronts.

    Front 0 = non-dominated individuals (best).
    Front 1 = dominated only by Front 0.
    etc.
    """
    pop_with_fitness = [ind for ind in population if ind.fitness is not None]
    if not pop_with_fitness:
        return [list(population)] if population else []

    fronts: list[list[Any]] = []
    remaining = list(pop_with_fitness)

    while remaining:
        front = []
        for ind in remaining:
            is_dominated = False
            for other in remaining:
                if other is ind:
                    continue
                if dominates(other.fitness, ind.fitness):
                    is_dominated = True
                    break
            if not is_dominated:
                front.append(ind)
        if not front:
            front = list(remaining)
            fronts.append(front)
            break
        fronts.append(front)
        remaining = [ind for ind in remaining if ind not in front]

    return fronts


def compute_crowding_distance(front: list[Any]) -> None:
    """Compute crowding distance for individuals in a single Pareto front.

    Sets ind.crowding_distance for each individual.
    """
    n = len(front)
    if n == 0:
        return

    for ind in front:
        ind.crowding_distance = 0.0

    if n <= 2:
        for ind in front:
            ind.crowding_distance = float("inf")
        return

    fitness_sample = front[0].fitness
    objective_names = [
        name for name in fitness_sample.__dataclass_fields__
        if name not in ("LOWER_IS_BETTER",)
    ]

    for obj_name in objective_names:
        sorted_front = sorted(front, key=lambda ind: getattr(ind.fitness, obj_name))

        f_min = getattr(sorted_front[0].fitness, obj_name)
        f_max = getattr(sorted_front[-1].fitness, obj_name)
        spread = f_max - f_min

        sorted_front[0].crowding_distance = float("inf")
        sorted_front[-1].crowding_distance = float("inf")

        if spread == 0:
            continue

        for i in range(1, n - 1):
            val_next = getattr(sorted_front[i + 1].fitness, obj_name)
            val_prev = getattr(sorted_front[i - 1].fitness, obj_name)
            sorted_front[i].crowding_distance += (val_next - val_prev) / spread


def assign_pareto_ranks_and_crowding(fronts: list[list[Any]]) -> None:
    """Assign pareto_rank and crowding_distance to all individuals across fronts."""
    for rank, front in enumerate(fronts):
        for ind in front:
            ind.pareto_rank = rank
        compute_crowding_distance(front)


def select_parent(population: list[Any], tournament_size: int = 3) -> Any:
    """Tournament selection: pick best by (pareto_rank ASC, crowding_distance DESC)."""
    tournament = random.sample(population, min(tournament_size, len(population)))
    tournament.sort(key=lambda ind: (ind.pareto_rank, -ind.crowding_distance))
    return tournament[0]
