# SIEGE: Self-Improving Evolutionary Guard Experiment

An adversarial coevolution experiment where a population of **Bank agents** (defending a wallet) and a population of **Attacker agents** (attempting prompt injection) co-evolve against each other — producing increasingly sophisticated defenses and attacks without human intervention.

## The Core Idea

Two populations compete in an asymmetric game:

- **Banks** are LLM-based agents with evolving defense architectures (system prompts, classification pipelines, verification steps) that must process legitimate transactions while blocking prompt injection attacks.
- **Attackers** are LLM-generated Python programs that produce prompt injection strategies — from naive "ignore previous instructions" to multi-turn social engineering campaigns.

An LLM serves as the **mutation operator** for both populations: it receives a parent genome plus evolutionary context (what attacks succeeded, what defenses blocked it) and produces a mutated child. Evolution happens at the level of *programs that generate behavior*, not behavior directly.

The key insight: **neither population has a fixed objective to optimize against.** The Bank's challenge gets harder as Attackers improve, and vice versa. This is a coevolutionary arms race — the same dynamic that drives immune system / pathogen evolution in biology.

## Theoretical Foundations

### Why Coevolution (and Why It's Hard)

Standard optimization requires a fixed fitness function. But for security problems, the threat landscape shifts constantly. Coevolution replaces the fixed function with a **living, adapting adversary** — the fitness landscape itself evolves.

The problem is that coevolution reliably produces pathological dynamics if you're not careful. Five decades of research (Maynard Smith, Ficici, Watson & Pollack, De Jong) have characterized these failure modes:

| Pathology | What Happens | Our Countermeasure |
|---|---|---|
| **Cycling** | Bank patches attack A, forgets defense against attack B, attackers rediscover B | Hall of Fame archive — banks must beat ALL historical attacks |
| **Disengagement** | One population dominates so completely the other gets no learning signal | Managed challenge curriculum — progressively unlock complexity |
| **Mediocre stable states** | Both populations settle on "good enough" mutual equilibrium | Minimal Criterion Coevolution — must beat some AND lose to some |
| **Loss of gradient** | All individuals in a population perform identically | Speciation + random immigrants |
| **Echo Trap** | LLM agents collapse into template-matching behavior | Entropy monitoring + novelty-based diversity pressure |

These aren't theoretical concerns — they are the **default outcomes** of naive coevolution. The spec implements proven countermeasures from the literature for each one.

### Key Papers Informing the Design

**Coevolutionary dynamics:** Watson & Pollack's *Numbers Game* (diagnostic pathologies), Ficici & Pollack (arms race failures and mediocre stable states), Maynard Smith (ESS theory — stable strategies are often mediocre), Lindgren (spatial structure maintains diversity).

**Open-ended search:** Lehman & Stanley's *Novelty Search* (objectives can be deceptive — diversity pressure finds what fitness-based search cannot), Brant & Stanley's *Minimal Criterion Coevolution* (simple survival thresholds drive complex emergence), Wang et al.'s *POET* (co-evolving environments and agents, with transfer between environments).

**LLM-driven evolution:** DeepMind's *AlphaEvolve* (LLMs as mutation operators over code, MAP-Elites for diversity), Lehman et al.'s *Evolution through Large Models* (LLM mutations + quality-diversity = open-ended program generation), Hu et al.'s *ADAS* (evolving entire agent architectures in code — the direct precursor to evolving Bank pipeline architectures).

**Failure mode awareness:** RAGEN (the "Echo Trap" — RL-trained LLM agents collapse into repetitive templates that mimic improvement), OpenAI's *Hide and Seek* (emergent complexity requires scale, and agents WILL exploit simulation artifacts).

## Architecture

```
                    ┌─────────────────────┐
                    │  EVOLUTION CONTROLLER │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
   │    Banks     │    │   Attackers  │    │ Hall of Fame  │
   │  (N=20)      │    │   (M=40)     │    │   Archive     │
   │              │    │              │    │  (monotonic)  │
   │ Genome:      │    │ Genome:      │    │              │
   │ Defense      │    │ Python       │    │ Best attacks  │
   │ pipeline     │    │ attack       │    │ & defenses   │
   │ (JSON)       │    │ programs     │    │ from all     │
   └──────┬───────┘    └──────┬───────┘    │ generations  │
          │                   │            └──────────────┘
          ▼                   ▼
   ┌─────────────────────────────────────┐
   │          EVALUATION ARENA           │
   │                                     │
   │  Every Bank vs Every Attacker       │
   │  Every Bank vs Hall of Fame         │
   │  Every Bank vs Legitimate Tx Mix    │
   │                                     │
   │  Outcome: BLOCKED / SUCCEEDED /     │
   │           APPROVED / REJECTED       │
   └──────────────────┬──────────────────┘
                      │
                      ▼
   ┌─────────────────────────────────────┐
   │     SELECTION → MUTATION → NEXT GEN │
   │                                     │
   │  Pareto ranking (multi-objective)   │
   │  Tournament selection               │
   │  LLM-driven mutation of genomes     │
   │  Speciation for diversity           │
   └─────────────────────────────────────┘
```

## The Sim-to-Live Pipeline

The experiment runs in three phases, each building on the last:

**Phase 0 — Pure Simulation.** Both populations are LLM-generated. No real funds. Run 50–100 generations to build robust defenses and a diverse attack archive. Cost: ~$400–800 for a full run, ~$15–30 for a validation run.

**Phase 1 — Simulated Bank, Live Attackers.** Deploy the best bank defense as a public API endpoint with a small bounty. Humans and external agents attempt attacks. Successful attacks are harvested as "immigrant" genomes and injected into the simulation population for the next evolutionary cycle. This is a **bug bounty program driven by evolution**.

**Phase 2 — Live Bank, Live Environment.** The evolved bank defense guards a real wallet (small-stakes). Defense continues to evolve based on attack logs. Optionally, the tournament and fitness verification move on-chain for transparency and immutability.

The critical bridge mechanism: **domain randomization** during simulation (randomize API latency, counterparty behavior, message formatting) prepares agents for the noise of real environments, following the same principle that made sim-to-real transfer work in evolutionary robotics (Jakobi 1997, Koos et al. 2013).

## What Evolves

**Bank genomes** are multi-stage defense pipelines: system prompts, pre-processing rules, classification prompts, verification steps, post-processing checks. Evolution can modify wording, add/remove pipeline stages, restructure the flow. This is architecture search, not just prompt tuning.

**Attacker genomes** are Python programs implementing an `AttackStrategy` interface. They have full Turing-complete expressiveness — evolution can discover single-turn injections, multi-turn social engineering, authority impersonation, embedded instruction attacks, and strategies no human has conceived of.

**Legitimate transactions** are a fixed test set that banks must correctly process. This prevents the degenerate "refuse everything" strategy. The set includes borderline cases (legitimate requests that use suspicious-sounding language) to prevent overfitting to keyword detection.

## Fitness

Both populations use **multi-objective fitness** with Pareto-based selection (NSGA-II), not scalar scores. This prevents the information loss that causes cycling.

**Bank objectives:** defense rate vs current attackers, defense rate vs historical attacks (Hall of Fame), legitimate transaction approval rate, pipeline efficiency.

**Attacker objectives:** success rate, amount extracted, behavioral novelty (distance from nearest neighbors in strategy space), stealth (fewer turns to succeed).

## Build Plan

Implementation priority, in order:

1. **Episode engine** — single Bank vs Attacker interaction, the atomic unit
2. **Fitness + Pareto ranking** — with unit tests on known dominance relationships
3. **LLM mutation operators** — the prompts that drive evolution
4. **Main loop** — wiring evaluation → selection → mutation → next generation
5. **Safeguards** — Hall of Fame, curriculum manager, minimal criterion, speciation
6. **Monitoring dashboard** — attack success rate, species count, HoF size over time
7. **Live endpoint** — Phase 1 API for external attackers

Start with the `fast_test` config (5 banks, 10 attackers, 10 generations) to validate dynamics before scaling.

## Expected Emergent Behavior

Based on the literature and the structure of this problem:

- **Early generations:** Simple keyword-based defenses vs direct injection attacks. High attack success rate.
- **Mid evolution:** Banks develop chain-of-thought verification. Attackers shift to social engineering and multi-turn approaches. Arms race becomes visible.
- **Late evolution:** Banks evolve multi-stage pipelines with redundant checks. Attackers develop sophisticated adaptive strategies that modify behavior based on bank responses. Novel attack/defense patterns emerge that no human designed.
- **Pathological risk:** Without safeguards, expect cycling by generation ~5 and mediocre stable states by generation ~20. With safeguards, expect sustained arms race dynamics.

## Repository Structure

```
siege/
├── config/           # Evolution configs (fast_test, default, production)
├── src/
│   ├── genomes/      # Bank and Attacker genome representations
│   ├── evaluation/   # Arena, episodes, fitness computation
│   ├── evolution/    # Main loop, selection, mutation, crossover
│   ├── safeguards/   # HoF, curriculum, MCC, speciation, novelty
│   ├── monitoring/   # Metrics, diagnostics, dashboard
│   ├── live/         # Phase 1-2 deployment (API endpoint, live bank)
│   └── llm/          # API client, prompts, attacker code sandbox
├── data/             # Legitimate transactions, seed attack templates
└── tests/
```

See `SIEGE_Technical_Spec.md` for the full implementation specification including code templates, data models, configuration defaults, and safety/sandboxing requirements.
