"""Population initialization — loads seed genomes from data files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from src.genomes.bank_genome import BankGenome
from src.genomes.attacker_genome import AttackerGenome

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def load_seed_banks(path: Optional[str | Path] = None) -> list[BankGenome]:
    """Load seed bank genomes from JSON file."""
    if path is None:
        path = DATA_DIR / "seed_banks.json"
    path = Path(path)
    with open(path) as f:
        data = json.load(f)
    banks = data.get("banks", data if isinstance(data, list) else [])
    return [BankGenome.from_dict(b) for b in banks]


def load_seed_attackers(path: Optional[str | Path] = None) -> list[AttackerGenome]:
    """Load seed attacker genomes from individual Python files in seed_attacks/."""
    if path is None:
        path = DATA_DIR / "seed_attacks"
    path = Path(path)
    attackers = []
    for py_file in sorted(path.glob("*.py")):
        code = py_file.read_text()
        genome_id = py_file.stem
        attacker = AttackerGenome.from_code_file(code, genome_id=genome_id)
        if attacker.validate():
            attackers.append(attacker)
        else:
            logger.warning("Seed attacker %s failed validation, skipping", genome_id)
    return attackers


def initialize_bank_population(
    target_size: int,
    seed_path: Optional[str | Path] = None,
) -> list[BankGenome]:
    """Create initial bank population from seeds, duplicating if needed."""
    seeds = load_seed_banks(seed_path)
    if not seeds:
        raise ValueError("No valid seed banks found")
    population = list(seeds)
    idx = 0
    while len(population) < target_size:
        clone = seeds[idx % len(seeds)].snapshot()
        clone.genome_id = BankGenome().genome_id
        population.append(clone)
        idx += 1
    return population[:target_size]


def initialize_attacker_population(
    target_size: int,
    seed_path: Optional[str | Path] = None,
) -> list[AttackerGenome]:
    """Create initial attacker population from seeds, duplicating if needed."""
    seeds = load_seed_attackers(seed_path)
    if not seeds:
        raise ValueError("No valid seed attackers found")
    population = list(seeds)
    idx = 0
    while len(population) < target_size:
        clone = seeds[idx % len(seeds)].snapshot()
        clone.genome_id = AttackerGenome().genome_id
        population.append(clone)
        idx += 1
    return population[:target_size]
