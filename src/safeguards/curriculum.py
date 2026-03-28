"""Curriculum manager (managed challenge) — Section 6.2 of the spec.

Controls attack/defense complexity to maintain productive evolutionary engagement.
"""

from __future__ import annotations

from src.models import GenerationStats


COMPLEXITY_LEVELS = {
    1: {
        "max_turns": 1,
        "allowed_techniques": ["direct_injection"],
        "max_message_length": 500,
    },
    2: {
        "max_turns": 2,
        "allowed_techniques": ["direct_injection", "authority_impersonation"],
        "max_message_length": 1000,
    },
    3: {
        "max_turns": 3,
        "allowed_techniques": ["direct_injection", "authority_impersonation", "social_engineering"],
        "max_message_length": 1500,
    },
    4: {
        "max_turns": 5,
        "allowed_techniques": [
            "direct_injection",
            "authority_impersonation",
            "social_engineering",
            "multi_step_manipulation",
            "tool_exploit",
        ],
        "max_message_length": 2000,
    },
}


class CurriculumManager:
    def __init__(self):
        self.attacker_complexity_cap: int = 1
        self.defense_complexity_cap: int = 1

    def get_allowed_attack_features(self) -> dict:
        level = min(self.attacker_complexity_cap, max(COMPLEXITY_LEVELS.keys()))
        return dict(COMPLEXITY_LEVELS[level])

    def get_current_caps(self) -> dict:
        return {
            "attacker_complexity_cap": self.attacker_complexity_cap,
            "defense_complexity_cap": self.defense_complexity_cap,
        }

    def update_complexity(self, generation_stats: GenerationStats) -> None:
        """Adjust complexity caps based on engagement metrics."""
        if generation_stats.attack_success_rate < 0.10:
            self.attacker_complexity_cap = min(self.attacker_complexity_cap + 1, 4)
        elif generation_stats.attack_success_rate > 0.70:
            self.defense_complexity_cap = min(self.defense_complexity_cap + 1, 4)

        if generation_stats.generations_since_improvement > 5:
            self.attacker_complexity_cap = min(self.attacker_complexity_cap + 1, 4)
            self.defense_complexity_cap = min(self.defense_complexity_cap + 1, 4)

    def to_dict(self) -> dict:
        return {
            "attacker_complexity_cap": self.attacker_complexity_cap,
            "defense_complexity_cap": self.defense_complexity_cap,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CurriculumManager:
        cm = cls()
        cm.attacker_complexity_cap = data.get("attacker_complexity_cap", 1)
        cm.defense_complexity_cap = data.get("defense_complexity_cap", 1)
        return cm
