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
TACTICAL_CATEGORIES = (
    "Range Control",
    "Mobility / Initiative",
    "Finishing Power",
    "Durability / Attrition",
    "Special Abilities",
    "Resistance / Counterplay",
    "Skill / Tactics",
    "Prep Dependence",
    "Weakness Exploitation",
    "Battlefield Control",
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


def item_names(contender: dict[str, Any], section: str, limit: int = 3) -> list[str]:
    names = []
    for item in contender.get(section) or []:
        name = item.get("name") or item.get("id")
        if name:
            names.append(str(name))
    return names[:limit]


def axis_label(axis: str) -> str:
    return {
        "attack_potency": "Finishing Power",
        "speed": "Mobility / Initiative",
        "durability": "Durability / Attrition",
        "range": "Range Control",
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
    winner_name = str(winner.get("canonical_name") or "Winner")
    loser_name = str(loser.get("canonical_name") or "Loser")
    return {
        "factor": axis_label(axis).title(),
        "evidence": f"{winner_name} leads {axis_label(axis).casefold()} over {loser_name} in the packet.",
        "tactical_effect": tactical_effect(axis, winner, loser),
    }


def ability_factor(winner: dict[str, Any]) -> dict[str, str] | None:
    names = item_names(winner, "abilities")
    if not names:
        return None
    winner_name = str(winner.get("canonical_name") or "The winner")
    return {
        "factor": "Special Abilities",
        "evidence": f"{winner_name} has listed abilities: {', '.join(names)}",
        "tactical_effect": (
            f"{winner_name} has more than raw stats in the packet and can use listed "
            "abilities to create openings. No unlisted feats are assumed."
        ),
    }


def tactical_value(contender: dict[str, Any], key: str) -> Any:
    tactical = contender.get("tactical_profile") if isinstance(contender.get("tactical_profile"), dict) else {}
    return contender.get(key) or tactical.get(key)


def compact_names(values: Any, *, limit: int = 3) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        return [values]
    names = []
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                name = item.get("name") or item.get("id") or item.get("description")
            else:
                name = item
            if name:
                names.append(str(name))
    return names[:limit]


def structured_factor(winner: dict[str, Any], loser: dict[str, Any]) -> dict[str, str] | None:
    winner_name = str(winner.get("canonical_name") or "Winner")
    loser_name = str(loser.get("canonical_name") or "Loser")
    battlefield = tactical_value(winner, "battlefield_control")
    if battlefield:
        return {
            "factor": "Battlefield Control",
            "evidence": f"{winner_name} has packet battlefield-control notes.",
            "tactical_effect": (
                f"{winner_name} can shape positioning or engagement terms instead of letting "
                f"{loser_name} fight on preferred timing."
            ),
        }
    counters = compact_names(tactical_value(winner, "counters"))
    if counters:
        return {
            "factor": "Resistance / Counterplay",
            "evidence": f"{winner_name} has listed counterplay: {', '.join(counters)}",
            "tactical_effect": f"{winner_name} has an explicit packet route for blunting {loser_name}'s best tools.",
        }
    intelligence = tactical_value(winner, "tactical_intelligence")
    style = tactical_value(winner, "combat_style")
    if intelligence or style:
        return {
            "factor": "Skill / Tactics",
            "evidence": f"{winner_name} has packet tactical notes.",
            "tactical_effect": f"{winner_name} can choose exchanges more deliberately and avoid low-value trades.",
        }
    forms = compact_names(tactical_value(winner, "forms"))
    if forms:
        return {
            "factor": "Special Abilities",
            "evidence": f"{winner_name} has listed form access: {', '.join(forms)}",
            "tactical_effect": f"{winner_name} has escalation options in the packet if the opening exchange stalls.",
        }
    return None


def route_to_victory(winner: dict[str, Any], loser: dict[str, Any], factors: list[dict[str, str]]) -> str:
    winner_name = str(winner.get("canonical_name") or "Winner")
    loser_name = str(loser.get("canonical_name") or "Loser")
    factor_names = [str(factor.get("factor") or "") for factor in factors]
    structured_win = compact_names(tactical_value(winner, "win_conditions") or tactical_value(winner, "matchup_notes"), limit=1)
    if structured_win:
        return f"{winner_name} wins by playing toward the listed win condition: {structured_win[0]}"
    if "Battlefield Control" in factor_names or "Range Control" in factor_names:
        return f"{winner_name} wins by controlling distance and engagement terms until {loser_name} is forced into bad trades."
    if "Mobility / Initiative" in factor_names and "Finishing Power" in factor_names:
        return f"{winner_name} wins by taking first meaningful action, forcing reactions, then cashing in the higher output edge."
    if "Durability / Attrition" in factor_names:
        return f"{winner_name} wins by surviving the exchange pattern longer and turning repeated counters into attrition."
    if "Skill / Tactics" in factor_names:
        return f"{winner_name} wins by steering the matchup through cleaner decisions, timing, and packet-backed tactics."
    if "Special Abilities" in factor_names:
        return f"{winner_name} wins by using listed abilities to create the opening that raw stats alone do not describe."
    return f"{winner_name} has the clearer packet-backed route over {loser_name}."


def loser_path(loser: dict[str, Any], winner: dict[str, Any]) -> str:
    loser_name = str(loser.get("canonical_name") or "Loser")
    winner_name = str(winner.get("canonical_name") or "Winner")
    loss_conditions = compact_names(tactical_value(winner, "losing_conditions") or tactical_value(winner, "loss_conditions"), limit=1)
    if loss_conditions:
        return f"{loser_name} needs to force the listed failure case: {loss_conditions[0]}"
    weaknesses = item_names(winner, "weaknesses", limit=2)
    if weaknesses:
        return f"{loser_name} needs to exploit listed weaknesses such as {', '.join(weaknesses)} before {winner_name}'s main route stabilizes."
    return f"{loser_name} needs a listed counter, weakness exploit, or matchup-specific angle not resolved by the core packet comparison."


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
            "label": "Nerd Fight Referee Decision",
            "winner": None,
            "confidence": "none",
            "verdict_type": "needs_judge_review",
            "deciding_factors": [],
            "warnings": ["fight packet has resolution errors"],
            "profile_quality_notes": quality_notes(packet),
            "diagnostics": {"fallback": True, "fallback_reason": "resolution_error"},
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
            "label": "Nerd Fight Referee Decision",
            "winner": "needs_judge_review",
            "confidence": "low",
            "verdict_type": "needs_judge_review",
            "deciding_factors": deciding,
            "warnings": ["tier parsing was insufficient for a deterministic smoke winner"],
            "profile_quality_notes": notes,
            "diagnostics": {"fallback": True, "fallback_reason": "insufficient_packet_ranking"},
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
    factor = structured_factor(winner, loser)
    if factor:
        deciding.insert(0, factor)
    route = route_to_victory(winner, loser, deciding)
    return {
        "label": "Nerd Fight Referee Decision",
        "winner": winner["canonical_name"],
        "winner_character_id": winner["character_id"],
        "confidence": confidence,
        "verdict_type": "smoke_test_decision",
        "summary": (
            f"{winner['canonical_name']} has the clearer packet-backed route over "
            f"{loser['canonical_name']} from the supplied packet."
        ),
        "win_condition": route,
        "loser_best_path": loser_path(loser, winner),
        "deciding_factors": deciding,
        "warnings": warnings,
        "profile_quality_notes": notes,
        "diagnostics": {"fallback": True, "fallback_reason": "deterministic_smoke_judge"},
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
