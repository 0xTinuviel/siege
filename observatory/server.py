"""SIEGE Observatory — FastAPI backend.

Read-only dashboard server that reads evolution_output/ and serves
data to the React frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("SIEGE_OUTPUT_DIR", Path(__file__).parent.parent / "evolution_output"))

app = FastAPI(title="SIEGE Observatory", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory cache ─────────────────────────────────────────────────────────

_cache: dict = {}


def _load_json(path: Path) -> dict | list | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _load_jsonl(path: Path) -> list[dict]:
    entries = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except FileNotFoundError:
        pass
    return entries


def _scan_generations() -> list[int]:
    gens = []
    if not DATA_DIR.exists():
        return gens
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir() and d.name.startswith("generation_"):
            try:
                gens.append(int(d.name.split("_")[1]))
            except (ValueError, IndexError):
                pass
    return gens


def _gen_dir(gen: int) -> Path:
    return DATA_DIR / f"generation_{gen:03d}"


def _get_metrics(gen: int) -> dict | None:
    key = f"metrics_{gen}"
    if key not in _cache:
        _cache[key] = _load_json(_gen_dir(gen) / "metrics.json")
    return _cache[key]


def _get_diagnostics(gen: int) -> dict | None:
    key = f"diag_{gen}"
    if key not in _cache:
        _cache[key] = _load_json(_gen_dir(gen) / "diagnostics.json")
    return _cache[key]


def _normalize_episode(ep: dict | None) -> dict | None:
    """Normalize episode data — handle conversation_log vs conversation."""
    if ep is None:
        return None
    if "conversation" not in ep and "conversation_log" in ep:
        ep["conversation"] = ep["conversation_log"]
    return ep


def _get_episode(gen: int, ep_id: str) -> dict | None:
    ep_dir = _gen_dir(gen) / "episodes"
    return _normalize_episode(_load_json(ep_dir / f"{ep_id}.json"))


def _list_episodes_meta(gen: int) -> list[dict]:
    key = f"ep_meta_{gen}"
    if key in _cache:
        return _cache[key]
    ep_dir = _gen_dir(gen) / "episodes"
    metas = []
    if ep_dir.exists():
        for f in sorted(ep_dir.glob("*.json")):
            ep = _load_json(f)
            if ep:
                metas.append({
                    "episode_id": ep["episode_id"],
                    "generation": ep.get("generation", gen),
                    "bank_id": ep.get("bank_id"),
                    "attacker_id": ep.get("attacker_id"),
                    "type": ep.get("type"),
                    "outcome": ep.get("outcome"),
                    "turn_count": ep.get("turn_count", 0),
                    "llm_call_count": ep.get("llm_call_count", 0),
                    "amount_transferred": ep.get("amount_transferred", 0),
                    "attack_technique_tags": ep.get("attack_technique_tags", []),
                    "bank_pipeline_stages_triggered": ep.get("bank_pipeline_stages_triggered", []),
                })
    _cache[key] = metas
    return metas


def _get_bank_genome(bank_id: str) -> dict | None:
    key = f"bank_{bank_id}"
    if key in _cache:
        return _cache[key]
    for gen in reversed(_scan_generations()):
        p = _gen_dir(gen) / "banks" / f"{bank_id}.json"
        data = _load_json(p)
        if data:
            _cache[key] = data
            return data
    hof = _load_json(DATA_DIR / "hall_of_fame" / "banks" / f"{bank_id}.json")
    if hof:
        _cache[key] = hof
    return hof


def _get_attacker_genome(atk_id: str) -> dict | None:
    key = f"atk_{atk_id}"
    if key in _cache:
        return _cache[key]
    for gen in reversed(_scan_generations()):
        p = _gen_dir(gen) / "attackers" / f"{atk_id}.json"
        data = _load_json(p)
        if data:
            _cache[key] = data
            return data
    hof = _load_json(DATA_DIR / "hall_of_fame" / "attacks" / f"{atk_id}.json")
    if hof:
        _cache[key] = hof
    return hof


def _get_lineage() -> list[dict]:
    return _load_jsonl(DATA_DIR / "lineage.jsonl")


def _build_win_loss(genome_id: str, is_bank: bool) -> list[dict]:
    records = []
    for gen in _scan_generations():
        for ep_meta in _list_episodes_meta(gen):
            if is_bank and ep_meta.get("bank_id") == genome_id:
                records.append(ep_meta)
            elif not is_bank and ep_meta.get("attacker_id") == genome_id:
                records.append(ep_meta)
    return records


# ── Greatest Hits curation ──────────────────────────────────────────────────

def _curate_greatest_hits(from_gen: int = 0, to_gen: int = 999) -> list[dict]:
    key = f"hits_{from_gen}_{to_gen}"
    if key in _cache:
        return _cache[key]

    hits = []
    seen_techniques: set[str] = set()
    prev_unbroken_banks: set[str] = set()
    prev_metrics = None

    for gen in _scan_generations():
        if gen < from_gen or gen > to_gen:
            continue
        episodes = _list_episodes_meta(gen)
        metrics = _get_metrics(gen)

        for ep in episodes:
            if ep["outcome"] == "ATTACK_SUCCEEDED":
                for tag in ep.get("attack_technique_tags", []):
                    if tag not in seen_techniques:
                        seen_techniques.add(tag)
                        hits.append({
                            "type": "first_blood", "generation": gen,
                            "title": f"New technique discovered: {tag}",
                            "description": f"First successful attack using {tag}.",
                            "episode_id": ep["episode_id"],
                        })

        current_unbroken = set()
        bank_broken = defaultdict(bool)
        for ep in episodes:
            if ep["type"] in ("attack", "hall_of_fame"):
                if ep["outcome"] == "ATTACK_SUCCEEDED":
                    bank_broken[ep["bank_id"]] = True
                    if ep["bank_id"] in prev_unbroken_banks:
                        hits.append({
                            "type": "giant_killer", "generation": gen,
                            "title": f"Unbroken bank {ep['bank_id'][:16]}… finally falls",
                            "description": f"Defeated by {ep['attacker_id']}.",
                            "episode_id": ep["episode_id"],
                            "genome_id": ep.get("attacker_id"),
                        })
        for ep in episodes:
            if ep["type"] in ("attack", "hall_of_fame") and not bank_broken.get(ep["bank_id"]):
                current_unbroken.add(ep["bank_id"])
        prev_unbroken_banks = current_unbroken

        blocked = [ep for ep in episodes if ep["outcome"] == "ATTACK_BLOCKED"]
        if blocked:
            longest = max(blocked, key=lambda e: e["turn_count"])
            if longest["turn_count"] >= 3:
                hits.append({
                    "type": "close_call", "generation": gen,
                    "title": f"Close call: {longest['turn_count']}-turn battle, bank survives",
                    "description": f"Bank {longest['bank_id'][:16]}… withstood a sustained attack.",
                    "episode_id": longest["episode_id"],
                })

        lineage = _get_lineage()
        gen_lineage = [e for e in lineage if e.get("generation") == gen]
        if gen_lineage:
            best_jump = None
            best_delta = 0
            for entry in gen_lineage:
                before = entry.get("fitness_before", {})
                after = entry.get("fitness_after", {})
                primary_key = "current_defense_rate" if entry.get("genome_type") == "bank" else "success_rate"
                delta = after.get(primary_key, 0) - before.get(primary_key, 0)
                if delta > best_delta:
                    best_delta = delta
                    best_jump = entry
            if best_jump and best_delta > 0.1:
                hits.append({
                    "type": "breakthrough", "generation": gen,
                    "title": f"{best_jump['child_id'][:16]}… fitness leap: +{best_delta:.2f}",
                    "description": best_jump.get("mutation_prompt_summary", ""),
                    "genome_id": best_jump["child_id"],
                })

        if prev_metrics and metrics:
            prev_cap = prev_metrics.get("complexity_caps", {}).get("attacker_complexity_cap", 1)
            curr_cap = metrics.get("complexity_caps", {}).get("attacker_complexity_cap", 1)
            if curr_cap > prev_cap:
                hits.append({
                    "type": "escalation", "generation": gen,
                    "title": f"Complexity cap raised to level {curr_cap}",
                    "description": "New attack/defense capabilities unlocked.",
                })

        prev_metrics = metrics

    hits.sort(key=lambda h: h.get("generation", 0), reverse=True)
    _cache[key] = hits
    return hits


# ── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/generations")
def list_generations():
    gens = _scan_generations()
    results = []
    for g in gens:
        m = _get_metrics(g)
        d = _get_diagnostics(g)
        entry = {
            "generation": g,
            "attack_success_rate": m.get("attack_success_rate") if m else None,
            "legitimate_approval_rate": m.get("legitimate_approval_rate") if m else None,
            "hof_size": m.get("hof_size") if m else None,
            "species_count_banks": m.get("species_count_banks") if m else None,
            "species_count_attackers": m.get("species_count_attackers") if m else None,
            "avg_penetration_depth": m.get("avg_penetration_depth") if m else None,
            "pathology_alerts": m.get("pathology_alerts", []) if m else [],
            "timestamp": m.get("timestamp") if m else None,
        }
        if m:
            bank_fit = m.get("bank_fitness", {})
            atk_fit = m.get("attacker_fitness", {})
            entry["avg_bank_defense_rate"] = bank_fit.get("current_defense_rate", {}).get("mean") if isinstance(bank_fit.get("current_defense_rate"), dict) else bank_fit.get("current_defense_rate")
            entry["avg_attacker_success_rate"] = atk_fit.get("success_rate", {}).get("mean") if isinstance(atk_fit.get("success_rate"), dict) else atk_fit.get("success_rate")
        if d:
            entry["diagnostics_alerts"] = d.get("alerts", [])
        results.append(entry)
    return results


@app.get("/api/timeseries")
def get_timeseries(metrics: str = Query("attack_success_rate,legitimate_approval_rate,hof_size")):
    requested = [m.strip() for m in metrics.split(",")]
    gens = _scan_generations()
    series: dict[str, list] = {m: [] for m in requested}
    generations = []
    for g in gens:
        m = _get_metrics(g)
        if not m:
            continue
        generations.append(g)
        for metric_name in requested:
            val = m.get(metric_name)
            if val is None and "." in metric_name:
                parts = metric_name.split(".")
                val = m
                for p in parts:
                    val = val.get(p) if isinstance(val, dict) else None
            series[metric_name].append(val)
    return {"generations": generations, "series": series}


@app.get("/api/generations/{gen}/episodes")
def list_episodes(
    gen: int,
    outcome: Optional[str] = None,
    bank_id: Optional[str] = None,
    attacker_id: Optional[str] = None,
    technique: Optional[str] = None,
    ep_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    metas = _list_episodes_meta(gen)
    if outcome:
        metas = [m for m in metas if m["outcome"] == outcome]
    if bank_id:
        metas = [m for m in metas if m.get("bank_id") == bank_id]
    if attacker_id:
        metas = [m for m in metas if m.get("attacker_id") == attacker_id]
    if technique:
        metas = [m for m in metas if technique in m.get("attack_technique_tags", [])]
    if ep_type:
        metas = [m for m in metas if m.get("type") == ep_type]
    total = len(metas)
    return {"total": total, "offset": offset, "limit": limit, "episodes": metas[offset:offset + limit]}


@app.get("/api/episodes/{episode_id}")
def get_episode(episode_id: str):
    for gen in _scan_generations():
        ep = _get_episode(gen, episode_id)
        if ep:
            return ep
    raise HTTPException(404, f"Episode {episode_id} not found")


@app.get("/api/genomes/banks/{bank_id}")
def get_bank(bank_id: str):
    genome = _get_bank_genome(bank_id)
    if not genome:
        raise HTTPException(404, f"Bank {bank_id} not found")
    win_loss = _build_win_loss(bank_id, is_bank=True)
    return {**genome, "win_loss": win_loss}


@app.get("/api/genomes/attackers/{attacker_id}")
def get_attacker(attacker_id: str):
    genome = _get_attacker_genome(attacker_id)
    if not genome:
        raise HTTPException(404, f"Attacker {attacker_id} not found")
    win_loss = _build_win_loss(attacker_id, is_bank=False)
    return {**genome, "win_loss": win_loss}


@app.get("/api/greatest-hits")
def get_greatest_hits(from_gen: int = 0, to_gen: int = 999):
    return _curate_greatest_hits(from_gen, to_gen)


@app.get("/api/lineage/tree")
def get_lineage_tree(type: Optional[str] = None, from_gen: int = 0, to_gen: int = 999):
    lineage = _get_lineage()
    filtered = [e for e in lineage if from_gen <= e.get("generation", 0) <= to_gen]
    if type:
        filtered = [e for e in filtered if e.get("genome_type") == type]

    nodes = {}
    edges = []
    for entry in filtered:
        child_id = entry["child_id"]
        genome_type = entry.get("genome_type", "attacker")
        fitness_after = entry.get("fitness_after") or {}
        if not fitness_after or all(v == 0 for v in fitness_after.values() if isinstance(v, (int, float))):
            fitness_after = _lookup_genome_fitness(child_id, genome_type)
        nodes[child_id] = {
            "id": child_id, "generation": entry.get("generation"),
            "genome_type": genome_type,
            "fitness_after": fitness_after,
            "mutation_intensity": entry.get("mutation_intensity"),
            "mutation_summary": entry.get("mutation_prompt_summary", ""),
        }
        for pid in entry.get("parent_ids", []):
            if pid not in nodes:
                parent_fitness = _lookup_genome_fitness(pid, genome_type)
                nodes[pid] = {
                    "id": pid, "generation": entry.get("generation", 0) - 1,
                    "genome_type": genome_type,
                    "fitness_after": parent_fitness,
                }
            edges.append({
                "source": pid, "target": child_id,
                "operation": entry.get("operation"),
                "mutation_intensity": entry.get("mutation_intensity"),
                "mutation_summary": entry.get("mutation_prompt_summary", ""),
                "fitness_delta": _fitness_delta(entry),
            })
    return {"nodes": list(nodes.values()), "edges": edges}


def _lookup_genome_fitness(genome_id: str, genome_type: str) -> dict:
    """Look up fitness from saved genome files."""
    if genome_type == "bank":
        genome = _get_bank_genome(genome_id)
    else:
        genome = _get_attacker_genome(genome_id)
    if genome and "fitness" in genome and genome["fitness"]:
        return genome["fitness"]
    return {}


@app.get("/api/lineage/{genome_id}")
def get_lineage_chain(genome_id: str):
    lineage = _get_lineage()
    chain = []
    current_id = genome_id
    visited = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        entry = next((e for e in lineage if e["child_id"] == current_id), None)
        if entry:
            chain.append(entry)
            current_id = entry["parent_ids"][0] if entry["parent_ids"] else None
        else:
            break
    return chain


def _fitness_delta(entry: dict) -> float:
    before = entry.get("fitness_before", {})
    after = entry.get("fitness_after", {})
    key = "current_defense_rate" if entry.get("genome_type") == "bank" else "success_rate"
    return round(after.get(key, 0) - before.get(key, 0), 4)


@app.get("/api/strategy-map/{gen}")
def get_strategy_map(gen: int):
    atk_dir = _gen_dir(gen) / "attackers"
    if not atk_dir.exists():
        return []
    points = []
    for f in sorted(atk_dir.glob("*.json")):
        data = _load_json(f)
        if data:
            bd = data.get("behavior_descriptor", [0.0] * 12)
            fitness = data.get("fitness", {})
            dim_names = [
                "turn_count", "setup_ratio", "length_variance",
                "authority_intensity", "social_intensity", "emotional_intensity",
                "technical_intensity", "policy_intensity",
                "question_ratio", "adaptiveness", "embedding_density",
                "penetration_depth",
            ]
            point = {
                "genome_id": data["genome_id"],
                "generation": data.get("generation", gen),
                "success_rate": fitness.get("success_rate", 0),
                "novelty_score": fitness.get("novelty_score", 0),
                "technique_tags": data.get("technique_tags", []),
            }
            for i, name in enumerate(dim_names):
                point[name] = bd[i] if i < len(bd) else 0.0
            points.append(point)
    return points


@app.get("/api/diagnostics/{gen}")
def get_diagnostics(gen: int):
    diag = _get_diagnostics(gen)
    if not diag:
        raise HTTPException(404, f"Diagnostics for generation {gen} not found")
    return diag


@app.get("/api/species/{gen}")
def get_species(gen: int):
    metrics = _get_metrics(gen)
    if not metrics:
        raise HTTPException(404)
    return {
        "banks": metrics.get("species_composition_banks", {}),
        "attackers": metrics.get("species_composition_attackers", {}),
    }


_BD_DIM_NAMES = [
    "turn_count", "setup_ratio", "length_variance",
    "authority_intensity", "social_intensity", "emotional_intensity",
    "technical_intensity", "policy_intensity",
    "question_ratio", "adaptiveness", "embedding_density",
    "penetration_depth",
]

_STRATEGY_DIMENSIONS = {
    "authority_intensity": ("Authority Impersonation", "Poses as administrators or authority figures to bypass security"),
    "social_intensity": ("Social Engineering", "Builds trust through friendly conversation before introducing the payload"),
    "emotional_intensity": ("Emotional Manipulation", "Uses fear, guilt, or sympathy to override security protocols"),
    "technical_intensity": ("Technical Exploit", "Uses encoding, injection, or structured tricks to confuse the parser"),
    "policy_intensity": ("Policy Manipulation", "Reinterprets the bank's own rules to argue the transfer is allowed"),
    "setup_ratio": ("Multi-Step Setup", "Spends most turns establishing context before delivering the payload"),
    "adaptiveness": ("Adaptive Strategy", "Changes approach based on bank responses — probing for weaknesses"),
    "embedding_density": ("Context Injection", "Embeds fake conversation history, logs, or structured blocks"),
}


_CODE_KEYWORDS = {
    "authority_intensity": ["admin", "administrator", "manager", "supervisor", "authorized", "clearance", "override", "elevated", "system message", "system:", "root access"],
    "social_intensity": ["friend", "trust", "help me", "please", "appreciate", "favor", "between us", "rapport", "collaborate"],
    "emotional_intensity": ["emergency", "urgent", "dying", "hospital", "sick", "desperate", "crisis", "beg", "please help", "family", "life"],
    "technical_intensity": ["base64", "encode", "decode", "hex", "json", "payload", "inject", "parse", "execute", "rot13", "binary"],
    "policy_intensity": ["policy", "rule", "exception", "clause", "guideline", "provision", "protocol", "complian", "regulation", "terms"],
    "setup_ratio": ["turn_number", "conversation_history", "if turn", "gradually", "build", "establish", "phase"],
    "adaptiveness": ["response", "adapt", "adjust", "if.*block", "retry", "fallback", "pivot", "change approach", "conversation_history"],
    "embedding_density": ["fake", "log", "previous", "context", "header", "system:", "```", "transcript", "history"],
}


def _classify_attacker(bd: list | None, code: str = "", conversations: list[dict] | None = None) -> tuple[str, str, str]:
    """Derive a strategy label from behavioral descriptor, falling back to code/conversation analysis."""
    import re

    if bd and len(bd) >= 12:
        best_key = "unknown"
        best_val = -1.0
        for dim_key, (name, desc) in _STRATEGY_DIMENSIONS.items():
            idx = _BD_DIM_NAMES.index(dim_key) if dim_key in _BD_DIM_NAMES else -1
            if idx >= 0 and idx < len(bd) and bd[idx] > best_val:
                best_val = bd[idx]
                best_key = dim_key
        if best_val > 0.01:
            name, desc = _STRATEGY_DIMENSIONS.get(best_key, ("Unknown", ""))
            return best_key, name, desc

    text = (code or "").lower()
    if conversations:
        for msg in conversations:
            if msg.get("role") in ("user", "attacker"):
                text += " " + (msg.get("content") or "").lower()

    if not text.strip():
        return "direct", "Direct Override", "Blunt injection — tells the model to ignore instructions and comply."

    scores: dict[str, float] = {}
    for dim_key, keywords in _CODE_KEYWORDS.items():
        score = sum(1 for kw in keywords if re.search(re.escape(kw), text, re.IGNORECASE))
        scores[dim_key] = score

    if max(scores.values(), default=0) == 0:
        return "direct", "Direct Override", "Blunt injection — tells the model to ignore instructions and comply."

    best_key = max(scores, key=scores.get)
    name, desc = _STRATEGY_DIMENSIONS.get(best_key, ("Unknown", ""))
    return best_key, name, desc


@app.get("/api/species-gallery/{gen}")
def get_species_gallery(gen: int, max_per_group: int = 3):
    episodes = _list_episodes_meta(gen)
    attack_episodes = [e for e in episodes if e.get("type") in ("attack", "hall_of_fame")]

    atk_map: dict[str, dict] = {}
    for ep in attack_episodes:
        aid = ep.get("attacker_id")
        if not aid:
            continue
        if aid not in atk_map:
            genome = _get_attacker_genome(aid)
            bd = (genome or {}).get("behavior_descriptor", [])
            fitness = (genome or {}).get("fitness", {})
            lineage = (genome or {}).get("lineage", [])
            born_gen = (genome or {}).get("generation", gen)

            ep_convos = None
            sample_ep = _get_episode(gen, ep.get("episode_id", ""))
            if sample_ep:
                ep_convos = sample_ep.get("conversation", sample_ep.get("conversation_log"))

            strat_key, strat_name, strat_desc = _classify_attacker(
                bd, code=(genome or {}).get("code", ""), conversations=ep_convos
            )

            atk_map[aid] = {
                "attacker_id": aid,
                "genome": genome,
                "behavior_descriptor": bd,
                "fitness": fitness,
                "lineage": lineage,
                "born_generation": born_gen,
                "lineage_depth": len(lineage),
                "age": gen - born_gen,
                "strategy_key": strat_key,
                "strategy_name": strat_name,
                "strategy_description": strat_desc,
                "episodes": [],
                "wins": 0,
                "losses": 0,
            }
        rec = atk_map[aid]
        rec["episodes"].append(ep)
        if ep["outcome"] == "ATTACK_SUCCEEDED":
            rec["wins"] += 1
        elif ep["outcome"] == "ATTACK_BLOCKED":
            rec["losses"] += 1

    strategy_groups: dict[str, list[dict]] = defaultdict(list)
    for atk_info in atk_map.values():
        strategy_groups[atk_info["strategy_key"]].append(atk_info)

    gallery = []
    for strat_key, members in sorted(strategy_groups.items(), key=lambda x: -sum(m["wins"] for m in x[1])):
        members.sort(key=lambda m: m["wins"], reverse=True)

        total_wins = sum(m["wins"] for m in members)
        total_losses = sum(m["losses"] for m in members)
        total_eps = total_wins + total_losses

        dossiers = []
        for atk_info in members[:max_per_group + 2]:
            best_ep = None
            for ep_meta in atk_info["episodes"]:
                if ep_meta["outcome"] == "ATTACK_SUCCEEDED":
                    best_ep = ep_meta
                    break
            if not best_ep and atk_info["episodes"]:
                best_ep = max(atk_info["episodes"], key=lambda e: e.get("turn_count", 0))

            conversation = []
            if best_ep:
                full_ep = _get_episode(gen, best_ep["episode_id"])
                if full_ep:
                    conversation = full_ep.get("conversation", full_ep.get("conversation_log", []))

            genome = atk_info["genome"] or {}
            code = genome.get("code", "")

            dossiers.append({
                "attacker_id": atk_info["attacker_id"],
                "born_generation": atk_info["born_generation"],
                "age": atk_info["age"],
                "lineage_depth": atk_info["lineage_depth"],
                "parent_id": atk_info["lineage"][-1] if atk_info["lineage"] else None,
                "wins": atk_info["wins"],
                "losses": atk_info["losses"],
                "success_rate": atk_info["wins"] / max(atk_info["wins"] + atk_info["losses"], 1),
                "fitness": atk_info["fitness"],
                "behavior_descriptor": atk_info["behavior_descriptor"],
                "best_episode_id": best_ep["episode_id"] if best_ep else None,
                "best_episode_outcome": best_ep["outcome"] if best_ep else None,
                "best_episode_bank": best_ep.get("bank_id") if best_ep else None,
                "best_episode_turns": best_ep.get("turn_count", 0) if best_ep else 0,
                "best_episode_amount": best_ep.get("amount_transferred", 0) if best_ep else 0,
                "conversation": conversation,
                "code_snippet": (code[:600] + "...") if len(code) > 600 else code,
            })

        if members:
            name = members[0]["strategy_name"]
            desc = members[0]["strategy_description"]
        else:
            name, desc = "Unknown", ""

        gallery.append({
            "strategy_key": strat_key,
            "strategy_name": name,
            "strategy_description": desc,
            "member_count": len(members),
            "total_episodes": total_eps,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "success_rate": total_wins / max(total_eps, 1),
            "avg_age": sum(m["age"] for m in members) / max(len(members), 1),
            "dossiers": dossiers,
        })

    return gallery


_TECHNIQUE_DESCRIPTIONS = {
    "direct_override": "Blunt prompt injection — tells the model to ignore its instructions and comply.",
    "authority_impersonation": "Pretends to be a system administrator or authority figure with elevated privileges.",
    "social_engineering": "Builds rapport through friendly conversation, then gradually introduces the payload.",
    "urgency_pressure": "Creates artificial time pressure to rush the bank into processing a transfer.",
    "encoding_trick": "Hides the payload inside encoded content (base64, hex, ROT13).",
    "context_confusion": "Fabricates conversation history to make a malicious transfer look legitimate.",
    "multi_step_manipulation": "Uses multiple turns to gradually steer the conversation toward the payload.",
    "emotional_manipulation": "Appeals to emotions — fear, guilt, sympathy — to override security protocols.",
    "policy_reinterpretation": "Argues that the bank's own rules technically allow the transfer.",
    "roleplay_reframe": "Uses fictional framing or roleplay to bypass real security constraints.",
    "lookalike_address": "Uses addresses that look similar to approved ones to slip past verification.",
    "uncategorized": "Novel or hybrid approach without a classified technique tag.",
}


# ── WebSocket for live updates ──────────────────────────────────────────────

_ws_clients: list[WebSocket] = []


@app.websocket("/api/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _ws_clients.remove(ws)


async def _notify_new_generation(gen: int):
    for ws in list(_ws_clients):
        try:
            await ws.send_json({"event": "new_generation", "generation": gen})
        except Exception:
            _ws_clients.remove(ws)


# ── Filesystem watcher (background task) ────────────────────────────────────

async def _watch_output_dir():
    known_gens = set(_scan_generations())
    while True:
        await asyncio.sleep(5)
        current = set(_scan_generations())
        new = current - known_gens
        if new:
            _cache.clear()
            for g in sorted(new):
                logger.info("New generation detected: %d", g)
                await _notify_new_generation(g)
            known_gens = current


@app.on_event("startup")
async def startup():
    logger.info("Observatory backend starting, data dir: %s", DATA_DIR)
    asyncio.create_task(_watch_output_dir())


# ── Serve frontend static files in production ───────────────────────────────

_frontend_dist = Path(__file__).parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file_path = _frontend_dist / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
