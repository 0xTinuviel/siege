"""Tests for fitness computation — Layer 3."""

import pytest

from src.evaluation.fitness import compute_attacker_fitness, compute_bank_fitness
from src.models import AttackerFitness, BankFitness, EpisodeOutcome, EpisodeResult, EpisodeType


def _attack_result(outcome: EpisodeOutcome, llm_calls: int = 2, turns: int = 1, amount: float = 0.0) -> EpisodeResult:
    return EpisodeResult(
        bank_id="bank_1",
        attacker_id="atk_1",
        type=EpisodeType.ATTACK,
        outcome=outcome,
        turn_count=turns,
        llm_call_count=llm_calls,
        amount_transferred=amount,
    )


def _legit_result(outcome: EpisodeOutcome, llm_calls: int = 2) -> EpisodeResult:
    return EpisodeResult(
        bank_id="bank_1",
        legitimate_tx_id="legit_1",
        type=EpisodeType.LEGITIMATE,
        outcome=outcome,
        llm_call_count=llm_calls,
    )


def _hof_result(outcome: EpisodeOutcome, llm_calls: int = 2) -> EpisodeResult:
    return EpisodeResult(
        bank_id="bank_1",
        attacker_id="hof_atk_1",
        type=EpisodeType.HALL_OF_FAME,
        outcome=outcome,
        llm_call_count=llm_calls,
    )


class TestBankFitness:
    def test_perfect_defense(self):
        results = [
            _attack_result(EpisodeOutcome.ATTACK_BLOCKED),
            _attack_result(EpisodeOutcome.ATTACK_BLOCKED),
            _legit_result(EpisodeOutcome.LEGITIMATE_APPROVED),
            _hof_result(EpisodeOutcome.ATTACK_BLOCKED),
        ]
        f = compute_bank_fitness("bank_1", results)
        assert f.current_defense_rate == 1.0
        assert f.legitimate_approval_rate == 1.0
        assert f.historical_defense_rate == 1.0

    def test_mixed_results(self):
        results = [
            _attack_result(EpisodeOutcome.ATTACK_BLOCKED, llm_calls=2),
            _attack_result(EpisodeOutcome.ATTACK_SUCCEEDED, llm_calls=3),
            _legit_result(EpisodeOutcome.LEGITIMATE_APPROVED, llm_calls=2),
            _legit_result(EpisodeOutcome.LEGITIMATE_REJECTED, llm_calls=1),
            _hof_result(EpisodeOutcome.ATTACK_BLOCKED),
            _hof_result(EpisodeOutcome.ATTACK_SUCCEEDED),
        ]
        f = compute_bank_fitness("bank_1", results)
        assert f.current_defense_rate == 0.5
        assert f.legitimate_approval_rate == 0.5
        assert f.historical_defense_rate == 0.5

    def test_no_attacks(self):
        results = [_legit_result(EpisodeOutcome.LEGITIMATE_APPROVED)]
        f = compute_bank_fitness("bank_1", results)
        assert f.current_defense_rate == 0.0
        assert f.legitimate_approval_rate == 1.0


class TestAttackerFitness:
    def test_successful_attacker(self):
        results = [
            _attack_result(EpisodeOutcome.ATTACK_SUCCEEDED, turns=2, amount=500),
            _attack_result(EpisodeOutcome.ATTACK_SUCCEEDED, turns=3, amount=300),
            _attack_result(EpisodeOutcome.ATTACK_BLOCKED),
        ]
        f = compute_attacker_fitness("atk_1", results, novelty_score=0.5)
        assert abs(f.success_rate - 2 / 3) < 1e-9
        assert f.total_extracted == 800.0
        assert f.avg_turns_to_success == 2.5
        assert f.novelty_score == 0.5

    def test_no_successes(self):
        results = [_attack_result(EpisodeOutcome.ATTACK_BLOCKED)]
        f = compute_attacker_fitness("atk_1", results)
        assert f.success_rate == 0.0
        assert f.avg_turns_to_success == float("inf")

    def test_empty_results(self):
        f = compute_attacker_fitness("atk_1", [])
        assert f.success_rate == 0.0
