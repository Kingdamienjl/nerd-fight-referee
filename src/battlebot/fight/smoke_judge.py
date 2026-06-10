"""Deterministic fallback fight smoke judge."""

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

CONFIDENCE_CAPPING_FLAGS = {
    "needs_manual_review",
    "suspicious_low_power_for_known_high_tier",
    "preferred_profile_blocked_phrase",
    "missing_attack",
    "missing_attack_potency",
    "missing_speed",
    "missing_durability",
}
MATCHUP_CAPPING_FLAGS = {
    "suspicious_low_power_for_known_high_tier",
    "preferred_profile_blocked_phrase",
    "missing_attack",
    "missing_attack_potency",
    "missing_speed",
    "missing_durability",
}


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


def item_names(contender: dict[str, Any], section: str, limit: int = 3) -> list[str]:
    names = []
    for item in contender.get(section) or []:
        name = item.get("name") or item.get("id")
        if name:
            names.append(str(name))
    return names[:limit]


def axis_label(axis: str) -> str:
    return {
        "attack_potency": "finishing power",
        "speed": "initiative and spacing",
        "durability": "exchange durability",
        "range": "range control",
    }.get(axis, axis.replace("_", " "))


def tactical_effect(axis: str, winner: dict[str, Any], loser: dict[str, Any]) -> str:
    winner_name = str(winner.get("canonical_name") or "The winner")
    loser_name = str(loser.get("canonical_name") or "the opponent")
    if axis == "attack_potency":
        return (
            f"{winner_name} can turn clean openings into decisive damage, forcing "
            f"{loser_name} to avoid direct exchanges instead of trading."
        )
    if axis == "speed":
        return (
            f"{winner_name} is more likely to act first, control spacing, and punish "
            f"{loser_name} before slower options develop."
        )
    if axis == "durability":
        return (
            f"{winner_name} can absorb more of the listed exchanges, making attrition "
            f"and counterattacks harder for {loser_name}."
        )
    if axis == "range":
        return (
            f"{winner_name} can shape the engagement distance and make {loser_name} "
            "spend actions closing or defending."
        )
    return f"{winner_name} can convert this listed advantage into tactical pressure."


def deciding_factor(axis: str, winner: dict[str, Any], loser: dict[str, Any]) -> dict[str, str]:
    winner_power = winner.get("power_scale") or {}
    loser_power = loser.get("power_scale") or {}
    winner_name = str(winner.get("canonical_name") or "Winner")
    loser_name = str(loser.get("canonical_name") or "Loser")
    return {
        "factor": axis_label(axis).title(),
        "evidence": (
            f"{winner_name} leads {axis}: {winner_power.get(axis) or 'n/a'} "
            f"vs {loser_name}: {loser_power.get(axis) or 'n/a'}"
        ),
        "tactical_effect": tactical_effect(axis, winner, loser),
    }


def ability_factor(winner: dict[str, Any]) -> dict[str, str] | None:
    names = item_names(winner, "abilities")
    if not names:
        return None
    winner_name = str(winner.get("canonical_name") or "The winner")
    return {
        "factor": "Listed ability pressure",
        "evidence": f"{winner_name} has listed abilities: {', '.join(names)}",
        "tactical_effect": (
            f"{winner_name} has more than raw stats in the packet and can use listed "
            "abilities to create openings. No unlisted feats are assumed."
        ),
    }


def quality_notes(packet: dict[str, Any]) -> list[str]:
    notes = []
    for warning in packet.get("warnings") or []:
        flag = warning.get("flag")
        contender = warning.get("contender")
        if flag:
            notes.append(f"{contender}: {flag}")
    return notes


def warning_contender_matches(warning: dict[str, Any], contender: dict[str, Any], label: str) -> bool:
    target = str(warning.get("contender") or "")
    return target in {
        label,
        str(contender.get("character_id") or ""),
        str(contender.get("canonical_name") or ""),
    }


def winner_capping_warnings(packet: dict[str, Any], winner: dict[str, Any], winner_label: str) -> list[str]:
    flags = []
    for warning in packet.get("warnings") or []:
        flag = str(warning.get("flag") or "")
        if flag in CONFIDENCE_CAPPING_FLAGS and warning_contender_matches(warning, winner, winner_label):
            flags.append(flag)
    return flags


def matchup_capping_warnings(packet: dict[str, Any]) -> list[str]:
    return [
        str(warning.get("flag") or "")
        for warning in packet.get("warnings") or []
        if str(warning.get("flag") or "") in MATCHUP_CAPPING_FLAGS
    ]


def smoke_judge_packet(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("errors"):
        return {
            "label": "Nerd Fight Referee Decision - fallback mode",
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
            deciding.append(deciding_factor(axis, a, b))
        elif right > left:
            score_total -= 1
            deciding.append(deciding_factor(axis, b, a))
    notes = quality_notes(packet)
    if parsed < 2 or score_total == 0:
        return {
            "label": "Nerd Fight Referee Decision - fallback mode",
            "winner": "needs_judge_review",
            "confidence": "low",
            "verdict_type": "needs_judge_review",
            "deciding_factors": deciding,
            "warnings": ["tier parsing was insufficient for a deterministic smoke winner"],
            "profile_quality_notes": notes,
        }
    winner_label = "contender_a" if score_total > 0 else "contender_b"
    winner = a if score_total > 0 else b
    loser = b if score_total > 0 else a
    axis_leads = abs(score_total)
    confidence = "strong" if parsed == 3 and axis_leads == 3 else "medium" if axis_leads >= 2 else "low"
    warnings = []
    capping_warnings = winner_capping_warnings(packet, winner, winner_label) or matchup_capping_warnings(packet)
    if capping_warnings:
        confidence = "low_to_medium" if confidence in {"strong", "medium"} else "low"
        warnings.append("profile quality warnings lowered confidence")
    factor = ability_factor(winner)
    if factor:
        deciding.append(factor)
    return {
        "label": "Nerd Fight Referee Decision - fallback mode",
        "winner": winner["canonical_name"],
        "winner_character_id": winner["character_id"],
        "confidence": confidence,
        "verdict_type": "smoke_test_decision",
        "summary": (
            f"{winner['canonical_name']} has the clearer packet-backed route over "
            f"{loser['canonical_name']} in this deterministic fallback."
        ),
        "win_condition": (
            f"{winner['canonical_name']} wins by converting the listed stat leads into "
            "initiative, damage pressure, and survivable exchanges."
        ),
        "loser_best_path": (
            f"{loser['canonical_name']} needs to exploit listed weaknesses or abilities "
            "not covered by the core stat comparison; missing evidence limits confidence."
        ),
        "deciding_factors": deciding,
        "warnings": warnings,
        "profile_quality_notes": notes,
    }


def format_smoke_summary(result: dict[str, Any]) -> str:
    lines = [result["label"], f"winner: {result.get('winner')}", f"confidence: {result.get('confidence')}"]
    if result.get("summary"):
        lines.append(f"summary: {result['summary']}")
    if result.get("win_condition"):
        lines.append(f"win_condition: {result['win_condition']}")
    if result.get("deciding_factors"):
        lines.append("deciding_factors:")
        for factor in result["deciding_factors"][:6]:
            if isinstance(factor, dict):
                lines.append(f"- {factor.get('factor')}: {factor.get('tactical_effect')}")
            else:
                lines.append(f"- {factor}")
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
