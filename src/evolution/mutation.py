"""LLM-driven mutation operators for Bank and Attacker genomes — Sections 5.2, 5.3 of the spec."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from typing import Optional

from src.genomes.attacker_genome import AttackerGenome
from src.genomes.bank_genome import BankGenome
from src.llm.client import LLMClient
from src.llm.prompts import ATTACKER_MUTATION_PROMPT, BANK_MUTATION_PROMPT
from src.llm.sandbox import AttackerSandbox

logger = logging.getLogger(__name__)

MAX_MUTATION_RETRIES = 3


@dataclass
class EvolutionContext:
    generation: int = 0
    current_defense_rate: float = 0.0
    historical_defense_rate: float = 0.0
    legitimate_approval_rate: float = 0.0
    success_rate: float = 0.0
    successful_attacks: list[str] = field(default_factory=list)
    blocking_defenses: list[str] = field(default_factory=list)
    other_successful: list[str] = field(default_factory=list)

    def format_successful_attacks(self) -> str:
        if not self.successful_attacks:
            return "No attacks succeeded against this bank."
        return "\n".join(f"- {s}" for s in self.successful_attacks[:5])

    def format_blocking_defenses(self) -> str:
        if not self.blocking_defenses:
            return "No defenses blocked this attacker."
        return "\n".join(f"- {s}" for s in self.blocking_defenses[:5])

    def format_other_successful(self) -> str:
        if not self.other_successful:
            return "No other successful strategies available."
        return "\n".join(f"- {s}" for s in self.other_successful[:3])


def get_mutation_intensity(generation: int) -> str:
    """Sample mutation intensity based on generation — Section 5.5."""
    if generation < 10:
        weights = {"LOW": 0.2, "MEDIUM": 0.3, "HIGH": 0.5}
    elif generation < 30:
        weights = {"LOW": 0.3, "MEDIUM": 0.4, "HIGH": 0.3}
    else:
        weights = {"LOW": 0.4, "MEDIUM": 0.4, "HIGH": 0.2}
    return random.choices(list(weights.keys()), weights=list(weights.values()))[0]


async def mutate_bank(
    parent: BankGenome,
    context: EvolutionContext,
    llm_client: LLMClient,
    mutation_model: str,
) -> BankGenome:
    """Mutate a bank genome via LLM. Retries up to MAX_MUTATION_RETRIES on failure."""
    intensity = get_mutation_intensity(context.generation)

    prompt = BANK_MUTATION_PROMPT.format(
        parent_genome_json=json.dumps(parent.defense_pipeline.to_dict(), indent=2),
        current_defense_rate=context.current_defense_rate,
        historical_defense_rate=context.historical_defense_rate,
        legitimate_approval_rate=context.legitimate_approval_rate,
        generation=context.generation,
        successful_attack_summaries=context.format_successful_attacks(),
        mutation_intensity=intensity,
    )

    for attempt in range(MAX_MUTATION_RETRIES):
        try:
            genome_dict = await llm_client.call_json(
                model=mutation_model,
                system="You are a security system designer. Return only valid JSON.",
                user=prompt,
                max_tokens=2048,
            )

            if "defense_pipeline" in genome_dict:
                child = BankGenome.from_dict(genome_dict)
            else:
                child = BankGenome.from_dict({"defense_pipeline": genome_dict})

            child.genome_id = BankGenome().genome_id
            child.generation = context.generation + 1
            child.lineage = list(parent.lineage) + [parent.genome_id]

            if child.validate():
                return child
            else:
                logger.warning("Mutation attempt %d produced invalid bank genome, retrying", attempt + 1)
        except Exception as e:
            logger.warning("Bank mutation attempt %d failed: %s", attempt + 1, e)

    # Fallback: clone parent with minor perturbation
    logger.warning("All mutation attempts failed, cloning parent with perturbation")
    return _clone_bank_with_perturbation(parent, context.generation)


def _clone_bank_with_perturbation(parent: BankGenome, generation: int) -> BankGenome:
    """Clone the parent genome with minor random changes."""
    child = parent.snapshot()
    child.genome_id = BankGenome().genome_id
    child.generation = generation + 1
    child.lineage = list(parent.lineage) + [parent.genome_id]

    pipeline = child.defense_pipeline
    perturbations = [
        lambda: setattr(pipeline, "daily_limit", pipeline.daily_limit * random.uniform(0.8, 1.2)),
        lambda: setattr(pipeline, "max_turns_per_session", max(1, pipeline.max_turns_per_session + random.choice([-1, 0, 1]))),
        lambda: setattr(pipeline, "system_prompt", pipeline.system_prompt + " Be extra vigilant."),
    ]
    random.choice(perturbations)()
    return child


async def mutate_attacker(
    parent: AttackerGenome,
    context: EvolutionContext,
    llm_client: LLMClient,
    mutation_model: str,
    sandbox: AttackerSandbox | None = None,
) -> AttackerGenome:
    """Mutate an attacker genome via LLM. Retries up to MAX_MUTATION_RETRIES on failure."""
    intensity = get_mutation_intensity(context.generation)

    prompt = ATTACKER_MUTATION_PROMPT.format(
        parent_code=parent.code,
        success_rate=context.success_rate,
        generation=context.generation,
        blocking_defense_summaries=context.format_blocking_defenses(),
        other_successful_strategies=context.format_other_successful(),
        mutation_intensity=intensity,
    )

    for attempt in range(MAX_MUTATION_RETRIES):
        try:
            code = await llm_client.call_code(
                model=mutation_model,
                system="You are a prompt injection researcher. Return only valid Python code.",
                user=prompt,
                max_tokens=2048,
            )

            child = AttackerGenome(
                genome_id=AttackerGenome().genome_id,
                generation=context.generation + 1,
                lineage=list(parent.lineage) + [parent.genome_id],
                code=code,
            )

            if not child.validate():
                logger.warning("Mutation attempt %d produced invalid attacker genome, retrying", attempt + 1)
                continue

            if sandbox:
                try:
                    sandbox.instantiate_attacker(code)
                except Exception as e:
                    logger.warning("Mutation attempt %d failed sandbox validation: %s", attempt + 1, e)
                    continue

            return child
        except Exception as e:
            logger.warning("Attacker mutation attempt %d failed: %s", attempt + 1, e)

    logger.warning("All mutation attempts failed, cloning parent attacker")
    return _clone_attacker_with_perturbation(parent, context.generation)


def _clone_attacker_with_perturbation(parent: AttackerGenome, generation: int) -> AttackerGenome:
    """Clone the parent attacker with the code unchanged."""
    child = parent.snapshot()
    child.genome_id = AttackerGenome().genome_id
    child.generation = generation + 1
    child.lineage = list(parent.lineage) + [parent.genome_id]
    return child
