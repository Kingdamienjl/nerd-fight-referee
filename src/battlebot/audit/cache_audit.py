"""Read-only audit of cached fight results (cached_fight_results).

Three checks per row, all read-only:

1. checker re-run -- the stored rewrite must still pass the repo's
   mechanical SB checker against the stored draft. A row that passed
   at write time and fails now means the checker or the prompt moved
   under it (checker drift).
2. staleness -- the stored profile hashes must still match the live
   character_profiles hashes for both fighters. A mismatch means the
   serving path would miss the cache and re-judge; the row is dead
   weight, kept only as history. A prompt_version different from the
   current PROMPT_VERSION is the same class of drift.
3. spot re-judge -- an independent DeepSeek verdict from the stored
   draft's analyst breakdown, via the existing referee-rewrite-together
   LiteLLM group, compared to the cached winner/difficulty. A
   disagreement means the draft verdict itself is suspect -- the cloud
   rewrite only rewords the local draft and never questions it.

Nothing here writes to the database, the cache, or any profile. The
re-judge caller is injectable (``caller=``) so tests never spend a
real LLM call.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from battlebot.fight.rewrite_check import check_rewrite
from battlebot.fight.rewrite_prompt import PROMPT_VERSION

LOGGER = logging.getLogger("battlebot.audit.cache_audit")

REJUDGE_MODEL = "referee-rewrite-together"
REJUDGE_TEMPERATURE = 0.1
REJUDGE_MAX_TOKENS = 32768  # DeepSeek reasoning eats small caps.
REJUDGE_TIMEOUT = 300.0
# DeepSeek-V4.1-Flash via Together: $0.30 / $1.20 per 1M in/out.
REJUDGE_PRICE_IN_PER_M = 0.30
REJUDGE_PRICE_OUT_PER_M = 1.20
# Output tokens are not returned by call_ollama; estimate the short
# JSON verdict + reasoning at 4,000 tokens per call and label it so.
REJUDGE_EST_OUTPUT_TOKENS = 4000
DIFFICULTIES = ("Neg/No Diff", "Low Diff", "Mid Diff", "High Diff", "Extreme Diff")

CACHE_ROWS_SQL = """SELECT id, fighter_a, form_a, fighter_b, form_b,
        energy_equalization, arena, prep_time, prompt_version,
        profile_hash_a, profile_hash_b, verdict_winner, difficulty,
        confidence, draft_json, rewritten_json, hit_count, created_at
    FROM cached_fight_results ORDER BY id"""

LIVE_HASHES_SQL = """SELECT character_id, profile_hash
    FROM character_profiles WHERE character_id = ANY($1)"""

DISPLAY_NAMES_SQL = """SELECT id, canonical_name
    FROM characters WHERE id = ANY($1)"""

REJUDGE_SYSTEM = (
    "You are an independent fight adjudicator. Read the analyst "
    "breakdown and the draft verdict for a versus fight between two "
    "named fighters. Return ONLY a JSON object with keys winner, "
    "difficulty, confidence. winner must be exactly one of the two "
    "fighter names given. difficulty must be exactly one of: "
    "Neg/No Diff, Low Diff, Mid Diff, High Diff, Extreme Diff. "
    "confidence must be exactly one of: low, medium, high. "
    "Do not add any other text."
)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


async def fetch_cache_rows(conn: Any) -> list[dict[str, Any]]:
    """All cached rows, oldest first. Read-only."""
    rows = await conn.fetch(CACHE_ROWS_SQL)
    return [dict(r) for r in rows]


def check_cached_row(row: dict[str, Any]) -> dict[str, Any]:
    """Re-run the SB checker on one stored row.

    Returns {"fail": [...], "flags": [...], "detail": {...}} -- fail is
    empty when the stored rewrite still passes against the stored
    draft. JOIN/semicolon hits land in flags, not fail, exactly as
    the production checker defines them.
    """
    draft = _as_dict(row.get("draft_json"))
    draft_rs = draft.get("referee_structured_draft") or {}
    rewritten = _as_dict(row.get("rewritten_json"))
    fail, flags, detail = check_rewrite(draft_rs, rewritten)
    return {"fail": fail, "flags": flags, "detail": detail}


async def fetch_live_hashes(conn: Any, fighter_ids: list[str]) -> dict[str, str | None]:
    """Current character_profiles hashes for the given fighters."""
    if not fighter_ids:
        return {}
    rows = await conn.fetch(LIVE_HASHES_SQL, fighter_ids)
    return {r["character_id"]: r["profile_hash"] for r in rows}


def stale_check(row: dict[str, Any], live_hashes: dict[str, str | None]) -> list[str]:
    """Staleness findings for one row (empty = live and servable)."""
    findings: list[str] = []
    if row.get("prompt_version") != PROMPT_VERSION:
        findings.append(f"prompt_version_drift:{row.get('prompt_version')}")
    for side, fighter_key, hash_key in (
        ("a", "fighter_a", "profile_hash_a"),
        ("b", "fighter_b", "profile_hash_b"),
    ):
        fighter = row.get(fighter_key)
        live = live_hashes.get(str(fighter)) if fighter else None
        if fighter is None:
            findings.append(f"fighter_{side}_missing")
        elif live is None:
            findings.append(f"fighter_{side}_not_in_db:{fighter}")
        elif str(live) != str(row.get(hash_key)):
            findings.append(f"stale_hash_{side}:{fighter}")
    return findings


def select_rejudge_sample(rows: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """Sample to re-judge: ALL rows while the cache is small (<50),
    otherwise the `cap` most-served rows (hit_count desc, id asc --
    deterministic, and the rows users actually see)."""
    if len(rows) <= 50:
        return list(rows)
    ranked = sorted(rows, key=lambda r: (-(r.get("hit_count") or 0), r.get("id") or 0))
    return ranked[:cap]


def build_rejudge_messages(
    row: dict[str, Any],
    display_a: str | None = None,
    display_b: str | None = None,
) -> list[dict[str, str]]:
    """Independent-verdict prompt from the stored draft evidence.

    The model is given DISPLAY names (canonical names from the
    characters table), never the fighter IDs: telling it the IDs
    makes it echo an ID back as the winner, which no name comparison
    can match to the cached display-name verdict.
    """
    draft = _as_dict(row.get("draft_json"))
    draft_rs = draft.get("referee_structured_draft") or {}
    verdict = draft.get("fight_verdict") or {}
    name_a = display_a or str(row.get("fighter_a"))
    name_b = display_b or str(row.get("fighter_b"))
    user = (
        f"Fighter A: {name_a}\n"
        f"Fighter B: {name_b}\n\n"
        f"Analyst breakdown:\n{draft.get('analyst_breakdown') or ''}\n\n"
        f"Draft verdict: winner={draft_rs.get('predicted_winner')} "
        f"difficulty={draft_rs.get('difficulty')} "
        f"confidence={draft_rs.get('confidence')}\n"
        f"Draft summary: {verdict.get('summary') or ''}\n"
        f"Draft reasoning: {verdict.get('reasoning') or ''}\n\n"
        "Who wins this fight, and by how much?"
    )
    return [
        {"role": "system", "content": REJUDGE_SYSTEM},
        {"role": "user", "content": user},
    ]


def _name_tokens(name: Any) -> set[str]:
    return {t for t in str(name or "").casefold().split() if t}


def names_agree(a: Any, b: Any) -> bool:
    """Winner-name agreement, tolerant of 'Goku' vs 'Son Goku':
    agree when either token set is a non-empty subset of the other."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


def compare_verdicts(
    cached_winner: Any,
    cached_difficulty: Any,
    rejudged: dict[str, Any],
) -> list[str]:
    """Disagreements between the cached verdict and a re-judge."""
    findings: list[str] = []
    if not names_agree(cached_winner, rejudged.get("winner")):
        findings.append(
            f"winner_disagree:cached={cached_winner!r} rejudged={rejudged.get('winner')!r}"
        )
    if str(cached_difficulty or "").strip() != str(rejudged.get("difficulty") or "").strip():
        findings.append(
            f"difficulty_disagree:cached={cached_difficulty!r} "
            f"rejudged={rejudged.get('difficulty')!r}"
        )
    return findings


async def rejudge_row(
    row: dict[str, Any],
    *,
    caller: Any | None = None,
    model: str = REJUDGE_MODEL,
    timeout: float = REJUDGE_TIMEOUT,
    display_a: str | None = None,
    display_b: str | None = None,
) -> dict[str, Any]:
    """Independent DeepSeek verdict for one cached row.

    Returns {"row_id", "pair", "rejudged", "disagreements", "error",
    "model", "prompt_tokens_est"}. A call/parse failure is an error,
    never a disagreement.
    """
    from battlebot.fight.rewrite import parse_rewrite

    pair = f"{row.get('fighter_a')} vs {row.get('fighter_b')}"
    messages = build_rejudge_messages(row, display_a, display_b)
    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    out: dict[str, Any] = {
        "row_id": row.get("id"),
        "pair": pair,
        "rejudged": None,
        "disagreements": [],
        "error": None,
        "model": model,
        "prompt_tokens_est": max(1, prompt_chars // 4),
    }
    try:
        if caller is None:
            from battlebot.fight.llm_judge import call_ollama

            caller = call_ollama
        raw = await caller(
            messages,
            model=model,
            format_json=True,
            temperature=REJUDGE_TEMPERATURE,
            num_predict=REJUDGE_MAX_TOKENS,
            timeout=timeout,
        )
    except Exception as exc:  # call failure -> error, not disagreement
        out["error"] = f"call_failed:{type(exc).__name__}:{str(exc)[:160]}"
        return out
    parsed, parse_note = parse_rewrite(raw)
    if not isinstance(parsed, dict) or not parsed.get("winner"):
        out["error"] = f"unparseable:{parse_note or 'no winner in reply'}"
        return out
    out["rejudged"] = {
        "winner": parsed.get("winner"),
        "difficulty": parsed.get("difficulty"),
        "confidence": parsed.get("confidence"),
    }
    out["disagreements"] = compare_verdicts(
        row.get("verdict_winner"), row.get("difficulty"), out["rejudged"]
    )
    return out


async def audit_cache(
    conn: Any,
    *,
    sample_cap: int = 25,
    rejudge: bool = True,
    caller: Any | None = None,
) -> dict[str, Any]:
    """Run all three cache checks. Read-only; returns findings."""
    rows = await fetch_cache_rows(conn)
    fighter_ids = sorted(
        {str(r.get(f)) for r in rows for f in ("fighter_a", "fighter_b") if r.get(f)}
    )
    live_hashes = await fetch_live_hashes(conn, fighter_ids)
    display_rows = await conn.fetch(DISPLAY_NAMES_SQL, fighter_ids)
    display_names = {r["id"]: r["canonical_name"] for r in display_rows}
    checker_failed: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for row in rows:
        checked = check_cached_row(row)
        if checked["fail"]:
            checker_failed.append(
                {
                    "row_id": row.get("id"),
                    "pair": f"{row.get('fighter_a')} vs {row.get('fighter_b')}",
                    "fail": checked["fail"],
                    "flags": checked["flags"],
                }
            )
        findings = stale_check(row, live_hashes)
        if findings:
            stale.append(
                {
                    "row_id": row.get("id"),
                    "pair": f"{row.get('fighter_a')} vs {row.get('fighter_b')}",
                    "findings": findings,
                }
            )
    rejudged: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    rejudge_errors: list[dict[str, Any]] = []
    est_input_tokens = 0
    if rejudge:
        for row in select_rejudge_sample(rows, sample_cap):
            result = await rejudge_row(
                row,
                caller=caller,
                display_a=display_names.get(str(row.get("fighter_a"))),
                display_b=display_names.get(str(row.get("fighter_b"))),
            )
            est_input_tokens += result["prompt_tokens_est"]
            if result["error"]:
                rejudge_errors.append(result)
            else:
                rejudged.append(result)
                if result["disagreements"]:
                    disagreements.append(result)
    est_cost_usd = (
        est_input_tokens * REJUDGE_PRICE_IN_PER_M
        + len(rejudged) * REJUDGE_EST_OUTPUT_TOKENS * REJUDGE_PRICE_OUT_PER_M
    ) / 1_000_000
    return {
        "rows_checked": len(rows),
        "checker_failed": checker_failed,
        "stale": stale,
        "rejudge_sampled": len(rejudged) + len(rejudge_errors),
        "rejudged": rejudged,
        "disagreements": disagreements,
        "rejudge_errors": rejudge_errors,
        "est_input_tokens": est_input_tokens,
        "est_cost_usd": round(est_cost_usd, 4),
    }
