"""Pydantic schema for the schema-constrained LLM fight verdict.

``FightVerdict`` is serialized via ``model_json_schema()`` and passed as the
``format`` parameter to Ollama's ``/api/chat`` (or as ``response_format`` when
routing through the LiteLLM proxy) for constrained JSON decoding. This
replaces regex-based winner parsing on the primary judge path; the old
``referee_winner_from_text()`` remains as a fallback for non-Ollama callers.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RubricScores(BaseModel):
    """Per-axis G-Eval style rubric scores, 1 (no edge) .. 5 (decisive).

    Scores are always written from the perspective of the contender the judge
    believes wins: how decisively does the WINNER lead on each axis.
    """

    feat_quality: int = Field(
        ge=1,
        le=5,
        description="Quality/reliability of the winner's cited feats",
    )
    stat_differential: int = Field(
        ge=1,
        le=5,
        description="Raw stat gap in the winner's favor (strength, durability, DC)",
    )
    hax_counterplay: int = Field(
        ge=1,
        le=5,
        description="Winner's hax, resistances, and counterplay options vs the loser",
    )
    win_condition_count: int = Field(
        ge=1,
        le=5,
        description="Number of reliable, evidence-backed paths to victory for the winner",
    )
    speed_advantage: int = Field(
        ge=1,
        le=5,
        description="Winner's speed/blitz potential over the loser",
    )


class FightVerdict(BaseModel):
    """Schema-constrained verdict emitted by the LLM judge.

    Field order is significant: ``reasoning`` comes first so the model
    reasons step by step through each rubric axis BEFORE committing to
    ``winner`` (Pydantic preserves declaration order in the JSON schema).
    """

    reasoning: str = Field(
        description=(
            "Chain-of-thought: reason step by step through each rubric axis "
            "(feat quality, stat differential, hax/counterplay, win conditions, "
            "speed), citing packet evidence, BEFORE stating the verdict."
        )
    )
    rubric: RubricScores
    winner: Literal["a", "b"] = Field(
        description='"a" means contender_a wins, "b" means contender_b wins'
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Judge's confidence in the verdict, 0.0 (toss-up) to 1.0 (certain)",
    )
    summary: str = Field(
        description="1-2 sentence verdict summary suitable for Discord"
    )


def fight_verdict_json_schema() -> dict[str, Any]:
    """Return the JSON Schema dict used for constrained decoding."""
    return FightVerdict.model_json_schema()


def verdict_winner_name(verdict: FightVerdict, packet: dict[str, Any]) -> str:
    """Map a schema verdict's ``winner`` ("a"/"b") back to the canonical contender name."""
    side = "contender_a" if verdict.winner == "a" else "contender_b"
    contender = packet.get(side) if isinstance(packet.get(side), dict) else {}
    return str(
        contender.get("canonical_name")
        or contender.get("character_id")
        or ("Contender A" if verdict.winner == "a" else "Contender B")
    )
