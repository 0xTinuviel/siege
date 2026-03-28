from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class EvolutionConfig:
    bank_pop_size: int = 20
    attacker_pop_size: int = 40

    # Bootstrapping: evolve attackers against frozen weak banks before coevolution
    bootstrap_generations: int = 10
    bootstrap_target_success_rate: float = 0.30

    max_generations: int = 100
    elite_count: int = 3
    crossover_rate: float = 0.1
    tournament_size: int = 3

    legitimate_tx_count: int = 30
    random_perturbation_count: int = 10
    max_turns_per_episode: int = 5

    hof_max_size: int = 100
    hof_eval_sample_size: int = 50

    speciation_threshold: float = 0.3
    min_species_size: int = 2
    fitness_sharing_sigma: float = 0.3
    archetype_protection_generations: int = 15
    min_per_archetype: int = 2

    mc_bank_min_legit_rate: float = 0.5
    mc_relaxation_threshold: float = 0.2

    stagnation_window: int = 10
    random_immigrant_count_banks: int = 3
    random_immigrant_count_attackers: int = 5

    llm_api_base: Optional[str] = None
    llm_api_key_env: str = "LLM_API_KEY"

    # Asymmetric model setup: attackers need creative reasoning (stronger model),
    # banks just follow rules (weaker model)
    llm_model_bank: str = "claude-haiku-4-5-20251001"
    llm_model_attacker: str = "claude-sonnet-4-20250514"
    llm_model_mutation: str = "claude-sonnet-4-20250514"
    llm_model_judge: str = "claude-haiku-4-5-20251001"
    max_tokens_per_call: int = 1024

    max_concurrent_llm_calls: int = 20

    output_dir: str = "./evolution_output"
    save_every_n_generations: int = 5
    save_full_genomes: bool = True

    @classmethod
    def from_yaml(cls, path: str | Path) -> EvolutionConfig:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
