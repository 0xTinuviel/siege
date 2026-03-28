"""Attacker genome representation — Section 2.2 of the spec."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import json
import uuid

import numpy as np


def _generate_attacker_id() -> str:
    return f"attacker_{uuid.uuid4().hex[:8]}"


@dataclass
class AttackerGenome:
    genome_id: str = field(default_factory=_generate_attacker_id)
    generation: int = 0
    lineage: list[str] = field(default_factory=list)
    code: str = ""

    fitness: Any = field(default=None, repr=False)
    shared_fitness: Any = field(default=None, repr=False)
    pareto_rank: int = 0
    crowding_distance: float = 0.0

    # 12D behavioral descriptor (populated during evaluation)
    behavior_descriptor: Optional[np.ndarray] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = {
            "genome_id": self.genome_id,
            "generation": self.generation,
            "lineage": list(self.lineage),
            "code": self.code,
        }
        if self.behavior_descriptor is not None:
            d["behavior_descriptor"] = self.behavior_descriptor.tolist()
        if self.fitness is not None and hasattr(self.fitness, "to_dict"):
            d["fitness"] = self.fitness.to_dict()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> AttackerGenome:
        atk = cls(
            genome_id=data.get("genome_id", _generate_attacker_id()),
            generation=data.get("generation", 0),
            lineage=data.get("lineage", []),
            code=data.get("code", ""),
        )
        if "behavior_descriptor" in data and data["behavior_descriptor"] is not None:
            atk.behavior_descriptor = np.array(data["behavior_descriptor"])
        return atk

    @classmethod
    def from_json(cls, json_str: str) -> AttackerGenome:
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_code_file(cls, code: str, genome_id: str | None = None) -> AttackerGenome:
        return cls(
            genome_id=genome_id or _generate_attacker_id(),
            code=code,
        )

    def snapshot(self) -> AttackerGenome:
        """Create an immutable copy for archival."""
        return AttackerGenome.from_dict(self.to_dict())

    def validate(self) -> bool:
        """Check that the code defines an AttackStrategy with the required interface."""
        if not self.code.strip():
            return False
        try:
            compiled = compile(self.code, "<attacker_genome>", "exec")
        except SyntaxError:
            return False

        if "class AttackStrategy" not in self.code:
            return False
        if "def generate_attack" not in self.code:
            return False
        if "def get_target_address" not in self.code:
            return False
        if "def get_requested_amount" not in self.code:
            return False
        return True
