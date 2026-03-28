"""Tests for all five safeguards — Layer 5."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from src.genomes.attacker_genome import AttackerGenome
from src.genomes.bank_genome import BankGenome, DefensePipeline
from src.models import (
    AttackerFitness,
    BankFitness,
    EpisodeOutcome,
    EpisodeResult,
    EpisodeType,
    GenerationStats,
)
from src.safeguards.curriculum import CurriculumManager
from src.safeguards.hall_of_fame import HallOfFame
from src.safeguards.minimal_criterion import apply_minimal_criterion
from src.safeguards.novelty import (
    BEHAVIOR_DIM,
    apply_fitness_sharing,
    assign_archetype,
    compute_behavior_descriptor,
    compute_novelty,
)
from src.safeguards.speciation import Species, speciate


def _attacker(genome_id: str, success_rate: float = 0.5, **kwargs) -> AttackerGenome:
    a = AttackerGenome(genome_id=genome_id, code="class AttackStrategy:\n  pass")
    a.fitness = AttackerFitness(success_rate=success_rate, **kwargs)
    return a


def _attacker_with_descriptor(genome_id: str, descriptor: list[float], **kwargs) -> AttackerGenome:
    a = _attacker(genome_id, **kwargs)
    a.behavior_descriptor = np.array(descriptor)
    return a


def _bank(genome_id: str, cdr: float = 0.8, hdr: float = 0.8, lar: float = 0.9) -> BankGenome:
    b = BankGenome(
        genome_id=genome_id,
        defense_pipeline=DefensePipeline(
            system_prompt="secure",
            classification_prompt="classify",
            transfer_verification_prompt="verify",
            approved_recipients=["treasury_main"],
        ),
    )
    b.fitness = BankFitness(current_defense_rate=cdr, historical_defense_rate=hdr, legitimate_approval_rate=lar)
    return b


def _attack_result(bank_id: str, attacker_id: str, outcome: EpisodeOutcome, ep_type: EpisodeType = EpisodeType.ATTACK) -> EpisodeResult:
    return EpisodeResult(
        bank_id=bank_id,
        attacker_id=attacker_id,
        type=ep_type,
        outcome=outcome,
    )


# --- Hall of Fame Tests ---

class TestHallOfFame:
    def test_monotonic_growth(self):
        """HoF only grows — entries are never removed unless dominated."""
        hof = HallOfFame(max_size=50)
        atk = _attacker("atk_1", success_rate=0.5)
        results = {"atk_1": [_attack_result("b1", "atk_1", EpisodeOutcome.ATTACK_SUCCEEDED)]}

        initial_size = len(hof.attack_archive)
        hof.update_attack_archive([atk], results)
        assert len(hof.attack_archive) >= initial_size

    def test_only_successful_attacks_added(self):
        hof = HallOfFame(max_size=50)
        atk = _attacker("atk_fail")
        results = {"atk_fail": [_attack_result("b1", "atk_fail", EpisodeOutcome.ATTACK_BLOCKED)]}

        hof.update_attack_archive([atk], results)
        assert len(hof.attack_archive) == 0

    def test_max_size_respected(self):
        hof = HallOfFame(max_size=3)
        for i in range(10):
            atk = _attacker(f"atk_{i}", success_rate=0.1 * i)
            atk.behavior_descriptor = np.array([i * 0.1] * BEHAVIOR_DIM)
            results = {f"atk_{i}": [_attack_result("b1", f"atk_{i}", EpisodeOutcome.ATTACK_SUCCEEDED)]}
            hof.update_attack_archive([atk], results)
        assert len(hof.attack_archive) <= 3

    def test_serialization_roundtrip(self):
        hof = HallOfFame(max_size=10)
        atk = _attacker("atk_1")
        results = {"atk_1": [_attack_result("b1", "atk_1", EpisodeOutcome.ATTACK_SUCCEEDED)]}
        hof.update_attack_archive([atk], results)

        d = hof.to_dict()
        restored = HallOfFame.from_dict(d)
        assert len(restored.attack_archive) == len(hof.attack_archive)


# --- Curriculum Manager Tests ---

class TestCurriculumManager:
    def test_initial_state(self):
        cm = CurriculumManager()
        assert cm.attacker_complexity_cap == 1
        features = cm.get_allowed_attack_features()
        assert features["max_turns"] == 1

    def test_unlock_on_low_attack_success(self):
        cm = CurriculumManager()
        stats = GenerationStats(attack_success_rate=0.05)
        cm.update_complexity(stats)
        assert cm.attacker_complexity_cap == 2

    def test_unlock_defense_on_high_attack_success(self):
        cm = CurriculumManager()
        stats = GenerationStats(attack_success_rate=0.80)
        cm.update_complexity(stats)
        assert cm.defense_complexity_cap == 2

    def test_stagnation_unlocks_both(self):
        cm = CurriculumManager()
        stats = GenerationStats(attack_success_rate=0.5, generations_since_improvement=6)
        cm.update_complexity(stats)
        assert cm.attacker_complexity_cap == 2
        assert cm.defense_complexity_cap == 2

    def test_cap_at_max(self):
        cm = CurriculumManager()
        cm.attacker_complexity_cap = 4
        stats = GenerationStats(attack_success_rate=0.05)
        cm.update_complexity(stats)
        assert cm.attacker_complexity_cap == 4

    def test_serialization_roundtrip(self):
        cm = CurriculumManager()
        cm.attacker_complexity_cap = 3
        cm.defense_complexity_cap = 2
        d = cm.to_dict()
        restored = CurriculumManager.from_dict(d)
        assert restored.attacker_complexity_cap == 3
        assert restored.defense_complexity_cap == 2


# --- Minimal Criterion Tests ---

class TestMinimalCriterion:
    def _make_results(self) -> dict[str, list[EpisodeResult]]:
        return {
            "bank_good": [
                _attack_result("bank_good", "atk1", EpisodeOutcome.ATTACK_BLOCKED),
                _attack_result("bank_good", "atk2", EpisodeOutcome.ATTACK_SUCCEEDED),
                EpisodeResult(bank_id="bank_good", type=EpisodeType.LEGITIMATE, outcome=EpisodeOutcome.LEGITIMATE_APPROVED),
                EpisodeResult(bank_id="bank_good", type=EpisodeType.LEGITIMATE, outcome=EpisodeOutcome.LEGITIMATE_APPROVED),
            ],
            "bank_bad": [
                _attack_result("bank_bad", "atk1", EpisodeOutcome.ATTACK_SUCCEEDED),
                _attack_result("bank_bad", "atk2", EpisodeOutcome.ATTACK_SUCCEEDED),
                EpisodeResult(bank_id="bank_bad", type=EpisodeType.LEGITIMATE, outcome=EpisodeOutcome.LEGITIMATE_REJECTED),
            ],
            "atk1": [
                _attack_result("bank_good", "atk1", EpisodeOutcome.ATTACK_BLOCKED),
                _attack_result("bank_bad", "atk1", EpisodeOutcome.ATTACK_SUCCEEDED),
            ],
            "atk2": [
                _attack_result("bank_good", "atk2", EpisodeOutcome.ATTACK_SUCCEEDED),
                _attack_result("bank_bad", "atk2", EpisodeOutcome.ATTACK_SUCCEEDED),
            ],
        }

    def test_filters_correctly(self):
        banks = [_bank("bank_good"), _bank("bank_bad")]
        attackers = [_attacker("atk1"), _attacker("atk2")]
        results = self._make_results()

        viable_banks, viable_attackers = apply_minimal_criterion(banks, attackers, results)
        viable_bank_ids = [b.genome_id for b in viable_banks]
        viable_atk_ids = [a.genome_id for a in viable_attackers]

        assert "bank_good" in viable_bank_ids
        assert "atk1" in viable_atk_ids

    def test_relaxation_when_too_restrictive(self):
        """MC should relax if it would eliminate >80% of population."""
        banks = [_bank(f"bank_{i}") for i in range(10)]
        attackers = [_attacker(f"atk_{i}") for i in range(10)]
        results = {b.genome_id: [] for b in banks}
        results.update({a.genome_id: [] for a in attackers})

        viable_banks, viable_attackers = apply_minimal_criterion(banks, attackers, results)
        assert len(viable_banks) == len(banks)
        assert len(viable_attackers) == len(attackers)


# --- Novelty Tests ---

class TestNovelty:
    def test_behavior_descriptor_shape(self):
        atk = _attacker("atk_1")
        desc = compute_behavior_descriptor(atk)
        assert desc.shape == (BEHAVIOR_DIM,)

    def test_novelty_high_for_unique(self):
        similar = [_attacker_with_descriptor(f"atk_{i}", [0.2] * BEHAVIOR_DIM) for i in range(5)]
        unique = _attacker_with_descriptor("atk_unique", [0.9] * BEHAVIOR_DIM)

        novelty = compute_novelty(unique, similar, [], k=3)
        assert novelty > 0

    def test_novelty_low_for_identical(self):
        population = [_attacker_with_descriptor(f"atk_{i}", [0.5] * BEHAVIOR_DIM) for i in range(5)]
        target = _attacker_with_descriptor("atk_target", [0.5] * BEHAVIOR_DIM)

        novelty = compute_novelty(target, population, [], k=3)
        assert novelty == pytest.approx(0.0, abs=1e-6)


# --- Fitness Sharing Tests ---

class TestFitnessSharing:
    def test_crowded_niche_fitness_reduced(self):
        cluster = [_attacker_with_descriptor(f"c_{i}", [0.5] * BEHAVIOR_DIM, success_rate=0.5) for i in range(5)]
        lone = _attacker_with_descriptor("lone", [0.0] * BEHAVIOR_DIM, success_rate=0.5)
        pop = cluster + [lone]

        apply_fitness_sharing(pop, sigma_share=0.3)

        assert lone.shared_fitness.success_rate > cluster[0].shared_fitness.success_rate

    def test_no_sharing_when_distant(self):
        a = _attacker_with_descriptor("a", [0.0] * BEHAVIOR_DIM, success_rate=0.5)
        b = _attacker_with_descriptor("b", [1.0] * BEHAVIOR_DIM, success_rate=0.5)

        apply_fitness_sharing([a, b], sigma_share=0.1)

        assert a.shared_fitness.success_rate == pytest.approx(a.fitness.success_rate, abs=1e-6)


# --- Archetype Tests ---

class TestArchetypes:
    def test_assign_archetype_returns_unclassified_without_centroids(self):
        atk = _attacker_with_descriptor("atk", [0.5] * BEHAVIOR_DIM)
        arch = assign_archetype(atk)
        assert arch == "unclassified"


# --- Speciation Tests ---

class TestSpeciation:
    def test_creates_species(self):
        pop = []
        for i in range(6):
            a = _attacker_with_descriptor(f"atk_{i}", [i * 0.2] * BEHAVIOR_DIM)
            pop.append(a)

        species_list = speciate(pop, [], threshold=0.3)
        assert len(species_list) >= 1
        total_members = sum(len(s.members) for s in species_list)
        assert total_members == len(pop)

    def test_removes_empty_species(self):
        atk = _attacker_with_descriptor("atk_1", [0.5] * BEHAVIOR_DIM)
        sp = Species(representative=atk, members=[])
        result = speciate([atk], [sp], threshold=10.0)
        assert all(len(s.members) > 0 for s in result)
