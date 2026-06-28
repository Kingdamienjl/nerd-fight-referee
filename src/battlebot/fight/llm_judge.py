"""Local LLM fight judge constrained to the supplied fight packet."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

import httpx

from battlebot.common.db import connect_database
from battlebot.fight.decision_formatter import format_decision
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.profiles.fight_packet import build_fight_packet


FALLBACK_LLM_DISABLED = "LLM disabled"
FALLBACK_OLLAMA_UNAVAILABLE = "Ollama unavailable"
FALLBACK_TIMEOUT = "timeout"
LOCKED_ENGINE_CONFIDENCE = {"high", "strong"}
SYSTEM_PROMPT = (
    "You are the official Nerd Fight Referee. Explain the deterministic engine result using "
    "only the supplied packet evidence. Do not invent feats, forms, equipment, prep time, or "
    "weaknesses."
)
BATTLE_RULES = (
    "Battle rules: standard encounter; no prep unless profile explicitly grants it; strongest "
    "consistent canonical profile from DB; no unsupported claims; evidence packet is source of truth."
)


def llm_enabled(env: dict[str, str] | None = None) -> bool:
    values = env or os.environ
    return str(values.get("BATTLEBOT_LLM_ENABLED") or "").casefold() in {"1", "true", "yes", "on"}


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
            "abilities": contender.get("abilities") or [],
            "equipment": contender.get("equipment") or [],
            "weaknesses": contender.get("weaknesses") or [],
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
            "Explain how the fight unfolds.",
            "Reference supplied evidence naturally.",
            "Write 3-6 concise paragraphs.",
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
        "deciding_factors": smoke.get("deciding_factors") or [],
        "winner_probability": smoke.get("winner_probability"),
        "loser_probability": smoke.get("loser_probability"),
        "overall_probability": smoke.get("overall_probability"),
        "advantage_breakdown": smoke.get("advantage_breakdown") or {},
        "swing_factors": smoke.get("swing_factors") or [],
        "fight_flow": smoke.get("fight_flow") or {},
        "engine_reasoning": smoke.get("engine_reasoning") or [],
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
    engine = engine_verdict(smoke)
    referee = referee_verdict(smoke, raw, explanation[:700], packet=packet)
    decision = {
        **smoke,
        "title": "Nerd Fight Referee Decision",
        "summary": explanation[:700],
        "win_condition": explanation[:700],
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
        "deciding_factors": smoke_baseline.get("deciding_factors") or [],
        "overall_probability": smoke_baseline.get("overall_probability"),
        "winner_probability": smoke_baseline.get("winner_probability"),
        "loser_probability": smoke_baseline.get("loser_probability"),
        "advantage_breakdown": smoke_baseline.get("advantage_breakdown") or {},
        "swing_factors": smoke_baseline.get("swing_factors") or [],
        "fight_flow": smoke_baseline.get("fight_flow") or {},
        "engine_reasoning": smoke_baseline.get("engine_reasoning") or [],
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
        "options": {
            "num_predict": int(values.get("BATTLEBOT_LLM_NUM_PREDICT") or 512),
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
