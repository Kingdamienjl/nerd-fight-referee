"""Deterministic pre-LLM fight smoke judge."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet


TIER_PHRASES: tuple[tuple[str, int], ...] = (
    ("outerversal", 130),
    ("hyperversal", 120),
    ("multiversal", 110),
    ("universal", 100),
    ("galaxy", 90),
    ("multi-solar system", 86),
    ("solar system", 84),
    ("star", 80),
    ("planet", 70),
    ("moon", 65),
    ("continent", 60),
    ("country", 55),
    ("island", 50),
    ("mountain", 45),
    ("city", 40),
    ("town", 35),
    ("building", 25),
    ("wall", 20),
    ("street", 10),
    ("human", 8),
)

SPEED_PHRASES: tuple[tuple[str, int], ...] = (
    ("immeasurable", 120),
    ("infinite", 115),
    ("massively ftl+", 105),
    ("massively faster than light", 100),
    ("ftl", 90),
    ("relativistic", 80),
    ("light", 75),
    ("hypersonic", 55),
    ("supersonic", 45),
    ("subsonic", 30),
    ("peak human", 20),
    ("human", 10),
)


def text_rank(value: str | None, *, speed: bool = False) -> int | None:
    if not value:
        return None
    normalized = re.sub(r"[^a-z0-9+ -]", " ", value.casefold())
    phrases = SPEED_PHRASES if speed else TIER_PHRASES
    for phrase, rank in phrases:
        if phrase in normalized:
            return rank
    return None


def contender_scores(contender: dict[str, Any]) -> dict[str, int | None]:
    power = contender.get("power_scale") or {}
    return {
        "attack_potency": text_rank(power.get("attack_potency")),
        "speed": text_rank(power.get("speed"), speed=True),
        "durability": text_rank(power.get("durability")),
    }


def quality_notes(packet: dict[str, Any]) -> list[str]:
    notes = []
    for warning in packet.get("warnings") or []:
        flag = warning.get("flag")
        contender = warning.get("contender")
        if flag:
            notes.append(f"{contender}: {flag}")
    return notes


def smoke_judge_packet(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("errors"):
        return {
            "label": "Smoke Test Decision - deterministic pre-LLM result",
            "winner": None,
            "confidence": "none",
            "verdict_type": "needs_judge_review",
            "deciding_factors": [],
            "warnings": ["fight packet has resolution errors"],
            "profile_quality_notes": quality_notes(packet),
        }

    a = packet["contender_a"]
    b = packet["contender_b"]
    scores_a = contender_scores(a)
    scores_b = contender_scores(b)
    deciding = []
    score_total = 0
    parsed = 0
    for axis in ("attack_potency", "speed", "durability"):
        left = scores_a[axis]
        right = scores_b[axis]
        if left is None or right is None:
            continue
        parsed += 1
        if left > right:
            score_total += 1
            deciding.append(f"{a['canonical_name']} leads {axis}")
        elif right > left:
            score_total -= 1
            deciding.append(f"{b['canonical_name']} leads {axis}")
    notes = quality_notes(packet)
    if parsed < 2 or score_total == 0:
        return {
            "label": "Smoke Test Decision - deterministic pre-LLM result",
            "winner": "needs_judge_review",
            "confidence": "low",
            "verdict_type": "needs_judge_review",
            "deciding_factors": deciding,
            "warnings": ["tier parsing was insufficient for a deterministic smoke winner"],
            "profile_quality_notes": notes,
        }
    winner = a if score_total > 0 else b
    confidence = "medium" if abs(score_total) >= 2 else "low"
    warnings = []
    if notes:
        confidence = "low_to_medium" if confidence == "medium" else "low"
        warnings.append("profile quality warnings lowered confidence")
    return {
        "label": "Smoke Test Decision - deterministic pre-LLM result",
        "winner": winner["canonical_name"],
        "winner_character_id": winner["character_id"],
        "confidence": confidence,
        "verdict_type": "smoke_test_decision",
        "deciding_factors": deciding,
        "warnings": warnings,
        "profile_quality_notes": notes,
    }


def format_smoke_summary(result: dict[str, Any]) -> str:
    lines = [result["label"], f"winner: {result.get('winner')}", f"confidence: {result.get('confidence')}"]
    if result.get("deciding_factors"):
        lines.append("deciding_factors:")
        lines.extend(f"- {factor}" for factor in result["deciding_factors"][:6])
    if result.get("warnings"):
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in result["warnings"][:6])
    if result.get("profile_quality_notes"):
        lines.append("profile_quality_notes:")
        lines.extend(f"- {note}" for note in result["profile_quality_notes"][:6])
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> int:
    async with connect_database(args.database_url) as connection:
        packet = await build_fight_packet(connection, args.contender_a, args.contender_b, rules={"smoke": True})
    result = smoke_judge_packet(packet)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_smoke_summary(result))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic pre-LLM smoke judging")
    parser.add_argument("contender_a")
    parser.add_argument("contender_b")
    parser.add_argument("--database-url")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
