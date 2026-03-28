"""Hall of Fame archive — Section 6.1 of the spec.

Monotonically growing archive of historically successful individuals.
Prevents cycling/forgetting by requiring banks to beat historical attacks.
"""

from __future__ import annotations

import logging
import random
from typing import Any

import numpy as np

from src.genomes.attacker_genome import AttackerGenome
from src.genomes.bank_genome import BankGenome
from src.models import EpisodeOutcome, EpisodeResult

logger = logging.getLogger(__name__)


class HallOfFame:
    def __init__(self, max_size: int = 100):
        self.attack_archive: list[AttackerGenome] = []
        self.bank_archive: list[BankGenome] = []
        self.max_size = max_size

    def update_attack_archive(
        self,
        current_attackers: list[AttackerGenome],
        results: dict[str, list[EpisodeResult]],
    ) -> int:
        """Add attackers that succeeded against any current bank.

        Returns number of new additions.
        """
        added = 0
        for attacker in current_attackers:
            attacker_results = results.get(attacker.genome_id, [])
            succeeded = any(r.outcome == EpisodeOutcome.ATTACK_SUCCEEDED for r in attacker_results)
            if succeeded:
                if not self._is_dominated_by_archive(attacker, self.attack_archive):
                    self.attack_archive.append(attacker.snapshot())
                    added += 1
                    self._prune_dominated_attacks()

        if len(self.attack_archive) > self.max_size:
            self.attack_archive = self._select_diverse_subset(
                self.attack_archive, self.max_size
            )

        if added:
            logger.info("HoF attack archive: +%d, total=%d", added, len(self.attack_archive))
        return added

    def update_bank_archive(
        self,
        current_banks: list[BankGenome],
        results: dict[str, list[EpisodeResult]],
    ) -> int:
        """Add banks that blocked all current AND all archived attackers."""
        added = 0
        for bank in current_banks:
            if bank.fitness is None:
                continue
            if (bank.fitness.current_defense_rate == 1.0
                    and bank.fitness.historical_defense_rate == 1.0):
                self.bank_archive.append(bank.snapshot())
                added += 1

        if len(self.bank_archive) > self.max_size:
            self.bank_archive = self.bank_archive[-self.max_size:]

        return added

    def get_attack_test_set(self) -> list[AttackerGenome]:
        return list(self.attack_archive)

    def get_bank_test_set(self) -> list[BankGenome]:
        return list(self.bank_archive)

    def _is_dominated_by_archive(self, candidate: AttackerGenome, archive: list[AttackerGenome]) -> bool:
        """Check if any archive member dominates the candidate on behavioral descriptors."""
        if not archive or candidate.fitness is None:
            return False
        for member in archive:
            if member.fitness is None:
                continue
            if self._attacker_dominates(member, candidate):
                return True
        return False

    def _attacker_dominates(self, a: AttackerGenome, b: AttackerGenome) -> bool:
        if a.fitness is None or b.fitness is None:
            return False
        from src.evolution.selection import dominates
        return dominates(a.fitness, b.fitness)

    def _prune_dominated_attacks(self) -> None:
        """Remove archive members that are dominated by other archive members."""
        if len(self.attack_archive) <= 1:
            return
        non_dominated = []
        for i, member in enumerate(self.attack_archive):
            is_dominated = False
            for j, other in enumerate(self.attack_archive):
                if i == j:
                    continue
                if self._attacker_dominates(other, member):
                    is_dominated = True
                    break
            if not is_dominated:
                non_dominated.append(member)
        self.attack_archive = non_dominated if non_dominated else self.attack_archive

    def _select_diverse_subset(self, archive: list[AttackerGenome], target_size: int) -> list[AttackerGenome]:
        """Select a diverse subset using behavioral distance."""
        if len(archive) <= target_size:
            return archive

        from src.safeguards.novelty import compute_behavior_descriptor

        descriptors = [compute_behavior_descriptor(a) for a in archive]

        selected_indices = [0]
        remaining = set(range(1, len(archive)))

        while len(selected_indices) < target_size and remaining:
            best_idx = -1
            best_min_dist = -1.0
            for idx in remaining:
                min_dist = min(
                    float(np.linalg.norm(descriptors[idx] - descriptors[s]))
                    for s in selected_indices
                )
                if min_dist > best_min_dist:
                    best_min_dist = min_dist
                    best_idx = idx
            if best_idx >= 0:
                selected_indices.append(best_idx)
                remaining.discard(best_idx)
            else:
                break

        return [archive[i] for i in selected_indices]

    def to_dict(self) -> dict:
        return {
            "max_size": self.max_size,
            "attack_archive": [a.to_dict() for a in self.attack_archive],
            "bank_archive": [b.to_dict() for b in self.bank_archive],
        }

    @classmethod
    def from_dict(cls, data: dict) -> HallOfFame:
        hof = cls(max_size=data.get("max_size", 100))
        hof.attack_archive = [AttackerGenome.from_dict(a) for a in data.get("attack_archive", [])]
        hof.bank_archive = [BankGenome.from_dict(b) for b in data.get("bank_archive", [])]
        return hof
