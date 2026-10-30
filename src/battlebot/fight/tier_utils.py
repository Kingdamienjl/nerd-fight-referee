"""VS Battles Wiki tier parsing + deterministic stomp pre-filter.

Per VS Battles Wiki versus-thread rules, a large tier gap is a decided
stomp: no debate -- and no LLM calls -- needed.

This module is intentionally independent of ``fight.llm_judge`` so the
pre-filter can sit in front of ``judge_fight_packet`` without touching it::

    from battlebot.fight.tier_utils import maybe_stomp_decision

    stomp = maybe_stomp_decision(packet)
    decision = stomp if stomp is not None else await judge_fight_packet(packet, smoke_result)

Config (env):
    REFEREE_TIER_PREFILTER_ENABLED -- "1/true/yes/on" to enable (default: enabled)
    REFEREE_STOMP_TIER_GAP        -- float tier gap that counts as a stomp (default: 2.0)
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_STOMP_TIER_GAP = 2.0
STOMP_CONFIDENCE_SCORE = 0.95

# Numeric strength scale: HIGHER = STRONGER.
# score = (11 - tier_number) + sub_tier_fraction + modifier_fraction
# e.g. Tier 4-B -> 7.5, Tier 7-C -> 4.25 (gap 3.25 -> "3 tier gap").
_SUB_SCORE = {"A": 0.75, "B": 0.5, "C": 0.25}
_MOD_SCORE = {"Low": -0.25, "High": 0.25}

# Matches: "4-B", "High 6-C", "Low 1-C" (also inside {{...}} wiki templates).
_TIER_TOKEN_RE = re.compile(r"(?:(Low|High)\s+)?\b([01]?\d)\s*-\s*([ABC])\b")
# Matches: "Tier 7", "Tier 4-B" (case-insensitive "tier").
_TIER_PLAIN_RE = re.compile(r"(?i)\btier\s+([01]?\d)(?:\s*-\s*([ABC]))?\b")

_UNPARSEABLE_MARKERS = re.compile(
    r"(?i)\{\{\s*(Unknown|Varies|Varies,?\s*up\s*to)\s*\}\}|\bunknown\b"
)


@dataclass(frozen=True)
class TierToken:
    """One parsed VS Battles Wiki tier."""

    modifier: str | None  # "Low" | "High" | None
    number: int           # 0 (strongest) .. 11 (weakest)
    sub: str | None       # "A" | "B" | "C" | None

    @property
    def score(self) -> float:
        """Higher = stronger. Used for gap comparisons."""
        return (
            (11 - self.number)
            + _SUB_SCORE.get(self.sub or "", 0.5)
            + _MOD_SCORE.get(self.modifier or "", 0.0)
        )

    @property
    def display(self) -> str:
        prefix = f"{self.modifier} " if self.modifier else ""
        suffix = f"-{self.sub}" if self.sub else ""
        return f"{prefix}{self.number}{suffix}".strip()


def extract_tier_tokens(text: str | None) -> list[TierToken]:
    """Extract every tier token from raw harvester tier text.

    Handles wiki templates (``{{High 8-C}}``), pipe-separated multi-form
    entries (``{{2-B}} | {{1-C}}``), qualifiers (``At least {{9-A}}``), and
    prose with garbage appended (``At least {{6-C}} Name: ... Origin: ...``).
    """
    if not text:
        return []
    raw = str(text)
    tokens: list[TierToken] = []
    seen: set[tuple[str | None, int, str | None]] = set()

    def _add(modifier: str | None, number: str, sub: str | None) -> None:
        try:
            num = int(number)
        except (TypeError, ValueError):
            return
        if not 0 <= num <= 11:
            return
        mod = modifier if modifier in ("Low", "High") else None
        key = (mod, num, sub)
        if key in seen:
            return
        seen.add(key)
        tokens.append(TierToken(modifier=mod, number=num, sub=sub))

    for match in _TIER_TOKEN_RE.finditer(raw):
        _add(match.group(1), match.group(2), match.group(3))
    for match in _TIER_PLAIN_RE.finditer(raw):
        _add(None, match.group(1), match.group(2))
    return tokens


def strongest_tier(text: str | None) -> TierToken | None:
    """Strongest tier found in the text, or None if unparseable/unknown."""
    tokens = extract_tier_tokens(text)
    if not tokens:
        return None
    return max(tokens, key=lambda t: t.score)


def fighter_tier(contender: dict[str, Any] | None) -> TierToken | None:
    """Strongest tier for one compacted fight-packet contender."""
    if not isinstance(contender, dict):
        return None
    power_scale = contender.get("power_scale") or {}
    return strongest_tier(power_scale.get("tier"))


def prefilter_enabled(env: dict[str, str] | None = None) -> bool:
    values = env or os.environ
    return str(values.get("REFEREE_TIER_PREFILTER_ENABLED", "true")).casefold() in {
        "1", "true", "yes", "on",
    }


def stomp_tier_gap(env: dict[str, str] | None = None) -> float:
    values = env or os.environ
    try:
        return float(values.get("REFEREE_STOMP_TIER_GAP", DEFAULT_STOMP_TIER_GAP))
    except (TypeError, ValueError):
        return DEFAULT_STOMP_TIER_GAP


def _fighter_tools(compact: dict[str, Any], tier_display: str) -> list[str]:
    """Real profile-backed tool names for the fight card (never placeholders)."""
    tools: list[str] = []
    for item in list(compact.get("equipment") or []) + list(compact.get("abilities") or []):
        name = item.get("name") if isinstance(item, dict) else None
        name = str(name or "").strip()
        if name and name not in tools:
            tools.append(name)
        if len(tools) >= 3:
            break
    if not tools:
        # Factual, profile-derived fallback -- never the "Standard combat
        # capabilities" webhook placeholder.
        tools.append(f"Tier {tier_display} combat scale")
    return tools


def _fighter_style(compact: dict[str, Any]) -> str:
    tactical = compact.get("tactical_profile") or {}
    style = tactical.get("combat_style") if isinstance(tactical, dict) else None
    if style:
        return str(style)
    return ""


def build_stomp_decision(
    packet: dict[str, Any],
    token_a: TierToken,
    token_b: TierToken,
    *,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Deterministic stomp verdict shaped like a normal judge decision.

    Carries every key the downstream formatting expects
    (decision_formatter -> structured_decision_output -> webhook) so the
    verdict renders with NO placeholder text.
    """
    threshold = DEFAULT_STOMP_TIER_GAP if threshold is None else threshold
    contender_a = packet.get("contender_a") or {}
    contender_b = packet.get("contender_b") or {}
    name_a = contender_a.get("canonical_name") or "Contender A"
    name_b = contender_b.get("canonical_name") or "Contender B"

    gap = abs(token_a.score - token_b.score)
    main_gap = abs(token_a.number - token_b.number)
    gap_label = f"{main_gap} tier gap"

    winner_is_a = token_a.score >= token_b.score
    winner, loser = (name_a, name_b) if winner_is_a else (name_b, name_a)
    winner_token, loser_token = (token_a, token_b) if winner_is_a else (token_b, token_a)

    tier_math = f"Tier {token_a.display} vs Tier {token_b.display}: {gap_label}"
    explanation = (
        f"\U0001f4a5 Stomp verdict \u2014 no LLM debate needed. {winner} is Tier "
        f"{winner_token.display}; {loser} caps at Tier {loser_token.display} "
        f"({tier_math}, threshold {threshold:g}). Per VS Battles Wiki versus-thread "
        f"rules, a gap of {threshold:g}+ tiers is a decided stomp: {loser} has no "
        f"profile-backed win path against an opponent {gap_label} above their scale."
    )
    quick_verdict = (
        f"Stomp \u2014 tier gap: {winner} (Tier {winner_token.display}) over "
        f"{loser} (Tier {loser_token.display}), {gap_label}."
    )

    # Cards stay in contender (a, b) order like smoke_judge.matchup_card --
    # downstream labels them with contender_a/b names.
    winner_route = (
        f"Overwhelm {loser} through raw tier superiority \u2014 a {gap_label} "
        "leaves no defensive answer."
    )
    loser_route = f"No viable win route: outscaled by {gap_label} against {winner}."
    matchup_card = []
    for contender, token, is_winner in (
        (contender_a, token_a, winner_is_a),
        (contender_b, token_b, not winner_is_a),
    ):
        cname = contender.get("canonical_name") or ("Contender A" if contender is contender_a else "Contender B")
        matchup_card.append(
            {
                "name": cname,
                "key_tools": _fighter_tools(contender, token.display),
                "best_route": winner_route if is_winner else loser_route,
                "risk": (
                    "Negligible: the tier gap removes credible upset routes."
                    if is_winner
                    else f"Outclassed across the stat board by Tier {winner_token.display}."
                ),
                "style": _fighter_style(contender),
            }
        )

    return {
        "title": "Nerd Fight Referee Decision",
        "winner": winner,
        "loser": loser,
        "verdict_type": "stomp_tier_gap",
        "verdict_label": "Stomp \u2014 tier gap",
        "tier_math": tier_math,
        "tier_gap": gap,
        "tier_gap_main_tiers": main_gap,
        "tier_gap_threshold": threshold,
        "tier_a": token_a.display,
        "tier_b": token_b.display,
        "confidence": "High",
        "confidence_score": STOMP_CONFIDENCE_SCORE,
        "summary": explanation,
        "quick_verdict": quick_verdict,
        "win_condition": explanation,
        "public_summary": quick_verdict,
        "matchup_card": matchup_card,
        "winner_probability": STOMP_CONFIDENCE_SCORE,
        "loser_probability": round(1.0 - STOMP_CONFIDENCE_SCORE, 2),
        "loser_best_path": (
            f"{loser} needed a matchup-specific counter to survive {winner}, but a "
            f"{gap_label} (Tier {loser_token.display} vs Tier {winner_token.display}) "
            "leaves no credible upset route."
        ),
        "deciding_factors": [
            {
                "factor": "Tier gap (VS Battles Wiki)",
                "evidence": (
                    f"{winner} is Tier {winner_token.display}; {loser} is Tier "
                    f"{loser_token.display} \u2014 a {gap_label}."
                ),
            },
            {
                "factor": "Versus-thread stomp rule",
                "evidence": (
                    f"A gap of {threshold:g}+ tiers is a decided stomp, so no LLM "
                    "debate was run."
                ),
            },
        ],
        "difficulty": "Neg/No Diff",
        "narrative_phases": [],
        "presentation_packet": packet,
        "judge_notes": [
            (f"Deterministic tier pre-filter: stomp declared at a {gap_label} "
            f"(threshold {threshold:g}); zero LLM calls spent.")
        ],
        "diagnostics": {
            "fallback": False,
            "pipeline": "tier_prefilter",
            "tier_gap": gap,
            "tier_gap_main_tiers": main_gap,
            "tier_gap_threshold": threshold,
            "tier_a": token_a.display,
            "tier_b": token_b.display,
            "llm_calls": 0,
        },
    }


def maybe_stomp_decision(
    packet: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return a deterministic stomp verdict, or None to run the full pipeline.

    Never raises and never calls the LLM: any missing/unparseable tier data
    returns None (skip pre-filter, run full pipeline).
    """
    try:
        if not prefilter_enabled(env):
            return None
        contender_a = (packet or {}).get("contender_a")
        contender_b = (packet or {}).get("contender_b")
        token_a = fighter_tier(contender_a)
        token_b = fighter_tier(contender_b)
        if token_a is None or token_b is None:
            return None
        threshold = stomp_tier_gap(env)
        gap = abs(token_a.score - token_b.score)
        if gap < threshold:
            return None
        decision = build_stomp_decision(packet, token_a, token_b, threshold=threshold)
        LOGGER.info(
            "tier_prefilter: STOMP %s (Tier %s) vs %s (Tier %s), gap=%.2f >= %.2f",
            (packet.get("contender_a") or {}).get("canonical_name"),
            token_a.display,
            (packet.get("contender_b") or {}).get("canonical_name"),
            token_b.display,
            gap,
            threshold,
        )
        return decision
    except Exception as exc:
        LOGGER.warning("tier_prefilter: skipped due to error: %s", exc)
        return None
