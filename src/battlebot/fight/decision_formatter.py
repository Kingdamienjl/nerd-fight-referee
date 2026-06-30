"""Format fight decisions for Discord."""

from __future__ import annotations

import re
from typing import Any


PUBLIC_LIMIT = 1800
RAW_TEMPLATE_RE = re.compile(r"\{\{[^{}\n]*(?:\n[^{}]*)?\}\}")
GENERIC_ROUTE = "converts stat leads into initiative, damage pressure, and survivable exchanges"


def truncate_at_sentence_boundary(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cutoff = max(0, limit - 3)
    truncated = text[:cutoff].rstrip()
    sentence_end = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if sentence_end >= cutoff // 3:
        return f"{truncated[: sentence_end + 1]}..."
    word_end = truncated.rfind(" ")
    if word_end > 0:
        truncated = truncated[:word_end].rstrip()
    return f"{truncated}..."


def clamp_text(text: str, limit: int = PUBLIC_LIMIT) -> str:
    return truncate_at_sentence_boundary(text, limit)


def clean_text(value: Any, *, limit: int = 220) -> str:
    text = str(value or "")
    text = RAW_TEMPLATE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" -:\n\t")
    text = text.replace(GENERIC_ROUTE, "turns the listed packet edge into practical fight pressure")
    return clamp_text(text, limit)


def compress_route_text(decision: dict[str, Any], route: str) -> str:
    normalized = route.casefold()
    if any(axis in normalized for axis in ("attack_potency:", "speed:", "durability:", "outerverse level", "athlete level")):
        winner = clean_text(decision.get("winner"), limit=80) or "The winner"
        loser_path = clean_text(decision.get("loser_best_path"), limit=120)
        if "prep" in loser_path.casefold() or "tactic" in loser_path.casefold():
            return f"{winner} has the stronger packet-backed output range; the opposing route leans on tactics, counters, or prep."
        return f"{winner} has the stronger packet-backed output and survivability lane without relying on raw tier dumps."
    return route


def factor_category(value: str) -> str:
    normalized = value.casefold()
    if "range" in normalized:
        return "Range Control"
    if "speed" in normalized or "initiative" in normalized or "mobility" in normalized:
        return "Mobility / Initiative"
    if "attack" in normalized or "power" in normalized or "finishing" in normalized:
        return "Finishing Power"
    if "durability" in normalized or "attrition" in normalized:
        return "Durability / Attrition"
    if "resistance" in normalized or "counter" in normalized:
        return "Resistance / Counterplay"
    if "skill" in normalized or "tactic" in normalized or "intelligence" in normalized:
        return "Skill / Tactics"
    if "prep" in normalized:
        return "Prep Dependence"
    if "weakness" in normalized:
        return "Weakness Exploitation"
    if "battlefield" in normalized:
        return "Battlefield Control"
    if "ability" in normalized or "special" in normalized:
        return "Special Abilities"
    return clean_text(value, limit=48) or "Key Factor"


def compressed_evidence(factor: dict[str, Any]) -> str:
    category = factor_category(str(factor.get("factor") or ""))
    evidence = clean_text(factor.get("evidence"), limit=120)
    effect = clean_text(factor.get("tactical_effect"), limit=120)
    if category and effect:
        return bullet_text(f"{category}: {effect}")
    if evidence:
        return bullet_text(f"{category}: packet evidence favors this lane.")
    return bullet_text(f"{category}: packet-backed edge.")


def bullet_text(value: str) -> str:
    return str(value or "").rstrip(" ,;:")


def fallback_diagnostics(decision: dict[str, Any]) -> list[str]:
    diagnostics = decision.get("diagnostics")
    lines = []
    if isinstance(diagnostics, dict):
        reason = diagnostics.get("fallback_reason")
        detail = diagnostics.get("fallback_detail")
        if reason:
            lines.append(f"fallback reason: {clean_text(reason, limit=80)}")
        if detail:
            lines.append(f"fallback detail: {clean_text(detail, limit=160)}")
    lines.extend(f"judge note: {clean_text(note, limit=160)}" for note in decision.get("judge_notes") or [])
    return [line for line in lines if line.strip()]


def format_decision(
    decision: dict[str, Any],
    *,
    limit: int = PUBLIC_LIMIT,
    include_diagnostics: bool = False,
) -> str:
    factors = [factor for factor in decision.get("deciding_factors") or [] if isinstance(factor, dict)]
    raw_analysis = clean_text(
        decision.get("summary") or decision.get("win_condition") or decision.get("route_to_victory"),
        limit=1400,
    )
    analysis = compress_route_text(
        decision,
        truncate_at_sentence_boundary(raw_analysis, 1250),
    )
    if not analysis:
        analysis = "Deterministic referee could not produce a supported fight explanation."
    loser_best_path = clean_text(decision.get("loser_best_path"), limit=300)
    if not loser_best_path:
        loser_best_path = "Evidence is incomplete."
    lines = [
        "Nerd Fight Referee Decision",
        f"winner: {clean_text(decision.get('winner'), limit=80)}",
        f"confidence: {clean_text(decision.get('confidence'), limit=40)}",
        "",
        "judge's analysis:",
        analysis,
    ]
    if factors:
        lines.extend(["", "evidence:"])
        for factor in factors[:3]:
            lines.append(f"- {compressed_evidence(factor)}")
    lines.extend(["", "loser's best path:", loser_best_path])
    warnings = decision.get("warnings") or []
    if warnings:
        lines.append("caveats:")
        lines.extend(f"- {clean_text(warning, limit=160)}" for warning in warnings[:3])
    if include_diagnostics:
        diagnostics = fallback_diagnostics(decision)
        if diagnostics:
            lines.append("diagnostics:")
            lines.extend(f"- {line}" for line in diagnostics[:5])
    return clamp_text("\n".join(lines), limit)
