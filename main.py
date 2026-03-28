"""SIEGE entry point — run the evolutionary experiment."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from src.config import EvolutionConfig
from src.evolution.loop import run_evolution


def main():
    parser = argparse.ArgumentParser(
        description="SIEGE: Self-Improving Evolutionary Guard Experiment"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/fast_test.yaml",
        help="Path to YAML config file (default: config/fast_test.yaml)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Path to checkpoint file or output directory to resume from",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Override output directory from config",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)-30s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = EvolutionConfig.from_yaml(args.config)
    if args.output:
        config.output_dir = args.output

    print(f"SIEGE — Self-Improving Evolutionary Guard Experiment")
    print(f"Config: {args.config}")
    print(f"Output: {config.output_dir}")
    print(f"API base: {config.llm_api_base or '(default OpenAI)'}")
    print(f"API key env: {config.llm_api_key_env}")
    print(f"Populations: {config.bank_pop_size} banks, {config.attacker_pop_size} attackers")
    print(f"Generations: {config.max_generations}")
    print(f"Bootstrap: {config.bootstrap_generations} gens (target {config.bootstrap_target_success_rate:.0%} success)")
    print(f"Bank model: {config.llm_model_bank}")
    print(f"Attacker model: {config.llm_model_attacker}")
    print(f"Mutation model: {config.llm_model_mutation}")
    print()

    asyncio.run(run_evolution(config, resume_from=args.resume))


if __name__ == "__main__":
    main()
