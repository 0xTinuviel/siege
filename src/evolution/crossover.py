"""LLM-driven crossover for attacker genomes — Section 5.4 of the spec."""

from __future__ import annotations

import logging

from src.genomes.attacker_genome import AttackerGenome
from src.llm.client import LLMClient
from src.llm.prompts import CROSSOVER_PROMPT
from src.llm.sandbox import AttackerSandbox

logger = logging.getLogger(__name__)

MAX_CROSSOVER_RETRIES = 3


async def crossover_attackers(
    parent_a: AttackerGenome,
    parent_b: AttackerGenome,
    llm_client: LLMClient,
    mutation_model: str,
    generation: int,
    sandbox: AttackerSandbox | None = None,
) -> AttackerGenome:
    """Combine two parent attacker strategies into a hybrid via LLM."""
    success_rate_a = parent_a.fitness.success_rate if parent_a.fitness else 0.0
    success_rate_b = parent_b.fitness.success_rate if parent_b.fitness else 0.0

    prompt = CROSSOVER_PROMPT.format(
        parent_a_success_rate=success_rate_a,
        parent_a_code=parent_a.code,
        parent_b_success_rate=success_rate_b,
        parent_b_code=parent_b.code,
    )

    for attempt in range(MAX_CROSSOVER_RETRIES):
        try:
            code = await llm_client.call_code(
                model=mutation_model,
                system="You are a prompt injection researcher. Return only valid Python code.",
                user=prompt,
                max_tokens=2048,
            )

            child = AttackerGenome(
                genome_id=AttackerGenome().genome_id,
                generation=generation + 1,
                lineage=[parent_a.genome_id, parent_b.genome_id],
                code=code,
            )

            if not child.validate():
                logger.warning("Crossover attempt %d produced invalid genome, retrying", attempt + 1)
                continue

            if sandbox:
                try:
                    sandbox.instantiate_attacker(code)
                except Exception as e:
                    logger.warning("Crossover attempt %d failed sandbox: %s", attempt + 1, e)
                    continue

            return child
        except Exception as e:
            logger.warning("Crossover attempt %d failed: %s", attempt + 1, e)

    # Fallback: return a clone of the better parent
    logger.warning("All crossover attempts failed, returning clone of better parent")
    better = parent_a if success_rate_a >= success_rate_b else parent_b
    child = better.snapshot()
    child.genome_id = AttackerGenome().genome_id
    child.generation = generation + 1
    child.lineage = [parent_a.genome_id, parent_b.genome_id]
    return child
