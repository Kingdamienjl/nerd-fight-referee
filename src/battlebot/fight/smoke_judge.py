"""Deterministic fallback fight smoke judge."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

from battlebot.common.db import connect_database
from battlebot.fight.decision_formatter import sanitize_fight_card_item
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
NON_PHYSICAL_TERMS = (
    "magic",
    "spell",
    "purification",
    "healing",
    "barrier",
    "energy projection",
    "telepathy",
    "telekinesis",
    "reality warping",
    "soul manipulation",
    "transformation",
    "time manipulation",
    "sealing",
    "elemental",
    "ranged",
    "cosmic",
)
PHYSICAL_ONLY_TERMS = ("superhuman physical characteristics", "enhanced strength", "martial arts")


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


def contender_name(contender: dict[str, Any]) -> str:
    return str(contender.get("canonical_name") or contender.get("character_id") or "unknown")


def probability_for_confidence(confidence: str) -> float:
    return {
        "strong": 0.85,
        "medium": 0.7,
        "low_to_medium": 0.62,
        "low": 0.55,
    }.get(confidence, 0.5)


def margin_label(left: int | None, right: int | None) -> str:
    if left is None or right is None:
        return "low"
    diff = abs(left - right)
    if diff >= 30:
        return "high"
    if diff >= 15:
        return "medium"
    return "low"


def margin_from_presence(left: int, right: int) -> str:
    if left == right:
        return "low"
    if max(left, right) >= 3:
        return "high"
    if max(left, right) >= 2:
        return "medium"
    return "low"


def compact_value(value: Any) -> str:
    names = compact_names(value, limit=2)
    if names:
        return ", ".join(names)
    return str(value).strip() if value else "no listed packet entry"


def reason_margin_word(margin: str) -> str:
    return {"high": "substantially", "medium": "clearly"}.get(margin, "slightly")


def category_reason(category: str, winner: str, loser: str, margin: str) -> str:
    degree = reason_margin_word(margin)
    if category == "speed":
        return f"{winner} controls initiative because their listed speed tier {degree} exceeds {loser}'s."
    if category == "strength":
        return f"{winner} threatens the cleaner finish because their listed output {degree} exceeds {loser}'s."
    if category == "durability":
        return f"{winner} has the durability edge because {loser} must keep landing meaningful damage without being punished."
    if category == "mobility":
        return f"{winner} is better positioned to set the pace and deny {loser} stable engagement timing."
    if category == "range":
        return f"{winner} has the range edge because they can force {loser} to spend more effort entering safely."
    if category == "skill":
        return f"{winner} has the skill edge because their listed tactics give them cleaner decision points."
    if category == "abilities":
        return f"{winner} has the abilities edge because their named tools create more reliable win conditions."
    if category == "battlefield":
        return f"{winner} controls battlefield terms because their listed tools better shape positioning."
    return f"{winner} has the {category} edge because it creates more reliable fight pressure than {loser}'s route."


def ranked_factor(
    label: str,
    a: dict[str, Any],
    b: dict[str, Any],
    left: int | None,
    right: int | None,
    left_value: Any,
    right_value: Any,
    *,
    scoring: bool = False,
) -> dict[str, str]:
    if left is None or right is None:
        winner = "unknown"
        reason = (
            f"{label.title()} remains uncertain because the deterministic judge could not rank both sides cleanly."
        )
    elif left > right:
        winner = contender_name(a)
        reason = category_reason(label, winner, contender_name(b), margin_label(left, right))
    elif right > left:
        winner = contender_name(b)
        reason = category_reason(label, winner, contender_name(a), margin_label(left, right))
    else:
        winner = "even"
        reason = (
            f"{label.title()} does not create a decisive edge because both sides occupy the same listed tier."
        )
    return {"winner": winner, "margin": margin_label(left, right), "reason": reason}


def text_presence_factor(label: str, a: dict[str, Any], b: dict[str, Any], a_value: Any, b_value: Any) -> dict[str, str]:
    left = 1 if a_value else 0
    right = 1 if b_value else 0
    factor = ranked_factor(label, a, b, left, right, a_value, b_value)
    factor["margin"] = margin_from_presence(left, right)
    return factor


def ability_count_factor(a: dict[str, Any], b: dict[str, Any]) -> dict[str, str]:
    abilities_a = a.get("abilities") or []
    abilities_b = b.get("abilities") or []
    left = len(abilities_a)
    right = len(abilities_b)
    factor = ranked_factor("abilities", a, b, left, right, abilities_a, abilities_b)
    factor["margin"] = margin_from_presence(left, right)
    return factor


def advantage_breakdown(a: dict[str, Any], b: dict[str, Any], scores_a: dict[str, int | None], scores_b: dict[str, int | None]) -> dict[str, dict[str, str]]:
    power_a = a.get("power_scale") or {}
    power_b = b.get("power_scale") or {}
    return {
        "speed": ranked_factor(
            "speed",
            a,
            b,
            scores_a.get("speed"),
            scores_b.get("speed"),
            power_a.get("speed"),
            power_b.get("speed"),
            scoring=True,
        ),
        "strength": ranked_factor(
            "strength",
            a,
            b,
            scores_a.get("attack_potency"),
            scores_b.get("attack_potency"),
            power_a.get("attack_potency"),
            power_b.get("attack_potency"),
            scoring=True,
        ),
        "durability": ranked_factor(
            "durability",
            a,
            b,
            scores_a.get("durability"),
            scores_b.get("durability"),
            power_a.get("durability"),
            power_b.get("durability"),
            scoring=True,
        ),
        "range": text_presence_factor("range", a, b, power_a.get("range"), power_b.get("range")),
        "mobility": ranked_factor(
            "mobility",
            a,
            b,
            scores_a.get("speed"),
            scores_b.get("speed"),
            power_a.get("speed"),
            power_b.get("speed"),
        ),
        "skill": text_presence_factor(
            "skill",
            a,
            b,
            tactical_value(a, "tactical_intelligence") or tactical_value(a, "combat_style"),
            tactical_value(b, "tactical_intelligence") or tactical_value(b, "combat_style"),
        ),
        "abilities": ability_count_factor(a, b),
        "battlefield": text_presence_factor(
            "battlefield",
            a,
            b,
            tactical_value(a, "battlefield_control"),
            tactical_value(b, "battlefield_control"),
        ),
    }


def swing_factors_from_breakdown(breakdown: dict[str, dict[str, str]], winner_name: str) -> list[dict[str, str]]:
    swings = []
    for factor_name, factor in breakdown.items():
        if factor.get("winner") == winner_name:
            title = factor_name.replace("_", " ").title()
            margin = factor.get("margin") or "low"
            swings.append(
                {
                    "title": title,
                    "reason": factor.get("reason") or f"{title} favors {winner_name} in the packet.",
                    "impact": (
                        f"{winner_name} has a {margin} {factor_name} edge, so this factor helps explain "
                        "the deterministic verdict without changing the scoring calculation."
                    ),
                }
            )
    return swings[:4]


def empty_fight_flow() -> dict[str, list[dict[str, str]]]:
    return {"opening": [], "pressure": [], "counterplay": [], "adaptation": [], "finish": [], "loser_path": []}


def flow_item(winner: str, reason: str) -> dict[str, str]:
    return {"winner": winner, "reason": reason}


def first_breakdown_reason(
    breakdown: dict[str, dict[str, str]],
    winner_name: str,
    categories: tuple[str, ...],
) -> str:
    for category in categories:
        factor = breakdown.get(category) or {}
        if factor.get("winner") == winner_name and factor.get("reason"):
            return str(factor["reason"])
    return ""


def first_deciding_effect(factors: list[dict[str, str]], keywords: tuple[str, ...] = ()) -> str:
    for factor in factors:
        effect = str(factor.get("tactical_effect") or "").strip()
        factor_name = str(factor.get("factor") or "").casefold()
        if effect and (not keywords or any(keyword in factor_name for keyword in keywords)):
            return effect
    return ""


def build_fight_flow(
    winner_name: str,
    loser_name: str,
    deciding_factors: list[dict[str, str]],
    breakdown: dict[str, dict[str, str]],
    swing_factors: list[dict[str, str]],
    loser_best_path: str,
) -> dict[str, list[dict[str, str]]]:
    flow = empty_fight_flow()
    opening = first_breakdown_reason(breakdown, winner_name, ("speed", "mobility", "range"))
    if not opening:
        opening = first_deciding_effect(deciding_factors, ("initiative", "mobility", "range"))
    flow["opening"].append(flow_item(winner_name, opening or f"{winner_name} establishes the first reliable tempo edge."))

    pressure = first_breakdown_reason(breakdown, winner_name, ("skill", "abilities", "battlefield", "range"))
    if not pressure:
        pressure = first_deciding_effect(deciding_factors, ("skill", "ability", "battlefield", "range"))
    flow["pressure"].append(flow_item(winner_name, pressure or f"{winner_name} forces {loser_name} to defend before setting offense."))

    flow["counterplay"].append(flow_item(loser_name, loser_best_path))

    swing = swing_factors[0] if swing_factors else {}
    adaptation = str(swing.get("impact") or swing.get("reason") or "").strip()
    flow["adaptation"].append(
        flow_item(winner_name, adaptation or f"{winner_name} adapts by leaning on the strongest confirmed matchup edge.")
    )

    finish = first_deciding_effect(deciding_factors, ("finishing", "power", "durability", "ability"))
    if not finish:
        finish = f"{winner_name} finishes once {loser_name} is pinned, staggered, or out of reliable answers."
    flow["finish"].append(flow_item(winner_name, finish))
    flow["loser_path"].append(flow_item(loser_name, loser_best_path))
    return flow


def engine_reasoning_from_flow(fight_flow: dict[str, list[dict[str, str]]]) -> list[str]:
    reasoning = []
    for phase in ("opening", "pressure", "counterplay", "adaptation", "finish", "loser_path"):
        for item in fight_flow.get(phase) or []:
            reason = str(item.get("reason") or "").strip()
            if reason:
                reasoning.append(reason)
    return reasoning[:6]


def item_names(contender: dict[str, Any], section: str, limit: int = 3) -> list[str]:
    names = []
    for item in contender.get(section) or []:
        name = item.get("name") or item.get("id")
        if name:
            cleaned = sanitize_fight_card_item(clean_strategy_fragment(str(name)))
            if cleaned:
                names.append(cleaned)
    return names[:limit]


def clean_strategy_fragment(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"\{\{[^{}\n]*(?:\n[^{}]*)?\}\}", "", text)
    text = re.sub(r"\{\{.*?$|\}\}|\|", " ", text)
    text = re.sub(r"\b(?:tag:|tabber|Border|Content)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:No|Yes)\b(?:\s*•\s*\b(?:No|Yes|Content)\b)+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPart\s+[IVXLC]+\s*=\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bNotable Attacks/Techniques\s*:?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:Weaknesses|Weakness|Abilities|Equipment|Powers?)\s*:", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[A-Z][A-Za-z .'-]{1,40}=\s*", "", text)
    text = re.sub(r"^\s*\d+\s*(?:&\s*\d+)?\)\s*", "", text)
    text = re.sub(r"\b(his|her|their),\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" -:=,;\n\t")
    return text


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
            f"{winner_name} can punish a stagger or pinned guard hard enough that "
            f"{loser_name} cannot afford prolonged direct trades."
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
    winner_value = clean_strategy_fragment(str((winner.get("power_scale") or {}).get(axis) or ""))
    loser_value = clean_strategy_fragment(str((loser.get("power_scale") or {}).get(axis) or ""))
    evidence = f"{winner_name} leads {axis_label(axis).casefold()} over {loser_name} in the packet."
    if winner_value and loser_value:
        evidence = (
            f"{winner_name} leads {axis_label(axis).casefold()}: listed as {winner_value} "
            f"against {loser_name}'s {loser_value}."
        )
    return {
        "factor": axis_label(axis).title(),
        "evidence": evidence,
        "tactical_effect": tactical_effect(axis, winner, loser),
    }


def ability_factor(winner: dict[str, Any]) -> dict[str, str] | None:
    names = item_names(winner, "abilities")
    if not names:
        return None
    winner_name = str(winner.get("canonical_name") or "The winner")
    return {
        "factor": "Special Abilities",
        "evidence": f"{winner_name} brings named tools: {', '.join(names)}",
        "tactical_effect": (
            f"{winner_name} can build a fight plan around {', '.join(names)} instead of relying only "
            "on raw stat pressure. No unlisted feats are assumed."
        ),
    }


def tactical_value(contender: dict[str, Any], key: str) -> Any:
    tactical = contender.get("tactical_profile") if isinstance(contender.get("tactical_profile"), dict) else {}
    return contender.get(key) or tactical.get(key)


def compact_names(values: Any, *, limit: int = 3) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        cleaned = sanitize_fight_card_item(clean_strategy_fragment(values))
        return [cleaned] if cleaned else []
    names = []
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict):
                name = item.get("name") or item.get("id") or item.get("description")
            else:
                name = item
            if name:
                cleaned = sanitize_fight_card_item(clean_strategy_fragment(str(name)))
                if cleaned:
                    names.append(cleaned)
    return names[:limit]


def nested_value(mapping: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> Any:
    for path in paths:
        value: Any = mapping
        for key in path:
            if not isinstance(value, dict) or key not in value:
                value = None
                break
            value = value.get(key)
        if value not in (None, ""):
            return value
    return None


def physical_line(contender: dict[str, Any]) -> str:
    height = clean_strategy_fragment(
        str(
            nested_value(
                contender,
                (
                    ("height",),
                    ("physical_profile", "height"),
                    ("stats", "height"),
                    ("bio", "height"),
                ),
            )
            or ""
        )
    )
    weight = clean_strategy_fragment(
        str(
            nested_value(
                contender,
                (
                    ("weight",),
                    ("physical_profile", "weight"),
                    ("stats", "weight"),
                    ("bio", "weight"),
                ),
            )
            or ""
        )
    )
    if height and weight:
        return f"{height} / {weight}"
    return height or weight


def weapon_power_choice(contender: dict[str, Any]) -> list[str]:
    weapons = compact_names(
        contender.get("weapon_of_choice")
        or contender.get("weapons")
        or contender.get("equipment")
        or tactical_value(contender, "weapon_of_choice"),
        limit=2,
    )
    if weapons:
        return weapons
    powers = compact_names(
        contender.get("power_of_choice")
        or contender.get("powers")
        or contender.get("abilities")
        or tactical_value(contender, "power_of_choice")
        or tactical_value(contender, "power_source"),
        limit=2,
    )
    return powers


def combined_clean_terms(contender: dict[str, Any], *, limit: int = 20) -> list[str]:
    terms: list[str] = []
    for key in (
        "abilities",
        "powers",
        "special_abilities",
        "equipment",
        "weapons",
        "magic",
        "forms",
        "transformations",
        "techniques",
        "weaknesses",
    ):
        terms.extend(compact_names(contender.get(key) or tactical_value(contender, key), limit=limit))
    for key in (
        "power_source",
        "combat_style",
        "fighting_style",
        "personality",
        "summary",
        "description",
        "notes",
        "win_conditions",
        "loss_conditions",
    ):
        value = contender.get(key) or tactical_value(contender, key)
        if value:
            terms.extend(compact_names(value, limit=3))
    deduped: list[str] = []
    seen = set()
    for term in terms:
        normalized = term.casefold()
        if normalized not in seen:
            seen.add(normalized)
            deduped.append(term)
    return deduped[:limit]


def non_physical_options(contender: dict[str, Any]) -> list[str]:
    options = []
    for term in combined_clean_terms(contender, limit=30):
        normalized = term.casefold()
        if any(marker in normalized for marker in NON_PHYSICAL_TERMS):
            options.append(term)
    return options[:6]


def combat_mode(contender: dict[str, Any]) -> str:
    terms = " ".join(combined_clean_terms(contender, limit=30)).casefold()
    if any(marker in terms for marker in ("reality warping", "time manipulation", "cosmic", "silver crystal", "soul manipulation")):
        return "cosmic/reality hax user"
    if any(marker in terms for marker in ("magic", "spell", "purification", "healing", "barrier", "transformation")):
        return "magic user"
    if any(marker in terms for marker in ("energy projection", "ranged", "beam", "blast")):
        return "ranged energy user"
    if any(marker in terms for marker in ("weapon", "sword", "axe", "claws", "gun", "staff", "rod")):
        return "weapon specialist"
    if any(marker in terms for marker in ("tech", "armor", "gadget")):
        return "tech user"
    if any(marker in terms for marker in ("martial", "combat style", "hand to hand")):
        return "martial artist"
    if any(marker in terms for marker in ("durability", "strength", "bruiser", "tank")):
        return "tank/bruiser"
    return "packet-defined fighter"


def combat_identity(contender: dict[str, Any]) -> dict[str, Any]:
    style = compact_names(
        contender.get("combat_style")
        or contender.get("fighting_style")
        or tactical_value(contender, "combat_style")
        or tactical_value(contender, "fighting_style"),
        limit=1,
    )
    powers = compact_names(
        contender.get("abilities")
        or contender.get("powers")
        or contender.get("special_abilities")
        or contender.get("magic"),
        limit=6,
    )
    weapons = compact_names(contender.get("weapons") or contender.get("equipment"), limit=4)
    forms = compact_names(contender.get("forms") or contender.get("transformations") or tactical_value(contender, "forms"), limit=4)
    power_source = compact_names(contender.get("power_source") or tactical_value(contender, "power_source"), limit=2)
    non_physical = non_physical_options(contender)
    mode = combat_mode(contender)
    identity_summary = f"{contender_name(contender)} is a {mode}"
    if non_physical:
        identity_summary += f" with non-physical options: {', '.join(non_physical[:3])}"
    return {
        "identity_summary": identity_summary,
        "combat_mode": mode,
        "combat_style": style[0] if style else mode,
        "power_source": power_source,
        "signature_powers": powers,
        "signature_weapons": weapons,
        "signature_forms": forms,
        "non_physical_options": non_physical,
        "usual_win_condition": compact_names(tactical_value(contender, "win_conditions") or contender.get("win_conditions"), limit=2),
        "personality_flavor": compact_names(contender.get("personality") or tactical_value(contender, "personality"), limit=1),
        "limitations_or_risks": compact_names(contender.get("weaknesses") or tactical_value(contender, "loss_conditions"), limit=3),
    }


def named_tools(contender: dict[str, Any], *, limit: int = 5) -> list[str]:
    tools: list[str] = []
    for section in ("abilities", "equipment"):
        tools.extend(item_names(contender, section, limit=limit))
    for key in ("forms", "transformations", "notable_attacks", "techniques"):
        tools.extend(compact_names(tactical_value(contender, key), limit=limit))
    power_scale = contender.get("power_scale") if isinstance(contender.get("power_scale"), dict) else {}
    for key in ("attack_potency", "speed", "durability", "range"):
        value = clean_strategy_fragment(str(power_scale.get(key) or ""))
        if value:
            tools.append(f"{key.replace('_', ' ')}: {value}")
    deduped = []
    seen = set()
    for tool in tools:
        tool = sanitize_fight_card_item(tool)
        if not tool:
            continue
        normalized = tool.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(tool)
    return deduped[:limit]


def main_risk(contender: dict[str, Any]) -> str:
    risks = item_names(contender, "weaknesses", limit=1)
    if risks:
        return risks[0]
    loss_conditions = compact_names(tactical_value(contender, "losing_conditions") or tactical_value(contender, "loss_conditions"), limit=1)
    if loss_conditions:
        return loss_conditions[0]
    return "No clean exploitable weakness supplied."


def matchup_card(
    contender_a: dict[str, Any],
    contender_b: dict[str, Any],
    *,
    winner: dict[str, Any] | None = None,
    loser: dict[str, Any] | None = None,
    winner_route: str = "",
    loser_route: str = "",
) -> list[dict[str, Any]]:
    winner_id = (winner or {}).get("character_id")
    loser_id = (loser or {}).get("character_id")
    cards = []
    for contender in (contender_a, contender_b):
        contender_id = contender.get("character_id")
        if contender_id == winner_id:
            best_route = winner_route
        elif contender_id == loser_id:
            best_route = loser_route
        else:
            best_route = "Needs a clearer packet-backed win route."
        identity = combat_identity(contender)
        cards.append(
            {
                "name": contender_name(contender),
                "height_weight": physical_line(contender),
                "weapon_power": weapon_power_choice(contender),
                "combat_identity": identity,
                "style": identity["combat_style"],
                "key_tools": named_tools(contender),
                "best_route": best_route,
                "risk": main_risk(contender),
            }
        )
    return cards


def structured_factor(winner: dict[str, Any], loser: dict[str, Any]) -> dict[str, str] | None:
    winner_name = str(winner.get("canonical_name") or "Winner")
    loser_name = str(loser.get("canonical_name") or "Loser")
    battlefield = tactical_value(winner, "battlefield_control")
    if battlefield:
        battlefield_text = clean_strategy_fragment(str(battlefield))
        return {
            "factor": "Battlefield Control",
            "evidence": f"{winner_name}'s battlefield-control note: {battlefield_text}",
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
        tactical_note = clean_strategy_fragment(str(style or intelligence))
        return {
            "factor": "Skill / Tactics",
            "evidence": f"{winner_name}'s tactical note: {tactical_note}",
            "tactical_effect": f"{winner_name} can use {tactical_note} to avoid low-value trades.",
        }
    forms = compact_names(tactical_value(winner, "forms"))
    if forms:
        return {
            "factor": "Special Abilities",
            "evidence": f"{winner_name} has listed form access: {', '.join(forms)}",
            "tactical_effect": f"{winner_name} can change tempo with {', '.join(forms)} if the first approach stalls.",
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
        return f"{winner_name} wins by weathering early answers and making each return hit cost {loser_name} more."
    if "Skill / Tactics" in factor_names:
        return f"{winner_name} wins by steering the matchup through cleaner decisions, timing, and packet-backed tactics."
    if "Special Abilities" in factor_names:
        return f"{winner_name} wins by using named tools to create the opening that raw stats alone do not describe."
    return f"{winner_name} has the clearer packet-backed route over {loser_name}."


def loser_path(loser: dict[str, Any], winner: dict[str, Any]) -> str:
    loser_name = str(loser.get("canonical_name") or "Loser")
    winner_name = str(winner.get("canonical_name") or "Winner")
    loss_conditions = compact_names(tactical_value(winner, "losing_conditions") or tactical_value(winner, "loss_conditions"), limit=1)
    if loss_conditions:
        return (
            f"{loser_name}'s best route was to force the listed failure case, {loss_conditions[0]}, "
            f"before {winner_name} settled into their preferred pace."
        )
    weaknesses = item_names(winner, "weaknesses", limit=2)
    if weaknesses:
        return (
            f"{loser_name}'s best route against {winner_name} was to force their strongest confirmed lane early, pressure "
            f"{winner_name} around {', '.join(weaknesses)}, and punish any timing or stamina gap "
            f"before {winner_name} controlled the pace."
        )
    return (
        f"{loser_name} needed to force the fight against {winner_name} into their strongest confirmed lane, "
        "but the packet did not provide a clean exploitable weakness."
    )


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
            "overall_probability": {"winner": 0.5, "loser": 0.5},
            "winner_probability": 0.5,
            "loser_probability": 0.5,
            "advantage_breakdown": {},
            "swing_factors": [],
            "fight_flow": empty_fight_flow(),
            "engine_reasoning": [],
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
            "overall_probability": {"winner": 0.5, "loser": 0.5},
            "winner_probability": 0.5,
            "loser_probability": 0.5,
            "advantage_breakdown": advantage_breakdown(a, b, scores_a, scores_b),
            "swing_factors": [],
            "fight_flow": empty_fight_flow(),
            "engine_reasoning": ["The packet did not provide enough parsed ranking data for a deterministic winner."],
            "matchup_card": matchup_card(a, b),
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
    winner_probability = probability_for_confidence(confidence)
    loser_probability = round(1.0 - winner_probability, 2)
    breakdown = advantage_breakdown(a, b, scores_a, scores_b)
    best_loser_path = loser_path(loser, winner)
    swings = swing_factors_from_breakdown(breakdown, contender_name(winner))
    fight_flow = build_fight_flow(
        contender_name(winner),
        contender_name(loser),
        deciding,
        breakdown,
        swings,
        best_loser_path,
    )
    reasoning = engine_reasoning_from_flow(fight_flow)
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
        "loser_best_path": best_loser_path,
        "loser": loser["canonical_name"],
        "loser_character_id": loser["character_id"],
        "deciding_factors": deciding,
        "overall_probability": {"winner": winner_probability, "loser": loser_probability},
        "winner_probability": winner_probability,
        "loser_probability": loser_probability,
        "advantage_breakdown": breakdown,
        "swing_factors": swings,
        "fight_flow": fight_flow,
        "engine_reasoning": reasoning,
        "matchup_card": matchup_card(a, b, winner=winner, loser=loser, winner_route=route, loser_route=best_loser_path),
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
