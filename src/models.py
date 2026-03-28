"""Core data models for SIEGE — Section 9 of the spec."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import json
import uuid


class EpisodeOutcome(Enum):
    ATTACK_BLOCKED = "ATTACK_BLOCKED"
    ATTACK_SUCCEEDED = "ATTACK_SUCCEEDED"
    LEGITIMATE_APPROVED = "LEGITIMATE_APPROVED"
    LEGITIMATE_REJECTED = "LEGITIMATE_REJECTED"


class EpisodeType(Enum):
    ATTACK = "attack"
    LEGITIMATE = "legitimate"
    HALL_OF_FAME = "hall_of_fame"
    PERTURBATION = "perturbation"


@dataclass
class EpisodeResult:
    episode_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bank_id: str = ""
    attacker_id: Optional[str] = None
    legitimate_tx_id: Optional[str] = None
    type: EpisodeType = EpisodeType.ATTACK
    outcome: EpisodeOutcome = EpisodeOutcome.ATTACK_BLOCKED
    turn_count: int = 0
    llm_call_count: int = 0
    amount_transferred: float = 0.0
    conversation_log: list[dict] = field(default_factory=list)
    bank_internal_reasoning: list[str] = field(default_factory=list)
    bank_pipeline_stages_triggered: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "bank_id": self.bank_id,
            "attacker_id": self.attacker_id,
            "legitimate_tx_id": self.legitimate_tx_id,
            "type": self.type.value,
            "outcome": self.outcome.value,
            "turn_count": self.turn_count,
            "llm_call_count": self.llm_call_count,
            "amount_transferred": self.amount_transferred,
            "conversation_log": self.conversation_log,
            "bank_internal_reasoning": self.bank_internal_reasoning,
            "bank_pipeline_stages_triggered": self.bank_pipeline_stages_triggered,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EpisodeResult:
        return cls(
            episode_id=data["episode_id"],
            bank_id=data["bank_id"],
            attacker_id=data.get("attacker_id"),
            legitimate_tx_id=data.get("legitimate_tx_id"),
            type=EpisodeType(data["type"]),
            outcome=EpisodeOutcome(data["outcome"]),
            turn_count=data["turn_count"],
            llm_call_count=data["llm_call_count"],
            amount_transferred=data.get("amount_transferred", 0.0),
            conversation_log=data.get("conversation_log", []),
            bank_internal_reasoning=data.get("bank_internal_reasoning", []),
            bank_pipeline_stages_triggered=data.get("bank_pipeline_stages_triggered", []),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class BankFitness:
    current_defense_rate: float = 0.0
    historical_defense_rate: float = 0.0
    legitimate_approval_rate: float = 0.0
    avg_llm_calls_per_episode: float = 0.0

    LOWER_IS_BETTER = {"avg_llm_calls_per_episode"}

    def to_dict(self) -> dict:
        return {
            "current_defense_rate": self.current_defense_rate,
            "historical_defense_rate": self.historical_defense_rate,
            "legitimate_approval_rate": self.legitimate_approval_rate,
            "avg_llm_calls_per_episode": self.avg_llm_calls_per_episode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BankFitness:
        return cls(**data)

    def objectives(self) -> list[tuple[str, float]]:
        return [(k, getattr(self, k)) for k in self.__dataclass_fields__]


@dataclass
class AttackerFitness:
    success_rate: float = 0.0
    avg_penetration_depth: float = 0.0
    total_extracted: float = 0.0
    novelty_score: float = 0.0
    avg_turns_to_success: float = float("inf")

    LOWER_IS_BETTER = {"avg_turns_to_success"}

    def to_dict(self) -> dict:
        return {
            "success_rate": self.success_rate,
            "avg_penetration_depth": self.avg_penetration_depth,
            "total_extracted": self.total_extracted,
            "novelty_score": self.novelty_score,
            "avg_turns_to_success": self.avg_turns_to_success,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AttackerFitness:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def objectives(self) -> list[tuple[str, float]]:
        return [(k, getattr(self, k)) for k in self.__dataclass_fields__]


@dataclass
class GenerationStats:
    generation: int = 0
    attack_success_rate: float = 0.0
    legitimate_approval_rate: float = 0.0
    avg_penetration_depth: float = 0.0
    avg_bank_defense_rate: float = 0.0
    avg_attacker_success_rate: float = 0.0
    hof_size: int = 0
    bank_species_count: int = 0
    attacker_species_count: int = 0
    best_bank_defense_rate: float = 0.0
    best_attacker_success_rate: float = 0.0
    generations_since_improvement: int = 0

    def is_stagnant(self, window: int = 10) -> bool:
        return self.generations_since_improvement >= window

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, data: dict) -> GenerationStats:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EngagementDiagnostics:
    attack_success_rate: float = 0.0
    hof_attack_success_rate: float = 0.0
    bank_fitness_variance: float = 0.0
    attacker_fitness_variance: float = 0.0
    bank_species_count: int = 0
    attacker_species_count: int = 0
    attacker_strategy_entropy: float = 0.0
    fitness_reward_std: float = 0.0

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, data: dict) -> EngagementDiagnostics:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class LegitimateTransaction:
    id: str = ""
    message: str = ""
    expected_action: str = "APPROVE"
    recipient: Optional[str] = None
    amount: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "expected_action": self.expected_action,
            "recipient": self.recipient,
            "amount": self.amount,
        }

    @classmethod
    def from_dict(cls, data: dict) -> LegitimateTransaction:
        return cls(**data)
