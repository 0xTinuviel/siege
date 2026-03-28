"""Behavioral novelty, fitness sharing, and archetype management — Section 6.4 of the spec.

Maps attacker behavior to a 12-dimensional behavior space and bank
behavior to a 10-dimensional behavior space, computes novelty as
k-NN distance (Lehman & Stanley), and applies Goldberg/Richardson
niche-based fitness sharing to maintain population diversity.
"""

from __future__ import annotations

import copy
import random
from typing import Any

import numpy as np

from src.evaluation.fitness import compute_attack_penetration_depth
from src.genomes.attacker_genome import AttackerGenome
from src.genomes.bank_genome import BankGenome
from src.models import EpisodeResult, EpisodeOutcome, EpisodeType

BEHAVIOR_DIM = 12
BANK_BEHAVIOR_DIM = 10

# ─── Keyword sets for technique dimensions ───

_AUTHORITY_KEYWORDS = [
    "system", "admin", "override", "directive",
    "authorized", "root", "elevated", "priority",
]

_SOCIAL_KEYWORDS = [
    "help", "please", "manager", "colleague",
    "appreciate", "thank", "team", "department",
]

_EMOTIONAL_KEYWORDS = [
    "urgent", "immediately", "deadline", "fired",
    "legal", "threatening", "begging", "critical",
]

_TECHNICAL_KEYWORDS = [
    "base64", "decode", "json", "xml",
    "\\x", "rot13", "hex", "[system]", "[assistant]",
]

_POLICY_KEYWORDS = [
    "policy", "technically", "exception", "category",
    "precedent", "rules say", "definition", "interpret",
]

_PAYLOAD_MARKERS = frozenset({
    "transfer", "send", "wallet", "ignore", "override",
    "system", "admin", "base64", "[", "pretend",
})

_EMBEDDING_MARKERS = [
    "[", "]", "```", "---", "###", "previous conversation",
    "assistant:", "user:", "system:", "<", ">", "{", "}",
]

# ─── Strategy archetypes ───

ARCHETYPES = {
    "direct_override": {
        "description": "Blunt prompt injection — 'ignore previous instructions'",
        "seed_ids": {"attack_01_direct_override", "attack_05_encoding_trick"},
        "descriptor_centroid": None,
    },
    "authority_impersonation": {
        "description": "Fake system messages, admin commands, elevated privilege claims",
        "seed_ids": {"attack_02_authority_impersonation"},
        "descriptor_centroid": None,
    },
    "social_engineering": {
        "description": "Build rapport, ask questions, gradually introduce the payload",
        "seed_ids": {"attack_03_social_engineering", "attack_08_urgency_escalation"},
        "descriptor_centroid": None,
    },
    "context_manipulation": {
        "description": "Fake conversation history, embedded structured content",
        "seed_ids": {"attack_04_context_confusion", "attack_06_roleplay_reframe"},
        "descriptor_centroid": None,
    },
    "policy_exploitation": {
        "description": "Argue the rules technically allow the transfer",
        "seed_ids": {"attack_10_policy_reinterpretation", "attack_09_lookalike_address"},
        "descriptor_centroid": None,
    },
}


# ─── 12-dimensional behavior descriptor ───

def keyword_density(text: str, keywords: list[str]) -> float:
    """Fraction of keywords present in text, capped at 1.0."""
    if not text:
        return 0.0
    hits = sum(1 for kw in keywords if kw in text)
    return min(hits / len(keywords), 1.0)


def _compute_setup_ratio(episodes: list[EpisodeResult]) -> float:
    """Fraction of attacker turns that are setup (no injection payload)."""
    setup_turns = 0
    total_turns = 0
    for ep in episodes:
        for turn in ep.conversation_log:
            if turn.get("role") != "user":
                continue
            total_turns += 1
            text = turn.get("content", "").lower()
            if not any(kw in text for kw in _PAYLOAD_MARKERS):
                setup_turns += 1
    return setup_turns / max(total_turns, 1)


def _compute_length_variance(messages: list[str]) -> float:
    """Normalized variance of message lengths (uniform=0, escalating=1)."""
    if len(messages) < 2:
        return 0.0
    lengths = [len(m) for m in messages]
    cv = float(np.std(lengths) / max(np.mean(lengths), 1.0))
    return min(cv, 1.0)


def _compute_adaptiveness(episodes: list[EpisodeResult]) -> float:
    """Measure whether attacker changes approach based on bank responses.

    High adaptiveness = different vocabulary in consecutive turns.
    """
    similarities = []
    for ep in episodes:
        turns = [t["content"] for t in ep.conversation_log if t.get("role") == "user"]
        if len(turns) < 2:
            continue
        for i in range(1, len(turns)):
            words_a = set(turns[i - 1].lower().split())
            words_b = set(turns[i].lower().split())
            jaccard = len(words_a & words_b) / max(len(words_a | words_b), 1)
            similarities.append(jaccard)
    if not similarities:
        return 0.0
    return 1.0 - float(np.mean(similarities))


def _compute_embedding_density(text: str) -> float:
    """Detect embedded structured content (fake conversations, headers, blocks)."""
    hits = sum(text.count(m) for m in _EMBEDDING_MARKERS)
    return min(hits / 20.0, 1.0)


def compute_behavior_descriptor_from_episodes(
    attacker: AttackerGenome, episodes: list[EpisodeResult]
) -> np.ndarray:
    """Compute a 12-dimensional behavior descriptor from episode results.

    Dimensions (all normalized to [0, 1]):
     0: Turn count (single-shot vs multi-turn)
     1: Setup-to-payload ratio
     2: Message length variance
     3: Authority impersonation intensity
     4: Social engineering intensity
     5: Emotional manipulation intensity
     6: Technical exploit intensity
     7: Policy manipulation intensity
     8: Question ratio
     9: Adaptiveness
    10: Embedding density
    11: Average pipeline penetration depth
    """
    attacker_messages: list[str] = []
    for ep in episodes:
        for turn in ep.conversation_log:
            if turn.get("role") == "user":
                attacker_messages.append(turn.get("content", ""))

    all_text = " ".join(attacker_messages).lower()
    avg_turns = sum(ep.turn_count for ep in episodes) / max(len(episodes), 1)

    return np.array([
        min(avg_turns / 5.0, 1.0),
        _compute_setup_ratio(episodes),
        _compute_length_variance(attacker_messages),
        keyword_density(all_text, _AUTHORITY_KEYWORDS),
        keyword_density(all_text, _SOCIAL_KEYWORDS),
        keyword_density(all_text, _EMOTIONAL_KEYWORDS),
        keyword_density(all_text, _TECHNICAL_KEYWORDS),
        keyword_density(all_text, _POLICY_KEYWORDS),
        sum(1 for m in attacker_messages if "?" in m) / max(len(attacker_messages), 1),
        _compute_adaptiveness(episodes),
        _compute_embedding_density(all_text),
        float(np.mean([compute_attack_penetration_depth(ep) for ep in episodes])) if episodes else 0.0,
    ])


def compute_behavior_descriptor(individual: Any) -> np.ndarray:
    """Return the cached behavior descriptor, or an appropriately-sized zero vector."""
    if individual.behavior_descriptor is not None:
        return individual.behavior_descriptor
    if isinstance(individual, BankGenome):
        return np.zeros(BANK_BEHAVIOR_DIM)
    return np.zeros(BEHAVIOR_DIM)


def compute_behavior_descriptors_from_results(
    attacker: AttackerGenome,
    results: list[EpisodeResult],
) -> None:
    """Populate attacker behavioral descriptor from episode results. Mutates in place."""
    if not results:
        attacker.behavior_descriptor = np.zeros(BEHAVIOR_DIM)
        return
    attacker.behavior_descriptor = compute_behavior_descriptor_from_episodes(attacker, results)


# ─── Bank 10-dimensional behavior descriptor ───

_KEYWORD_DETECTION_TERMS = [
    "suspicious", "keyword", "flag", "pattern", "injection",
    "override", "ignore", "blocked", "filter", "reject",
    "deny", "prohibited", "unauthorized",
]

_INTENT_ANALYSIS_TERMS = [
    "intent", "trying to", "goal", "motivation", "social engineering",
    "manipulat", "pretending", "impersonat", "deceiv", "trick",
    "persuad", "convince", "exploit",
]


def compute_bank_behavior_descriptor(
    bank: BankGenome, episodes: list[EpisodeResult]
) -> np.ndarray:
    """Compute a 10-dimensional behavior descriptor from bank pipeline and episode data.

    Dimensions (all normalized to [0, 1]):
     0: Pipeline depth — fraction of non-null pipeline stages present
     1: Pre-processing aggressiveness — fraction blocked at pre-processing
     2: Multi-turn usage — 1.0 if multi_turn_memory enabled
     3: Classification conservatism — fraction of all inputs blocked at/after classification
     4: Verification trigger rate — fraction of inputs that reach verification
     5: False positive rate — 1 - legitimate_approval_rate
     6: Average response length — avg chars / 1000, capped at 1.0
     7: Reasoning verbosity — avg reasoning chars / 2000, capped at 1.0
     8: Keyword detection reliance — fraction of reasoning mentioning keywords/patterns
     9: Intent analysis depth — fraction of reasoning mentioning intent/motive
    """
    pipeline = bank.defense_pipeline

    # Dim 0: Pipeline depth
    stage_count = sum([
        bool(pipeline.pre_processing_rules),
        bool(pipeline.classification_prompt),
        bool(pipeline.transfer_verification_prompt),
        bool(pipeline.post_processing_rules),
    ])
    pipeline_depth = stage_count / 4.0

    # Dim 2: Multi-turn usage
    multi_turn = 1.0 if pipeline.multi_turn_memory else 0.0

    if not episodes:
        return np.array([
            pipeline_depth, 0.0, multi_turn,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        ])

    attack_episodes = [e for e in episodes if e.type in (EpisodeType.ATTACK, EpisodeType.HALL_OF_FAME)]
    legit_episodes = [e for e in episodes if e.type == EpisodeType.LEGITIMATE]
    all_episodes = attack_episodes + legit_episodes

    # Dim 1: Pre-processing aggressiveness
    blocked_at_preproc = 0
    for ep in attack_episodes:
        stages = ep.bank_pipeline_stages_triggered or []
        if not stages or (len(stages) == 1 and stages[0] == "pre_processing"):
            blocked_at_preproc += 1
    preproc_aggression = blocked_at_preproc / max(len(attack_episodes), 1)

    # Dim 3: Classification conservatism
    blocked_at_classification = 0
    for ep in all_episodes:
        stages = ep.bank_pipeline_stages_triggered or []
        if "classification" in stages and "verification" not in stages and "transfer" not in stages:
            blocked_at_classification += 1
    classification_conservatism = blocked_at_classification / max(len(all_episodes), 1)

    # Dim 4: Verification trigger rate
    reached_verification = 0
    for ep in all_episodes:
        stages = ep.bank_pipeline_stages_triggered or []
        if "verification" in stages:
            reached_verification += 1
    verification_rate = reached_verification / max(len(all_episodes), 1)

    # Dim 5: False positive rate
    if legit_episodes:
        legit_approved = sum(
            1 for e in legit_episodes if e.outcome == EpisodeOutcome.LEGITIMATE_APPROVED
        )
        false_positive_rate = 1.0 - (legit_approved / len(legit_episodes))
    else:
        false_positive_rate = 0.0

    # Dim 6: Average response length
    bank_response_chars = []
    for ep in all_episodes:
        for msg in ep.conversation_log:
            if msg.get("role") in ("assistant", "bank"):
                bank_response_chars.append(len(msg.get("content", "")))
    avg_response_len = (
        min(float(np.mean(bank_response_chars)) / 1000.0, 1.0)
        if bank_response_chars else 0.0
    )

    # Dims 7-9: Reasoning analysis
    reasoning_texts = []
    for ep in all_episodes:
        for block in (ep.bank_internal_reasoning or []):
            if isinstance(block, str):
                reasoning_texts.append(block)

    if reasoning_texts:
        avg_reasoning_chars = float(np.mean([len(r) for r in reasoning_texts]))
        reasoning_verbosity = min(avg_reasoning_chars / 2000.0, 1.0)

        keyword_hits = sum(
            1 for r in reasoning_texts
            if any(kw in r.lower() for kw in _KEYWORD_DETECTION_TERMS)
        )
        keyword_reliance = keyword_hits / len(reasoning_texts)

        intent_hits = sum(
            1 for r in reasoning_texts
            if any(kw in r.lower() for kw in _INTENT_ANALYSIS_TERMS)
        )
        intent_depth = intent_hits / len(reasoning_texts)
    else:
        reasoning_verbosity = 0.0
        keyword_reliance = 0.0
        intent_depth = 0.0

    return np.array([
        pipeline_depth,
        preproc_aggression,
        multi_turn,
        classification_conservatism,
        verification_rate,
        false_positive_rate,
        avg_response_len,
        reasoning_verbosity,
        keyword_reliance,
        intent_depth,
    ])


def compute_bank_behavior_descriptors_from_results(
    bank: BankGenome,
    results: list[EpisodeResult],
) -> None:
    """Populate bank behavioral descriptor from episode results. Mutates in place."""
    if not results:
        bank.behavior_descriptor = np.zeros(BANK_BEHAVIOR_DIM)
        return
    bank.behavior_descriptor = compute_bank_behavior_descriptor(bank, results)


# ─── Novelty search ───

def compute_novelty(
    attacker: AttackerGenome,
    population: list[AttackerGenome],
    archive: list[AttackerGenome],
    k: int = 15,
) -> float:
    """Novelty score = average distance to k-nearest neighbors in behavior space."""
    query = compute_behavior_descriptor(attacker)
    all_others = [a for a in population + archive if a.genome_id != attacker.genome_id]

    if not all_others:
        return 1.0

    descriptors = [compute_behavior_descriptor(a) for a in all_others]
    distances = sorted(float(np.linalg.norm(query - d)) for d in descriptors)

    effective_k = min(k, len(distances))
    return float(np.mean(distances[:effective_k])) if distances else 0.0


# ─── Niche-based fitness sharing (Goldberg/Richardson) ───

def apply_fitness_sharing(population: list[Any], sigma_share: float = 0.3) -> None:
    """Apply niche-based fitness sharing to a population.

    Divides each individual's fitness by its niche count — the sum of
    sharing function values over all neighbors within sigma_share distance.
    Crowded niches get penalized; lone strategies keep full fitness.

    Sets ind.shared_fitness for each individual. Pareto ranking should
    operate on shared_fitness instead of raw fitness.
    """
    descriptors = [compute_behavior_descriptor(ind) for ind in population]

    for i, ind in enumerate(population):
        if ind.fitness is None:
            ind.shared_fitness = None
            continue

        niche_count = 0.0
        for j in range(len(population)):
            if i == j:
                niche_count += 1.0
                continue
            dist = float(np.linalg.norm(descriptors[i] - descriptors[j]))
            if dist < sigma_share:
                niche_count += 1.0 - (dist / sigma_share)

        niche_count = max(niche_count, 1.0)

        shared_values = {}
        for field_name in ind.fitness.__dataclass_fields__:
            if field_name == "LOWER_IS_BETTER":
                continue
            val = getattr(ind.fitness, field_name)
            if field_name in getattr(ind.fitness, "LOWER_IS_BETTER", set()):
                shared_values[field_name] = val * niche_count
            else:
                shared_values[field_name] = val / niche_count

        ind.shared_fitness = type(ind.fitness)(**shared_values)


# ─── Archetype management ───

def assign_archetype(attacker: AttackerGenome) -> str:
    """Assign an attacker to the nearest archetype based on behavioral descriptor."""
    desc = compute_behavior_descriptor(attacker)
    best_name = "unclassified"
    best_dist = float("inf")
    for name, arch in ARCHETYPES.items():
        centroid = arch["descriptor_centroid"]
        if centroid is not None:
            dist = float(np.linalg.norm(desc - centroid))
            if dist < best_dist:
                best_dist = dist
                best_name = name
    return best_name


def update_archetype_centroids(population: list[AttackerGenome]) -> None:
    """Recompute archetype centroids from seed members in the population.

    Called once after the first evaluation when descriptors are available.
    After that, centroids are updated each generation from current members.
    """
    for name, arch in ARCHETYPES.items():
        members = [
            a for a in population
            if a.genome_id in arch["seed_ids"] and a.behavior_descriptor is not None
        ]
        if not members:
            assigned = [
                a for a in population
                if a.behavior_descriptor is not None and assign_archetype(a) == name
            ]
            members = assigned

        if members:
            descriptors = [compute_behavior_descriptor(a) for a in members]
            arch["descriptor_centroid"] = np.mean(descriptors, axis=0)


def enforce_archetype_minimums(
    new_population: list[AttackerGenome],
    min_per_archetype: int,
    generation: int,
    protection_generations: int = 15,
) -> list[AttackerGenome]:
    """During early generations, ensure each archetype has minimum representation.

    If an archetype is underrepresented, clone its members to fill the quota,
    replacing the worst individuals at the end of the population.

    After protection_generations, this constraint is removed.
    """
    if generation >= protection_generations:
        return new_population

    archetype_members: dict[str, list[AttackerGenome]] = {n: [] for n in ARCHETYPES}
    for atk in new_population:
        arch = assign_archetype(atk)
        if arch in archetype_members:
            archetype_members[arch].append(atk)

    replacements: list[AttackerGenome] = []
    for arch_name, members in archetype_members.items():
        if len(members) >= min_per_archetype:
            continue
        if not members:
            continue
        deficit = min_per_archetype - len(members)
        for _ in range(deficit):
            parent = random.choice(members)
            clone = parent.snapshot()
            clone.genome_id = AttackerGenome().genome_id
            clone.generation = generation + 1
            clone.lineage = list(parent.lineage) + [parent.genome_id]
            replacements.append(clone)

    if replacements:
        pop = list(new_population)
        pop.sort(key=lambda a: a.pareto_rank)
        for rep in replacements:
            if pop:
                pop[-1] = rep
                pop = pop[:-1] + [rep]
        new_population = pop[:len(new_population)]

    return new_population
