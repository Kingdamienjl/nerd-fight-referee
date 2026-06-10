"""Format fight decisions for Discord."""

from __future__ import annotations

from typing import Any


def clamp_text(text: str, limit: int = 1900) -> str:
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def format_decision(decision: dict[str, Any], *, limit: int = 1900) -> str:
    lines = [
        str(decision.get("title") or "Nerd Fight Referee Decision"),
        f"winner: {decision.get('winner')}",
        f"confidence: {decision.get('confidence')}",
    ]
    if decision.get("summary"):
        lines.append(f"summary: {decision['summary']}")
    if decision.get("win_condition"):
        lines.append(f"win condition: {decision['win_condition']}")
    if decision.get("loser_best_path"):
        lines.append(f"loser best path: {decision['loser_best_path']}")
    factors = decision.get("deciding_factors") or []
    if factors:
        lines.append("deciding factors:")
        for factor in factors[:5]:
            if isinstance(factor, dict):
                lines.append(f"- {factor.get('factor')}: {factor.get('tactical_effect')}")
                if factor.get("evidence"):
                    lines.append(f"  evidence: {factor['evidence']}")
            else:
                lines.append(f"- {factor}")
    warnings = decision.get("warnings") or []
    if warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in warnings[:5])
    notes = decision.get("judge_notes") or []
    if notes:
        lines.append("judge notes:")
        lines.extend(f"- {note}" for note in notes[:4])
    return clamp_text("\n".join(lines), limit)
