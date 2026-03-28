"""Tests for Pareto ranking and crowding distance — Layer 3.

Uses 10 individuals with known dominance relationships.
"""

import math
from dataclasses import dataclass, field

import pytest

from src.models import AttackerFitness, BankFitness
from src.evolution.selection import (
    assign_pareto_ranks_and_crowding,
    compute_crowding_distance,
    dominates,
    pareto_rank,
    select_parent,
)


@dataclass
class FakeIndividual:
    name: str
    fitness: BankFitness
    pareto_rank: int = 0
    crowding_distance: float = 0.0


def _bank(cdr: float, hdr: float, lar: float, llm: float) -> BankFitness:
    return BankFitness(
        current_defense_rate=cdr,
        historical_defense_rate=hdr,
        legitimate_approval_rate=lar,
        avg_llm_calls_per_episode=llm,
    )


class TestDominates:
    def test_clear_domination(self):
        a = _bank(0.9, 0.8, 0.95, 2.0)
        b = _bank(0.5, 0.5, 0.5, 5.0)
        assert dominates(a, b)
        assert not dominates(b, a)

    def test_equal_does_not_dominate(self):
        a = _bank(0.8, 0.8, 0.8, 3.0)
        b = _bank(0.8, 0.8, 0.8, 3.0)
        assert not dominates(a, b)
        assert not dominates(b, a)

    def test_tradeoff_no_domination(self):
        a = _bank(0.9, 0.5, 0.8, 2.0)
        b = _bank(0.5, 0.9, 0.8, 2.0)
        assert not dominates(a, b)
        assert not dominates(b, a)

    def test_lower_is_better_objective(self):
        a = _bank(0.8, 0.8, 0.8, 2.0)  # fewer LLM calls = better
        b = _bank(0.8, 0.8, 0.8, 5.0)
        assert dominates(a, b)

    def test_attacker_fitness_dominance(self):
        a = AttackerFitness(success_rate=0.8, total_extracted=1000, novelty_score=0.5, avg_turns_to_success=2.0)
        b = AttackerFitness(success_rate=0.3, total_extracted=200, novelty_score=0.2, avg_turns_to_success=4.0)
        assert dominates(a, b)


class TestParetoRank:
    def _make_population(self):
        """10 individuals with known dominance structure."""
        return [
            FakeIndividual("A", _bank(0.95, 0.90, 0.95, 1.5)),  # front 0 (elite)
            FakeIndividual("B", _bank(0.90, 0.95, 0.90, 2.0)),  # front 0 (tradeoff with A)
            FakeIndividual("C", _bank(0.85, 0.85, 0.95, 1.0)),  # front 0 (low LLM calls)
            FakeIndividual("D", _bank(0.80, 0.80, 0.80, 2.5)),  # front 1 (dominated by A,B,C)
            FakeIndividual("E", _bank(0.75, 0.85, 0.70, 3.0)),  # front 1
            FakeIndividual("F", _bank(0.70, 0.70, 0.90, 2.0)),  # front 1
            FakeIndividual("G", _bank(0.60, 0.60, 0.60, 4.0)),  # front 2
            FakeIndividual("H", _bank(0.50, 0.50, 0.80, 3.0)),  # front 2
            FakeIndividual("I", _bank(0.40, 0.40, 0.40, 5.0)),  # front 3 (worst)
            FakeIndividual("J", _bank(0.30, 0.30, 0.30, 6.0)),  # front 3
        ]

    def test_correct_fronts(self):
        pop = self._make_population()
        fronts = pareto_rank(pop)
        assert len(fronts) >= 2
        front_0_names = {ind.name for ind in fronts[0]}
        # A, B, C should all be on front 0 (none dominates the others due to tradeoffs)
        assert "A" in front_0_names
        assert "B" in front_0_names
        assert "C" in front_0_names

    def test_all_nondominated(self):
        pop = [
            FakeIndividual("A", _bank(0.9, 0.5, 0.5, 3.0)),
            FakeIndividual("B", _bank(0.5, 0.9, 0.5, 3.0)),
            FakeIndividual("C", _bank(0.5, 0.5, 0.9, 3.0)),
        ]
        fronts = pareto_rank(pop)
        assert len(fronts) == 1
        assert len(fronts[0]) == 3

    def test_all_identical(self):
        f = _bank(0.5, 0.5, 0.5, 3.0)
        pop = [FakeIndividual(f"X{i}", f) for i in range(5)]
        fronts = pareto_rank(pop)
        assert len(fronts) == 1
        assert len(fronts[0]) == 5

    def test_single_dominates_all(self):
        pop = [
            FakeIndividual("King", _bank(1.0, 1.0, 1.0, 1.0)),
            FakeIndividual("B", _bank(0.5, 0.5, 0.5, 5.0)),
            FakeIndividual("C", _bank(0.3, 0.3, 0.3, 6.0)),
        ]
        fronts = pareto_rank(pop)
        assert len(fronts) == 3
        assert fronts[0][0].name == "King"

    def test_empty_population(self):
        fronts = pareto_rank([])
        assert fronts == []


class TestCrowdingDistance:
    def test_boundary_individuals_get_infinity(self):
        pop = [
            FakeIndividual("A", _bank(0.9, 0.5, 0.5, 3.0)),
            FakeIndividual("B", _bank(0.7, 0.7, 0.7, 2.0)),
            FakeIndividual("C", _bank(0.5, 0.9, 0.9, 1.0)),
        ]
        compute_crowding_distance(pop)
        # A and C are boundaries on at least one objective
        assert pop[0].crowding_distance == float("inf") or pop[2].crowding_distance == float("inf")

    def test_two_individuals_both_infinite(self):
        pop = [
            FakeIndividual("A", _bank(0.9, 0.5, 0.5, 3.0)),
            FakeIndividual("B", _bank(0.5, 0.9, 0.9, 1.0)),
        ]
        compute_crowding_distance(pop)
        assert pop[0].crowding_distance == float("inf")
        assert pop[1].crowding_distance == float("inf")


class TestAssignRanksAndCrowding:
    def test_full_pipeline(self):
        pop = [
            FakeIndividual("A", _bank(0.95, 0.90, 0.95, 1.5)),
            FakeIndividual("B", _bank(0.90, 0.95, 0.90, 2.0)),
            FakeIndividual("C", _bank(0.50, 0.50, 0.50, 5.0)),
        ]
        fronts = pareto_rank(pop)
        assign_pareto_ranks_and_crowding(fronts)

        a = next(i for i in pop if i.name == "A")
        b = next(i for i in pop if i.name == "B")
        c = next(i for i in pop if i.name == "C")
        assert a.pareto_rank == 0
        assert b.pareto_rank == 0
        assert c.pareto_rank > 0


class TestTournamentSelection:
    def test_favors_lower_rank(self):
        pop = [
            FakeIndividual("A", _bank(0.9, 0.9, 0.9, 1.0)),
            FakeIndividual("B", _bank(0.1, 0.1, 0.1, 5.0)),
        ]
        fronts = pareto_rank(pop)
        assign_pareto_ranks_and_crowding(fronts)

        wins = {"A": 0, "B": 0}
        for _ in range(100):
            winner = select_parent(pop, tournament_size=2)
            wins[winner.name] += 1
        assert wins["A"] > wins["B"]
