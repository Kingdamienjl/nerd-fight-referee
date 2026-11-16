"""Cache-lookup-then-generate wrapper around judge_fight_packet.

Flow (see the SB wiring plan): the call sites run the stomp check FIRST,
so this wrapper only ever sees non-stomp fights -- stomps are never
cached and never served from cache. For a non-stomp fight:

1. Build the cache key from the REQUESTED order (pair + forms + prompt
   version + profile hashes; fight variables are dropped for launch, so
   the variable columns stay at the Wave 1 defaults). Never reuse
   packet["ordered_pair_key"]: ordered_pair_key() SORTS the IDs.
2. Hit (row + prompt version + both hashes match) -> reconstruct the
   decision from the cached draft + rewritten narration. The winner
   STAYS the draft winner. Best-effort hit-count bump, never fatal.
3. Miss (or DB unreachable, or packet lacks key fields) -> local draft
   via judge_fight_packet. A fallback draft is returned as-is, never
   rewritten. A real draft goes through the cloud rewrite
   (checker-gated, max 3, Gemini-first/DeepSeek-overflow); success maps
   the rewritten narration onto the draft decision and stores the row
   best-effort. Any rewrite/DB failure serves the local draft.

The wrapper never fails a fight: every cache/DB/rewrite error degrades
to the local draft decision.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from battlebot.common.db import connect_database
from battlebot.fight.llm_judge import engine_verdict, judge_fight_packet
from battlebot.fight.rewrite import rewrite_narration
from battlebot.fight.rewrite_check import REQUIRED_KEYS
from battlebot.fight.rewrite_prompt import PROMPT_VERSION

LOGGER = logging.getLogger("battlebot.fight.cached_judge")

# Cache-key variable columns, pinned at the Wave 1 defaults. Fight
# variables are DROPPED for launch (Chris 2026-11-09): a fight is the
# pair + forms, defaults, done.
CACHE_ENERGY_EQUALIZATION = False
CACHE_ARENA = "Neutral Dimensional Void"
CACHE_PREP_TIME = "Random Encounter"

_FETCH_SQL = """SELECT id, verdict_winner, difficulty, confidence,
                 draft_json, rewritten_json
          FROM cached_fight_results
          WHERE fighter_a = $1 AND form_a = $2 AND fighter_b = $3
            AND form_b = $4 AND energy_equalization = $5 AND arena = $6
            AND prep_time = $7 AND prompt_version = $8
            AND profile_hash_a = $9 AND profile_hash_b = $10"""

_INSERT_SQL = """INSERT INTO cached_fight_results
           (fighter_a, form_a, fighter_b, form_b, energy_equalization,
            arena, prep_time, prompt_version, profile_hash_a, profile_hash_b,
            verdict_winner, difficulty, confidence, draft_json, rewritten_json)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15::jsonb)
           ON CONFLICT (fighter_a, form_a, fighter_b, form_b,
                        energy_equalization, arena, prep_time, prompt_version)
           DO NOTHING"""

_BUMP_SQL = ("UPDATE cached_fight_results "
             "SET hit_count = hit_count + 1, last_served_at = now() "
             "WHERE id = $1")


def form_name_for_contender(contender: dict[str, Any]) -> str:
    """Form string for the cache key: the variant name, or "base"."""
    variant = contender.get("variant") or {}
    if variant.get("default_variant"):
        return "base"
    name = str(variant.get("variant_name") or "").strip()
    return name or "base"


def cache_key_from_packet(packet: dict[str, Any]) -> dict[str, Any] | None:
    """Requested-order cache key, or None when key fields are missing."""
    a = packet.get("contender_a") or {}
    b = packet.get("contender_b") or {}
    fighter_a = a.get("character_id") or a.get("profile_id")
    fighter_b = b.get("character_id") or b.get("profile_id")
    hashes = packet.get("profile_hashes") or []
    hash_a = a.get("profile_hash") or (hashes[0] if len(hashes) > 0 else None)
    hash_b = b.get("profile_hash") or (hashes[1] if len(hashes) > 1 else None)
    if not fighter_a or not fighter_b or not hash_a or not hash_b:
        return None
    return {
        "fighter_a": str(fighter_a),
        "form_a": form_name_for_contender(a),
        "fighter_b": str(fighter_b),
        "form_b": form_name_for_contender(b),
        "energy_equalization": CACHE_ENERGY_EQUALIZATION,
        "arena": CACHE_ARENA,
        "prep_time": CACHE_PREP_TIME,
        "prompt_version": PROMPT_VERSION,
        "profile_hash_a": str(hash_a),
        "profile_hash_b": str(hash_b),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except Exception:  # unparseable stored JSON -> empty
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def _fetch_cached_row(conn: Any, key: dict[str, Any]) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        _FETCH_SQL,
        key["fighter_a"], key["form_a"], key["fighter_b"], key["form_b"],
        key["energy_equalization"], key["arena"], key["prep_time"],
        key["prompt_version"], key["profile_hash_a"], key["profile_hash_b"],
    )
    return dict(row) if row is not None else None


async def _store_cached_row(
    conn: Any,
    key: dict[str, Any],
    winner: Any,
    difficulty: Any,
    confidence: Any,
    draft_artifact: dict[str, Any],
    rewritten: dict[str, Any],
) -> None:
    await conn.execute(
        _INSERT_SQL,
        key["fighter_a"], key["form_a"], key["fighter_b"], key["form_b"],
        key["energy_equalization"], key["arena"], key["prep_time"],
        key["prompt_version"], key["profile_hash_a"], key["profile_hash_b"],
        winner, difficulty, confidence,
        json.dumps(draft_artifact), json.dumps(rewritten),
    )


def reconstruct_decision(
    packet: dict[str, Any],
    smoke_result: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild a judge-shaped decision from a cached row.

    The deterministic fields come from the live smoke result; the winner,
    difficulty, and confidence come from the row; the narration comes
    from the stored rewrite. The winner STAYS the draft winner.
    """
    rewritten = _as_dict(row.get("rewritten_json"))
    draft = _as_dict(row.get("draft_json"))
    name_a = (packet.get("contender_a") or {}).get("canonical_name") or ""
    name_b = (packet.get("contender_b") or {}).get("canonical_name") or ""
    winner = row.get("verdict_winner") or smoke_result.get("winner")
    if winner == name_a and name_b:
        loser = name_b
    elif winner == name_b and name_a:
        loser = name_a
    else:
        loser = smoke_result.get("loser")
    phases = [rewritten.get("phase_1") or "",
              rewritten.get("phase_2") or "",
              rewritten.get("phase_3") or ""]
    quick = rewritten.get("quick_verdict") or ""
    stored_diag = draft.get("diagnostics")
    stored_diag = stored_diag if isinstance(stored_diag, dict) else {}
    diagnostics = dict(stored_diag)
    diagnostics.update({
        "fallback": False,
        "fallback_reason": "cache_hit",
        "fallback_detail": "Served from cached_fight_results; narration is the SB rewrite.",
        "cache_hit": True,
        "cache_row_id": row.get("id"),
    })
    return {
        **smoke_result,
        "winner": winner,
        "loser": loser,
        "verdict_type": "referee_verdict",
        "title": "Nerd Fight Referee Decision",
        "summary": quick,
        "quick_verdict": quick,
        "narrative_phases": phases,
        "difficulty": row.get("difficulty") or smoke_result.get("difficulty"),
        "confidence": row.get("confidence") or smoke_result.get("confidence"),
        "presentation_packet": packet,
        "win_condition": "\n\n".join(p for p in phases if p),
        "engine_verdict": stored_diag.get("engine_verdict") or engine_verdict(smoke_result),
        "referee_verdict": {
            "winner": winner,
            "changed_winner": False,
            "upset_allowed": False,
            "upset_justification": "",
            "explanation": quick,
        },
        "referee_structured": rewritten,
        "analyst_breakdown": draft.get("analyst_breakdown") or "",
        "fight_verdict": draft.get("fight_verdict"),
        "diagnostics": diagnostics,
        "judge_notes": ["Served from the fight cache; narration is the SB rewrite."],
    }


def _is_rewritable_draft(draft_rs: Any) -> bool:
    return isinstance(draft_rs, dict) and all(draft_rs.get(k) for k in REQUIRED_KEYS)


async def judge_fight_packet_cached(
    packet: dict[str, Any],
    smoke_result: dict[str, Any],
    *,
    judge_fn: Any | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Cached judge entry point. Never fails a fight.

    judge_fn defaults to judge_fight_packet; call sites pass their own
    module-level reference so tests can keep patching it.
    """
    judge_fn = judge_fn or judge_fight_packet
    key = cache_key_from_packet(packet)
    if key is not None:
        row = None
        try:
            async with connect_database(database_url) as conn:
                row = await _fetch_cached_row(conn, key)
                if row is not None:
                    try:
                        await conn.execute(_BUMP_SQL, row["id"])
                    except Exception as exc:  # bump is best-effort
                        LOGGER.warning("cache hit-count bump failed (%s)", type(exc).__name__)
        except Exception as exc:  # DB down means miss, never fatal
            LOGGER.warning("cache lookup failed (%s); generating live", type(exc).__name__)
            row = None
        if row is not None:
            return reconstruct_decision(packet, smoke_result, row)
    decision = await judge_fn(packet, smoke_result)
    if (decision.get("diagnostics") or {}).get("fallback"):
        return decision
    draft_rs = decision.get("referee_structured")
    if not _is_rewritable_draft(draft_rs):
        return decision
    rewritten, info = await rewrite_narration(
        draft_rs, decision.get("analyst_breakdown") or ""
    )
    if rewritten is None:
        LOGGER.warning("SB rewrite failed; serving local draft")
        return decision
    out = dict(decision)
    phases = [rewritten["phase_1"], rewritten["phase_2"], rewritten["phase_3"]]
    out["quick_verdict"] = rewritten["quick_verdict"]
    out["narrative_phases"] = phases
    out["summary"] = rewritten["quick_verdict"]
    out["win_condition"] = "\n\n".join(phases)
    out["referee_structured"] = rewritten
    out["difficulty"] = rewritten["difficulty"]
    out["confidence"] = rewritten["confidence"]
    diag = dict(decision.get("diagnostics") or {})
    diag["sb_rewritten"] = True
    diag["rewrite_model"] = info.get("model")
    out["diagnostics"] = diag
    if key is not None:
        draft_artifact = {
            "referee_structured_draft": draft_rs,
            "analyst_breakdown": decision.get("analyst_breakdown") or "",
            "fight_verdict": decision.get("fight_verdict"),
            "diagnostics": decision.get("diagnostics"),
        }
        try:
            async with connect_database(database_url) as conn:
                await _store_cached_row(
                    conn, key,
                    draft_rs.get("predicted_winner"),
                    draft_rs.get("difficulty"),
                    draft_rs.get("confidence"),
                    draft_artifact, rewritten,
                )
        except Exception as exc:  # store is best-effort
            LOGGER.warning("cache store failed (%s); serving rewritten decision", type(exc).__name__)
    return out
