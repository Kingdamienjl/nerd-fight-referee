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


VALID_CONFIDENCE = {"low", "low_to_medium", "medium", "high", "strong", "needs_judge_review"}
CONFLICT_NOTE = "judge_conflict: LLM contradicted deterministic baseline without packet evidence"
SYSTEM_PROMPT = (
    "You are Nerd Fight Referee. Decide only from the supplied packet. Do not invent feats, "
    "forms, equipment, prep time, or weaknesses. Explain how the winner turns the listed "
    "advantages into an actual fight plan."
)
BATTLE_RULES = (
    "Battle rules: standard encounter; no prep unless profile explicitly grants it; strongest "
    "consistent canonical profile from DB; no unsupported claims; evidence packet is source of truth."
)


def llm_enabled(env: dict[str, str] | None = None) -> bool:
    values = env or os.environ
    return str(values.get("BATTLEBOT_LLM_ENABLED") or "").casefold() == "true"


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
    user_prompt = "\n".join(
        [
            BATTLE_RULES,
            "Return only JSON with this schema:",
            json.dumps(
                {
                    "title": "Nerd Fight Referee Decision",
                    "winner": "string",
                    "confidence": "low|low_to_medium|medium|high|strong|needs_judge_review",
                    "summary": "2-4 sentence plain-English matchup summary",
                    "win_condition": "how the winner actually wins",
                    "loser_best_path": "how the loser could plausibly threaten or upset",
                    "deciding_factors": [
                        {
                            "factor": "Range control",
                            "evidence": "Packet-backed evidence only",
                            "tactical_effect": "How this changes the fight",
                        }
                    ],
                    "warnings": ["..."],
                    "judge_notes": ["..."],
                }
            ),
            "Evidence packet:",
            json.dumps(evidence, sort_keys=True),
        ]
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]


def parse_json_response(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM response JSON was not an object")
    return data


def normalize_decision(data: dict[str, Any]) -> dict[str, Any]:
    factors = data.get("deciding_factors") or []
    normalized_factors = []
    for factor in factors:
        if isinstance(factor, dict):
            normalized_factors.append(
                {
                    "factor": str(factor.get("factor") or "Deciding factor"),
                    "evidence": str(factor.get("evidence") or ""),
                    "tactical_effect": str(factor.get("tactical_effect") or ""),
                }
            )
    confidence = str(data.get("confidence") or "needs_judge_review")
    if confidence not in VALID_CONFIDENCE:
        confidence = "needs_judge_review"
    return {
        "title": "Nerd Fight Referee Decision",
        "winner": str(data.get("winner") or "needs_judge_review"),
        "confidence": confidence,
        "summary": str(data.get("summary") or "The supplied packet did not support a complete LLM decision."),
        "win_condition": str(data.get("win_condition") or "Evidence is incomplete."),
        "loser_best_path": str(data.get("loser_best_path") or "Evidence is incomplete."),
        "deciding_factors": normalized_factors,
        "warnings": [str(item) for item in data.get("warnings") or []],
        "judge_notes": [str(item) for item in data.get("judge_notes") or []],
    }


def fallback_decision(smoke_baseline: dict[str, Any], note: str) -> dict[str, Any]:
    return {
        "title": "Nerd Fight Referee Decision - fallback mode",
        "winner": smoke_baseline.get("winner"),
        "confidence": smoke_baseline.get("confidence") or "needs_judge_review",
        "summary": smoke_baseline.get("summary") or "LLM judge unavailable; using deterministic fallback.",
        "win_condition": smoke_baseline.get("win_condition") or "Fallback uses packet-backed stat leads.",
        "loser_best_path": smoke_baseline.get("loser_best_path") or "Evidence is incomplete.",
        "deciding_factors": smoke_baseline.get("deciding_factors") or [],
        "warnings": list(smoke_baseline.get("warnings") or []),
        "judge_notes": [note, *list(smoke_baseline.get("profile_quality_notes") or [])],
    }


def validate_against_smoke(decision: dict[str, Any], smoke_baseline: dict[str, Any]) -> dict[str, Any]:
    smoke_winner = smoke_baseline.get("winner")
    llm_winner = decision.get("winner")
    if smoke_winner and smoke_winner != "needs_judge_review" and llm_winner != smoke_winner:
        fallback = fallback_decision(smoke_baseline, CONFLICT_NOTE)
        fallback["warnings"].append("judge_conflict")
        return fallback
    return decision


async def call_ollama(
    messages: list[dict[str, str]],
    *,
    env: dict[str, str] | None = None,
) -> str:
    values = env or os.environ
    base_url = str(values.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
    model = str(values.get("BATTLEBOT_LLM_MODEL") or "llama3.1")
    timeout = float(values.get("BATTLEBOT_LLM_TIMEOUT_SECONDS") or 60)
    payload = {"model": model, "messages": messages, "stream": False, "format": "json"}
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
        return fallback_decision(smoke, "LLM judge disabled; using deterministic fallback.")
    try:
        caller = ollama_caller or call_ollama
        raw = await caller(build_prompt(packet, smoke), env=env)
        decision = normalize_decision(parse_json_response(raw))
    except Exception as exc:  # noqa: BLE001 - judge must degrade cleanly.
        return fallback_decision(smoke, f"LLM judge unavailable; using deterministic fallback. {exc}")
    return validate_against_smoke(decision, smoke)


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
