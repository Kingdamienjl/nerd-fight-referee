"""Local LLM fight judge constrained to the supplied fight packet."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from typing import Any

import httpx

from battlebot.common.db import connect_database
from battlebot.fight.decision_formatter import format_decision, sanitize_fight_card_item, truncate_at_sentence_boundary
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.profiles.fight_packet import build_fight_packet


FALLBACK_LLM_DISABLED = "LLM disabled"
FALLBACK_OLLAMA_UNAVAILABLE = "Ollama unavailable"
FALLBACK_TIMEOUT = "timeout"
LOCKED_ENGINE_CONFIDENCE = {"high", "strong"}
SYSTEM_PROMPT = (
    "You are the official Nerd Fight Referee giving a post-fight referee explanation. The "
    "deterministic engine chooses the winner and confidence; you explain why that verdict "
    "happened using only the supplied packet evidence. Do not invent feats, named techniques, "
    "powers, forms, equipment, prep time, or weaknesses."
)
BATTLE_RULES = (
    "Battle rules: standard encounter; no prep unless profile explicitly grants it; strongest "
    "consistent canonical profile from DB; no unsupported claims; evidence packet is source of truth."
)


def llm_enabled(env: dict[str, str] | None = None) -> bool:
    values = env or os.environ
    return str(values.get("BATTLEBOT_LLM_ENABLED") or "").casefold() in {"1", "true", "yes", "on"}


def compact_snippet(value: Any, *, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if any(fragment in text.casefold() for fragment in ("{{", "}}", "tag:", "tabber", "border", "content", "no • yes")):
        text = sanitize_fight_card_item(text)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."


def compact_named_items(values: Any, *, limit: int = 6) -> list[Any]:
    if not values:
        return []
    if isinstance(values, str):
        snippet = compact_snippet(values)
        return [snippet] if snippet else []
    compact = []
    if isinstance(values, (list, tuple)):
        for item in list(values)[:limit]:
            if isinstance(item, dict):
                entry = {
                    key: snippet
                    for key in ("name", "id", "description", "effect", "tags", "scope_limitations")
                    if item.get(key) and (snippet := compact_snippet(item.get(key)))
                }
                if entry:
                    compact.append(entry)
            else:
                snippet = compact_snippet(item)
                if snippet:
                    compact.append(snippet)
    return compact


def compact_tactical_fields(contender: dict[str, Any]) -> dict[str, Any]:
    tactical = contender.get("tactical_profile") if isinstance(contender.get("tactical_profile"), dict) else {}
    keys = (
        "tactical_intelligence",
        "combat_style",
        "battlefield_control",
        "notable_attacks",
        "techniques",
        "forms",
        "transformations",
        "counters",
        "resistances",
        "win_conditions",
        "loss_conditions",
        "matchup_notes",
        "fighting_style",
        "power_source",
        "magic",
        "special_abilities",
        "personality",
    )
    compact = {}
    for key in keys:
        value = contender.get(key) or tactical.get(key)
        if value:
            compact[key] = compact_named_items(value) if isinstance(value, (list, tuple)) else value
    return compact


def compact_evidence_packet(packet: dict[str, Any], smoke_baseline: dict[str, Any]) -> dict[str, Any]:
    if packet.get("errors"):
        return {"errors": packet.get("errors"), "smoke_baseline": smoke_baseline}
    contenders = {}
    for key in ("contender_a", "contender_b"):
        contender = packet.get(key) or {}
        contenders[key] = {
            "character_id": contender.get("character_id"),
            "canonical_name": contender.get("canonical_name"),
            "franchise": contender.get("franchise"),
            "category": contender.get("category"),
            "variant": contender.get("variant") or {},
            "power_scale": contender.get("power_scale") or {},
            "abilities": compact_named_items(contender.get("abilities") or []),
            "equipment": compact_named_items(contender.get("equipment") or []),
            "weaknesses": compact_named_items(contender.get("weaknesses") or []),
            "powers": compact_named_items(contender.get("powers") or contender.get("special_abilities") or []),
            "magic": compact_named_items(contender.get("magic") or []),
            "weapons": compact_named_items(contender.get("weapons") or []),
            "tactical_profile": compact_tactical_fields(contender),
            "warnings": contender.get("warnings") or [],
        }
    return {
        "rules": packet.get("rules") or {},
        "contenders": contenders,
        "quality_warnings": packet.get("warnings") or [],
        "smoke_baseline": smoke_baseline,
    }


def build_prompt(packet: dict[str, Any], smoke_baseline: dict[str, Any]) -> list[dict[str, str]]:
    evidence = compact_evidence_packet(packet, smoke_baseline)
    deciding_factors = smoke_baseline.get("deciding_factors") or []
    advantage_breakdown = smoke_baseline.get("advantage_breakdown") or {}
    fight_flow = smoke_baseline.get("fight_flow") or {}
    engine_reasoning = smoke_baseline.get("engine_reasoning") or []
    swing_factors = smoke_baseline.get("swing_factors") or []
    briefing = "\n".join(
        [
            f"Winner: {smoke_baseline.get('winner')}",
            f"Confidence: {smoke_baseline.get('confidence')}",
            f"Win condition / route to victory: {smoke_baseline.get('win_condition') or smoke_baseline.get('route_to_victory')}",
            f"Loser's best path: {smoke_baseline.get('loser_best_path')}",
            "Deciding factors:",
            json.dumps(deciding_factors, sort_keys=True),
            "advantage_breakdown:",
            json.dumps(advantage_breakdown, sort_keys=True),
            "fight_flow:",
            json.dumps(fight_flow, sort_keys=True),
            "engine_reasoning:",
            json.dumps(engine_reasoning, sort_keys=True),
            "swing_factors:",
            json.dumps(swing_factors, sort_keys=True),
            "Compact packet evidence for both contenders:",
            json.dumps(evidence, sort_keys=True),
        ]
    )
    user_prompt = "\n".join(
        [
            BATTLE_RULES,
            briefing,
            "You are the official Nerd Fight Referee.",
            "Do not change the winner.",
            "Do not invent feats.",
            "Do not contradict supplied evidence.",
            "Write in past tense as a post-fight referee explanation, not live play-by-play.",
            "Use fight scene detail, but keep the analysis outcome-focused rather than present-tense commentary.",
            "Describe what happened in the opening exchange, the winner's first meaningful tactic, the loser's best counterplay, how the winner adapted or countered that counterplay, and the finishing sequence.",
            "The loser must make at least one concrete counterplay attempt using supplied evidence.",
            "Do not require both fighter names in every paragraph; use names naturally instead of repetitive forced naming.",
            'When a fighter name is known, avoid vague labels: "the opponent", "his opponent", "her opponent", "their opponent", "the adversary".',
            "Use fighter names naturally at phase transitions: opening, counterplay, and finish.",
            "Before narrating, identify each fighter's combat mode from the packet: brawler, weapon specialist, martial artist, magic user, ranged energy user, cosmic/reality hax user, speedster, tank/bruiser, summoner, or tech user.",
            "Use each fighter's combat identity when narrating their opening and counterplay.",
            "Do not describe a fighter as relying on punches, kicks, grappling, or mundane melee unless those tactics are present in the packet.",
            "If a fighter has signature magic, transformation, ranged powers, purification, barriers, cosmic power, or energy projection, their counterplay must use those tools instead of generic melee.",
            "Do not flatten magical, cosmic, ranged, tech, or hax-based fighters into generic brawlers.",
            "Use safe tactical inference: infer how supplied abilities were used in combat, but do not invent new powers, forms, weapons, techniques, or feats not in the packet.",
            "Do not name any technique, form, weapon, power source, eye power, transformation, spell, or named attack unless the exact name appears in the compact evidence packet.",
            "Only name a technique, ability, weapon, or form if the exact name appears in the compact evidence packet.",
            "If only a generic capability is supplied, describe it generically.",
            "Explicitly forbid invented named techniques, powers, forms, or equipment.",
            "Use concrete supplied terms from the compact evidence packet.",
            "Mention named abilities, equipment, techniques, forms, weaknesses, or counters from both fighters when available.",
            "Mention at least two concrete listed traits, stats, abilities, equipment, or weaknesses when available.",
            'Avoid vague phrases like "various forms", "special abilities", or "high strength" unless those exact phrases are in the packet.',
            'Never use these phrases: "as evidenced by the packet", "listed abilities", "main route stabilizes", "clean openings into decisive damage", "exchange pattern", "escalation options", "higher speed tier".',
            'Avoid live play-by-play phrases like "as the fight begins", "the opening exchange is", or present-tense phrasing like "Green Lantern does X".',
            'Prefer past-tense phrasing like "Green Lantern opened by...", "Naruto tried to...", "That failed because...", and "The finish came when...".',
            'Itachi may use "Sharingan" only if "Sharingan" appears in the compact evidence packet.',
            'Itachi may NOT use "Byakugan" unless "Byakugan" appears in the compact evidence packet.',
            'Green Lantern may NOT use "Speed Force" unless "Speed Force" appears in the compact evidence packet.',
            "Naruto may NOT use invented chakra techniques unless the exact technique appears in the compact evidence packet.",
            'Allowed if the packet says "Shadow Clone Jutsu": "Naruto tried to flood the field with Shadow Clone Jutsu."',
            'Forbidden if the packet does not say "Chakra Resonance Technique" or "Speed Force": do not invent it.',
            "Do not make every fight only about speed, strength, and durability.",
            "When present, consider intelligence, tactics, battlefield control, hax, resistances, weaknesses, counters, regeneration, time manipulation, sealing, mind control, energy absorption, range, mobility, and win conditions.",
            'Prefer concrete post-fight wording: "Goku pressured with rapid movement, forced a guard with close-range strikes, then created space for a Kamehameha once the opponent was pinned or staggered."',
            "Reference supplied evidence naturally without repeating the evidence list verbatim.",
            "Write 2-4 concise paragraphs.",
            "End with a complete sentence.",
            "No JSON.",
            "No bullet lists.",
            "No markdown headings.",
        ]
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def engine_verdict(smoke: dict[str, Any]) -> dict[str, Any]:
    return {
        "winner": smoke.get("winner"),
        "winner_character_id": smoke.get("winner_character_id"),
        "confidence": smoke.get("confidence"),
        "win_condition": smoke.get("win_condition"),
        "loser_best_path": smoke.get("loser_best_path"),
        "loser": smoke.get("loser"),
        "loser_character_id": smoke.get("loser_character_id"),
        "deciding_factors": smoke.get("deciding_factors") or [],
        "winner_probability": smoke.get("winner_probability"),
        "loser_probability": smoke.get("loser_probability"),
        "overall_probability": smoke.get("overall_probability"),
        "advantage_breakdown": smoke.get("advantage_breakdown") or {},
        "swing_factors": smoke.get("swing_factors") or [],
        "fight_flow": smoke.get("fight_flow") or {},
        "engine_reasoning": smoke.get("engine_reasoning") or [],
        "matchup_card": smoke.get("matchup_card") or [],
    }


def confidence_allows_upset(confidence: Any) -> bool:
    return str(confidence or "").casefold() not in LOCKED_ENGINE_CONFIDENCE


def contender_names(packet: dict[str, Any]) -> list[str]:
    names = []
    for key in ("contender_a", "contender_b"):
        contender = packet.get(key) if isinstance(packet.get(key), dict) else {}
        for value in (contender.get("canonical_name"), contender.get("character_id")):
            if value and str(value) not in names:
                names.append(str(value))
    return names


def extract_prefixed_line(text: str, prefix: str) -> str:
    normalized_prefix = prefix.casefold()
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.casefold().startswith(normalized_prefix):
            return stripped[len(prefix) :].strip(" :-")
    return ""


def referee_winner_from_text(raw: str, names: list[str]) -> str:
    explicit = extract_prefixed_line(raw, "Referee verdict")
    search_space = explicit or raw
    for name in names:
        if name and name.casefold() in search_space.casefold():
            return name
    return explicit


def referee_verdict(
    smoke: dict[str, Any],
    raw: str,
    explanation: str,
    *,
    packet: dict[str, Any],
) -> dict[str, Any]:
    engine_winner = str(smoke.get("winner") or "")
    recommended_winner = engine_winner
    upset_justification = ""
    changed = False
    if confidence_allows_upset(smoke.get("confidence")):
        candidate = referee_winner_from_text(raw, contender_names(packet))
        if candidate and candidate != engine_winner:
            recommended_winner = candidate
            changed = True
            upset_justification = extract_prefixed_line(raw, "Upset justification") or explanation[:280]
    return {
        "winner": recommended_winner,
        "changed_winner": changed,
        "upset_allowed": confidence_allows_upset(smoke.get("confidence")),
        "upset_justification": upset_justification,
        "explanation": explanation,
    }


def clean_llm_explanation(raw: str) -> str:
    return " ".join(str(raw or "").replace("\n", " ").split()).strip()


def llm_explained_decision(smoke: dict[str, Any], raw: str, *, packet: dict[str, Any]) -> dict[str, Any]:
    explanation = clean_llm_explanation(raw)
    if not explanation:
        return fallback_decision(smoke, FALLBACK_OLLAMA_UNAVAILABLE, "LLM returned an empty explanation.")
    concise_explanation = truncate_at_sentence_boundary(explanation, 1100)
    engine = engine_verdict(smoke)
    referee = referee_verdict(smoke, raw, concise_explanation, packet=packet)
    decision = {
        **smoke,
        "title": "Nerd Fight Referee Decision",
        "summary": concise_explanation,
        "win_condition": concise_explanation,
        "engine_verdict": engine,
        "referee_verdict": referee,
    }
    notes = list(decision.get("judge_notes") or [])
    notes.append("LLM generated referee review; deterministic engine verdict remains available.")
    if referee["changed_winner"]:
        notes.append("Referee recommended an upset winner because engine confidence allowed review.")
    decision["judge_notes"] = notes
    decision["diagnostics"] = {
        "fallback": False,
        "fallback_reason": "llm_explanation",
        "fallback_detail": "LLM explanation applied to deterministic decision.",
        "engine_verdict": engine,
    }
    return decision



def fallback_decision(smoke_baseline: dict[str, Any], reason: str, detail: str = "") -> dict[str, Any]:
    engine = engine_verdict(smoke_baseline)
    explanation = smoke_baseline.get("summary") or "LLM judge unavailable; using deterministic fallback."
    return {
        "title": "Nerd Fight Referee Decision",
        "winner": smoke_baseline.get("winner"),
        "confidence": smoke_baseline.get("confidence") or "needs_judge_review",
        "summary": explanation,
        "win_condition": smoke_baseline.get("win_condition") or "Fallback uses packet-backed stat leads.",
        "loser_best_path": smoke_baseline.get("loser_best_path") or "Evidence is incomplete.",
        "loser": smoke_baseline.get("loser"),
        "loser_character_id": smoke_baseline.get("loser_character_id"),
        "deciding_factors": smoke_baseline.get("deciding_factors") or [],
        "overall_probability": smoke_baseline.get("overall_probability"),
        "winner_probability": smoke_baseline.get("winner_probability"),
        "loser_probability": smoke_baseline.get("loser_probability"),
        "advantage_breakdown": smoke_baseline.get("advantage_breakdown") or {},
        "swing_factors": smoke_baseline.get("swing_factors") or [],
        "fight_flow": smoke_baseline.get("fight_flow") or {},
        "engine_reasoning": smoke_baseline.get("engine_reasoning") or [],
        "matchup_card": smoke_baseline.get("matchup_card") or [],
        "engine_verdict": engine,
        "referee_verdict": {
            "winner": smoke_baseline.get("winner"),
            "changed_winner": False,
            "upset_allowed": confidence_allows_upset(smoke_baseline.get("confidence")),
            "upset_justification": "",
            "explanation": explanation,
        },
        "warnings": list(smoke_baseline.get("warnings") or []),
        "judge_notes": [detail, *list(smoke_baseline.get("profile_quality_notes") or [])] if detail else list(smoke_baseline.get("profile_quality_notes") or []),
        "diagnostics": {
            "fallback": True,
            "fallback_reason": reason,
            "fallback_detail": detail,
            "engine_verdict": engine,
        },
    }


def fallback_reason_for_exception(exc: Exception) -> str:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return FALLBACK_TIMEOUT
    if isinstance(exc, (httpx.ConnectError, httpx.HTTPStatusError, httpx.RequestError)):
        return FALLBACK_OLLAMA_UNAVAILABLE
    return FALLBACK_OLLAMA_UNAVAILABLE


async def call_ollama(
    messages: list[dict[str, str]],
    *,
    env: dict[str, str] | None = None,
) -> str:
    values = env or os.environ
    base_url = str(values.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = str(values.get("BATTLEBOT_LLM_MODEL") or values.get("REFEREE_MODEL") or "qwen3:8b")
    timeout = float(values.get("BATTLEBOT_LLM_TIMEOUT_SECONDS") or 60)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": str(values.get("BATTLEBOT_LLM_KEEP_ALIVE") or "30m"),
        "options": {
            "num_predict": int(values.get("BATTLEBOT_LLM_NUM_PREDICT") or 768),
            "temperature": float(values.get("BATTLEBOT_LLM_TEMPERATURE") or 0.1),
            "num_ctx": int(values.get("BATTLEBOT_LLM_NUM_CTX") or 4096),
            "num_thread": int(values.get("BATTLEBOT_LLM_NUM_THREAD") or 8),
        },
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base_url}/api/chat", json=payload)
        response.raise_for_status()
    data = response.json()
    message = data.get("message") or {}
    return str(message.get("content") or data.get("response") or "")


async def judge_fight_packet(
    packet: dict[str, Any],
    smoke_baseline: dict[str, Any] | None = None,
    *,
    env: dict[str, str] | None = None,
    ollama_caller: Any | None = None,
) -> dict[str, Any]:
    smoke = smoke_baseline or smoke_judge_packet(packet)
    if not llm_enabled(env):
        return fallback_decision(smoke, FALLBACK_LLM_DISABLED, "LLM judge disabled; using deterministic fallback.")
    try:
        caller = ollama_caller or call_ollama
        raw = await caller(build_prompt(packet, smoke), env=env)
        return llm_explained_decision(smoke, raw, packet=packet)
    except Exception as exc:  # noqa: BLE001 - judge must degrade cleanly.
        return fallback_decision(
            smoke,
            fallback_reason_for_exception(exc),
            f"LLM referee unavailable; using deterministic explanation. {exc}",
        )


async def async_main(args: argparse.Namespace) -> int:
    async with connect_database(args.database_url) as connection:
        packet = await build_fight_packet(
            connection,
            args.contender_a,
            args.contender_b,
            rules={"llm_enabled": llm_enabled()},
        )
    decision = await judge_fight_packet(packet)
    if args.json:
        print(json.dumps(decision, indent=2, sort_keys=True))
    else:
        print(format_decision(decision))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Nerd Fight Referee LLM judging")
    parser.add_argument("contender_a")
    parser.add_argument("contender_b")
    parser.add_argument("--database-url")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
