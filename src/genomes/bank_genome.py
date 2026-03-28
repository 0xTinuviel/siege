"""Bank genome representation — Section 2.1 of the spec."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import copy
import json
import uuid

import numpy as np


def _generate_bank_id() -> str:
    return f"bank_{uuid.uuid4().hex[:8]}"


@dataclass
class DefensePipeline:
    system_prompt: str = ""
    pre_processing_rules: list[str] = field(default_factory=list)
    classification_prompt: Optional[str] = ""
    transfer_verification_prompt: Optional[str] = ""
    post_processing_rules: list[str] = field(default_factory=list)
    approved_recipients: list[str] = field(default_factory=lambda: ["treasury_main", "payroll", "vendor_escrow"])
    daily_limit: float = 1000.0
    multi_turn_memory: bool = True
    max_turns_per_session: int = 5

    def to_dict(self) -> dict:
        return {
            "system_prompt": self.system_prompt,
            "pre_processing_rules": list(self.pre_processing_rules),
            "classification_prompt": self.classification_prompt,
            "transfer_verification_prompt": self.transfer_verification_prompt,
            "post_processing_rules": list(self.post_processing_rules),
            "approved_recipients": list(self.approved_recipients),
            "daily_limit": self.daily_limit,
            "multi_turn_memory": self.multi_turn_memory,
            "max_turns_per_session": self.max_turns_per_session,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DefensePipeline:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BankGenome:
    genome_id: str = field(default_factory=_generate_bank_id)
    generation: int = 0
    lineage: list[str] = field(default_factory=list)
    defense_pipeline: DefensePipeline = field(default_factory=DefensePipeline)

    fitness: Any = field(default=None, repr=False)
    shared_fitness: Any = field(default=None, repr=False)
    pareto_rank: int = 0
    crowding_distance: float = 0.0

    # 10D behavioral descriptor (populated during evaluation)
    behavior_descriptor: Optional[np.ndarray] = field(default=None, repr=False)

    avg_llm_calls: float = 0.0
    avg_response_length: float = 0.0

    def to_dict(self) -> dict:
        d = {
            "genome_id": self.genome_id,
            "generation": self.generation,
            "lineage": list(self.lineage),
            "defense_pipeline": self.defense_pipeline.to_dict(),
        }
        if self.behavior_descriptor is not None:
            d["behavior_descriptor"] = self.behavior_descriptor.tolist()
        if self.fitness is not None and hasattr(self.fitness, "to_dict"):
            d["fitness"] = self.fitness.to_dict()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> BankGenome:
        pipeline_data = data.get("defense_pipeline", {})
        bank = cls(
            genome_id=data.get("genome_id", _generate_bank_id()),
            generation=data.get("generation", 0),
            lineage=data.get("lineage", []),
            defense_pipeline=DefensePipeline.from_dict(pipeline_data),
        )
        if "behavior_descriptor" in data and data["behavior_descriptor"] is not None:
            bank.behavior_descriptor = np.array(data["behavior_descriptor"])
        return bank

    @classmethod
    def from_json(cls, json_str: str) -> BankGenome:
        return cls.from_dict(json.loads(json_str))

    def snapshot(self) -> BankGenome:
        """Create an immutable copy for archival."""
        return BankGenome.from_dict(self.to_dict())

    def validate(self) -> bool:
        """Check that genome has all required fields and is well-formed.

        classification_prompt and transfer_verification_prompt are optional —
        the weakest seed banks deliberately omit them.
        """
        p = self.defense_pipeline
        if not p.system_prompt:
            return False
        if not isinstance(p.approved_recipients, list) or len(p.approved_recipients) == 0:
            return False
        if not isinstance(p.daily_limit, (int, float)) or p.daily_limit <= 0:
            return False
        if not isinstance(p.max_turns_per_session, int) or p.max_turns_per_session < 1:
            return False
        return True
