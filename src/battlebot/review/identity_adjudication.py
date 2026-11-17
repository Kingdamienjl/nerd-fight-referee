"""LLM identity adjudication: rescue-only second look for identity-rejected attempts.

When the lexical identity scorer rejects a repair source (identity_score below
IDENTITY_MATCH_THRESHOLD), the adjudicator asks an LLM whether the fetched page
is about the SAME character as the profile, using the fetched title plus the
page's first substantive paragraph. A high-confidence YES rescues the attempt
back into the EXISTING approval pipeline; anything else stays rejected.

Safety properties (hard requirements from the pilot GO verdict, 2026-11-16):
- RESCUE-ONLY: a YES only flips the attempt's identity standing so the normal
  eligibility, merge, and approval gates can consider it. It never
  auto-promotes, never bypasses approval blockers, and manual review of every
  merge remains mandatory.
- UNCERTAIN/NO stay rejected. Judge errors and unparseable verdicts stay
  rejected. Only a parsed YES rescues.
- ENV-GATED, OFF BY DEFAULT: inert unless IDENTITY_ADJUDICATION_ENABLED=1.
- The scorer itself is untouched: rescue sets the attempt's EFFECTIVE score to
  the threshold (the minimum passing value, so rescues sort below genuine
  lexical matches) and preserves the scorer's original score in
  adjudication_original_score and in the audit record.
- EVIDENCE: served title (normalized_page_title) + first paragraph. The
  recorded URL is deliberately OMITTED: the pilot showed URL/title conflicts
  caused 4/7 abstentions, because the URL names the recorded source, not
  necessarily the page that was fetched.
- BOUNDED: a per-cycle call budget (IDENTITY_ADJUDICATION_MAX_CALLS, default
  10), reset by the worker loop each cycle, plus a durable memo: every verdict
  is recorded in the audit log and re-used without a new call, so each unique
  attempt is judged at most once ever. Errors are never memoized.
- PROVENANCE: every adjudication (including errors) is appended to
  data/identity_adjudications.jsonl and recorded on the attempt itself, which
  lands in the per-profile debug report automatically.

Backend: call_ollama -> LiteLLM group referee-rewrite-together (DeepSeek
V4.1-Flash via Together), the pilot-proven backend, reusing the existing group
so no LiteLLM config change is needed. Override with
IDENTITY_ADJUDICATION_MODEL: the standing 8B re-check swaps the group, not code.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from battlebot.review.auto_repair import SourceAttempt

LOGGER = logging.getLogger("battlebot.review.identity_adjudication")

ENV_ENABLED = "IDENTITY_ADJUDICATION_ENABLED"
ENV_MAX_CALLS = "IDENTITY_ADJUDICATION_MAX_CALLS"
ENV_MODEL = "IDENTITY_ADJUDICATION_MODEL"

DEFAULT_MODEL = "referee-rewrite-together"
DEFAULT_MAX_CALLS_PER_CYCLE = 10
ADJUDICATION_TEMPERATURE = 0.1
ADJUDICATION_MAX_TOKENS = 32768  # REQUIRED: thinking tokens eat small caps.
ADJUDICATION_TIMEOUT = 600.0
DEFAULT_AUDIT_PATH = Path("data/identity_adjudications.jsonl")

# Planning-rate estimate for audit records. The LiteLLM path does not surface
# token usage through call_ollama, so per-call cost is recorded as this
# documented estimate, never presented as measured.
ESTIMATED_COST_USD_PER_CALL = 0.0005

# Effective score a rescued attempt carries: exactly the threshold, the minimum
# passing value. Read from auto_repair at call time (deferred import: this
# module must never import auto_repair at module level, or the hook import
# would cycle).


def _identity_match_threshold() -> int:
    from battlebot.review.auto_repair import IDENTITY_MATCH_THRESHOLD

    return IDENTITY_MATCH_THRESHOLD

# Proven judge system prompt from the identity pilot (judge_system.txt, verbatim).
SYSTEM_PROMPT = """You are an identity adjudicator for a character database. Decide whether a fetched wiki page is about the SAME character as a database profile.

Rules:
- Answer YES only when the evidence clearly shows the page is the same character (same person/being, allowing for alternate names, nicknames, titles, and continuity variants of the same character).
- Answer NO when the evidence clearly shows a DIFFERENT character (different person, a similarly named character from another franchise, a group/team/place/object page, or a disambiguation page that is not the character).
- Answer UNCERTAIN when the evidence is ambiguous, too thin, or could reasonably go either way. When in doubt, say UNCERTAIN, not YES.
- A wrong YES is the worst outcome: it would merge another character's stats into this profile. Be conservative.
- Use ONLY the evidence given. Do not use outside knowledge about the characters beyond reading the evidence.
- Respond with a JSON object only: {"verdict": "yes" | "no" | "uncertain", "reason": "<one sentence>"}"""

VERDICTS = ("yes", "no", "uncertain")


def adjudication_enabled() -> bool:
    """True only when explicitly enabled. Mirrors the HARVEST_LLM_FALLBACK gate."""
    return os.getenv(ENV_ENABLED, "0") == "1"


def max_calls_per_cycle() -> int:
    try:
        value = int(os.getenv(ENV_MAX_CALLS, str(DEFAULT_MAX_CALLS_PER_CYCLE)))
    except ValueError:
        return DEFAULT_MAX_CALLS_PER_CYCLE
    return max(0, value)


def adjudication_model() -> str:
    return os.getenv(ENV_MODEL, DEFAULT_MODEL) or DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Per-cycle budget (reset by the worker loop each cycle; see worker/main.py)
# ---------------------------------------------------------------------------

_BUDGET_USED = 0


def reset_cycle_budget() -> None:
    global _BUDGET_USED
    _BUDGET_USED = 0


def _try_reserve_call() -> bool:
    """Reserve one budgeted call. Synchronous: reserve before awaiting the LLM."""
    global _BUDGET_USED
    if _BUDGET_USED >= max_calls_per_cycle():
        return False
    _BUDGET_USED += 1
    return True


# ---------------------------------------------------------------------------
# Durable memo: verdicts recorded in the audit log are re-used, never re-judged
# ---------------------------------------------------------------------------

_MEMO_BY_PATH: dict[str, dict[str, dict[str, Any]]] = {}


def _memo_key(source_id: str, served_title: str) -> str:
    return f"{source_id}\n{served_title}"


def _load_memo(audit_path: Path) -> dict[str, dict[str, Any]]:
    key = str(audit_path)
    cached = _MEMO_BY_PATH.get(key)
    if cached is not None:
        return cached
    memo: dict[str, dict[str, Any]] = {}
    try:
        lines = audit_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        # Errors are never memoized: a transient failure must not block a
        # later rescue.
        if record.get("verdict") not in VERDICTS:
            continue
        memo[_memo_key(str(record.get("source_id") or ""), str(record.get("served_title") or ""))] = record
    _MEMO_BY_PATH[key] = memo
    return memo


def _reset_memo_cache() -> None:
    """Test hook: drop all cached memos so a fresh audit file is re-read."""
    _MEMO_BY_PATH.clear()


def _append_audit_record(audit_path: Path, record: dict[str, Any]) -> None:
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as exc:
        # Audit failure must never fail the repair; the attempt fields still
        # carry the verdict into the per-profile debug report.
        LOGGER.warning("identity adjudication audit write failed: %s", exc)


# ---------------------------------------------------------------------------
# Evidence: served title + first substantive paragraph (URL deliberately omitted)
# ---------------------------------------------------------------------------


class _ParagraphCollector(HTMLParser):
    """Collect top-level <p> text, skipping tables/nav/figures. Pilot port."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._current: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("table", "nav", "aside", "figure", "figcaption"):
            self._skip_depth += 1
        if tag == "p" and self._skip_depth == 0 and self._current is None:
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("table", "nav", "aside", "figure", "figcaption"):
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "p" and self._current is not None:
            text = re.sub(r"\s+", " ", "".join(self._current)).strip()
            if text:
                self.paragraphs.append(text)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._skip_depth == 0:
            self._current.append(data)


async def fetch_page_intro(api_url: str, title: str) -> tuple[str, str, str]:
    """Fetch the first substantive paragraph via action=parse.

    Returns (intro, status, served_title). Mirrors the pilot's fetch_intros.py:
    first paragraph >= 80 chars, else >= 40, capped at 900 chars.
    """
    import aiohttp

    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
    }
    timeout = aiohttp.ClientTimeout(total=25, connect=5, sock_connect=5, sock_read=15)
    try:
        async with (
            aiohttp.ClientSession(
                timeout=timeout, headers={"User-Agent": "battlebot-review-repair/0.1"}
            ) as session,
            session.get(api_url, params=params) as response,
        ):
            if response.status != 200:
                return "", f"missing:http_{response.status}", ""
            body = await response.json(content_type=None)
    except Exception as exc:  # network failure: thin evidence, judge decides
        return "", f"missing:{type(exc).__name__}", ""
    if not isinstance(body, dict):
        return "", "missing:bad_response", ""
    parse = body.get("parse") or {}
    if not isinstance(parse, dict) or "text" not in parse:
        error = body.get("error")
        error_code = error.get("code") if isinstance(error, dict) else None
        return "", f"missing:{error_code or 'no_parse'}", ""
    served = str(parse.get("title") or "")
    collector = _ParagraphCollector()
    try:
        collector.feed(str(parse["text"]))
    except Exception:
        return "", "missing:html_parse_error", served
    for para in collector.paragraphs:
        if len(para) >= 80:
            return html.unescape(para)[:900], "ok", served
    for para in collector.paragraphs:
        if len(para) >= 40:
            return html.unescape(para)[:900], "ok_short", served
    return "", "missing:no_paragraph", served


def profile_aliases(profile: dict[str, Any]) -> list[str]:
    """Raw recorded aliases (no normalization: the judge reads them as written)."""
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    seen: set[str] = set()
    aliases: list[str] = []
    for value in (*(profile.get("aliases") or []), *(identity.get("aliases") or [])):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            aliases.append(text)
    return aliases


def build_user_prompt(
    *,
    name: str,
    franchise: str,
    aliases: list[str],
    served_title: str,
    intro: str,
) -> str:
    """User prompt. The recorded URL is deliberately NOT included (see module docstring)."""
    alias_text = ", ".join(aliases) or "(none)"
    intro_text = intro or "(no introductory text available)"
    return (
        "PROFILE\n"
        f"Name: {name}\n"
        f"Franchise: {franchise}\n"
        f"Aliases: {alias_text}\n"
        "\nFETCHED PAGE\n"
        f"Title: {served_title}\n"
        f"Introductory text: {intro_text}\n"
        "\nIs the fetched page about the SAME character as the profile?"
    )


def parse_adjudication(raw: str) -> tuple[str, str, str | None]:
    """Parse a judge response into (verdict, reason, parse_note).

    Anything unparseable, or any verdict outside yes/no/uncertain, degrades to
    UNCERTAIN (safe default: stays rejected) with a parse note.
    """
    text = (raw or "").strip()
    try:
        verdict_obj = json.loads(text)
        note = None
    except (json.JSONDecodeError, TypeError):
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            verdict_obj = json.loads(text[start:end])
            note = "brace-extracted"
        except (ValueError, json.JSONDecodeError) as exc:
            return "uncertain", "", f"parse-failed: {type(exc).__name__}"
    if not isinstance(verdict_obj, dict):
        return "uncertain", "", "parse-failed: non-object"
    verdict = str(verdict_obj.get("verdict", "")).strip().lower()
    reason = str(verdict_obj.get("reason", "") or "")
    if verdict not in VERDICTS:
        return "uncertain", reason, f"bad-verdict: {verdict!r}"
    return verdict, reason, note


# ---------------------------------------------------------------------------
# Adjudication
# ---------------------------------------------------------------------------


def _qualifies_for_adjudication(attempt: SourceAttempt) -> bool:
    """Only attempts that are eligible in every way EXCEPT identity.

    Mirrors eligible_primary_attempts minus the identity_match requirement, so
    LLM spend goes only where a rescue can change the outcome.
    """
    return (
        attempt.fetch_status == "fetched"
        and not attempt.identity_match
        and attempt.core_field_count >= 3
        and attempt.ability_count >= 1
        and attempt.promotion_allowed
        and attempt.variant_score >= 0
        and not attempt.continuity_mismatch
    )


def _apply_verdict(
    attempt: SourceAttempt,
    *,
    verdict: str,
    reason: str,
    backend: str,
    cached: bool,
) -> None:
    """Record the verdict on the attempt; rescue on YES only."""
    attempt.adjudication_verdict = verdict
    attempt.adjudication_reason = reason
    attempt.adjudication_backend = backend
    attempt.adjudication_cached = cached
    if verdict == "yes":
        if attempt.adjudication_original_score is None:
            attempt.adjudication_original_score = attempt.identity_score
        attempt.identity_score = _identity_match_threshold()
        attempt.identity_match = True


async def _default_caller(messages: list[dict[str, str]], **kwargs: Any) -> str:
    # Deferred import: battlebot.fight must never be a hard import-time
    # dependency of the review package (import-cycle guard).
    from battlebot.fight.llm_judge import call_ollama

    return await call_ollama(messages, **kwargs)


async def _default_intro_fetcher(api_url: str, title: str) -> tuple[str, str, str]:
    return await fetch_page_intro(api_url, title)


async def adjudicate_attempt(
    profile: dict[str, Any],
    attempt: SourceAttempt,
    *,
    profile_label: str = "",
    caller: Any | None = None,
    intro_fetcher: Any | None = None,
    audit_path: Path | None = None,
) -> dict[str, Any] | None:
    """Adjudicate one rejected attempt. Returns the audit record, or None when
    the cycle budget is exhausted (attempt left untouched for a later cycle).

    Memo hits return the recorded verdict without spending budget or calling.
    """
    audit_path = audit_path or DEFAULT_AUDIT_PATH
    memo = _load_memo(audit_path)
    memo_key = _memo_key(attempt.source_id, attempt.normalized_page_title)
    memoized = memo.get(memo_key)
    if memoized is not None:
        _apply_verdict(
            attempt,
            verdict=str(memoized["verdict"]),
            reason=str(memoized.get("reason") or ""),
            backend=str(memoized.get("backend") or ""),
            cached=True,
        )
        return dict(memoized, cached=True)

    if not _try_reserve_call():
        LOGGER.info(
            "identity adjudication budget exhausted; deferring %s", attempt.source_id
        )
        return None

    model = adjudication_model()
    name = str(profile.get("name") or "")
    franchise = str(profile.get("franchise") or "")
    aliases = profile_aliases(profile)

    # Intro fetch: origin API from the recorded URL, page = the SERVED title.
    intro, intro_status = "", "missing:api_url"
    try:
        from battlebot.review.providers.mediawiki import resolve_mediawiki_api_url

        api_url = resolve_mediawiki_api_url(attempt.url)
    except Exception:
        api_url = ""
    if api_url and attempt.normalized_page_title:
        fetcher = intro_fetcher or _default_intro_fetcher
        try:
            intro, intro_status, _served_title = await fetcher(
                api_url, attempt.normalized_page_title
            )
        except Exception as exc:
            intro, intro_status = "", f"missing:{type(exc).__name__}"

    prompt = build_user_prompt(
        name=name,
        franchise=franchise,
        aliases=aliases,
        served_title=attempt.normalized_page_title,
        intro=intro,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    judge = caller or _default_caller
    request_info: dict[str, Any] = {}
    try:
        raw = await judge(
            messages,
            model=model,
            format_json=True,
            temperature=ADJUDICATION_TEMPERATURE,
            num_predict=ADJUDICATION_MAX_TOKENS,
            timeout=ADJUDICATION_TIMEOUT,
            request_info=request_info,
        )
    except Exception as exc:
        reason = f"judge-error: {type(exc).__name__}: {exc}"[:500]
        attempt.adjudication_verdict = "error"
        attempt.adjudication_reason = reason
        attempt.adjudication_backend = model
        attempt.adjudication_cached = False
        record = _audit_record(
            profile_label=profile_label,
            attempt=attempt,
            original_score=attempt.identity_score,
            evidence={
                "name": name,
                "franchise": franchise,
                "aliases": aliases,
                "served_title": attempt.normalized_page_title,
                "intro": intro,
                "intro_status": intro_status,
            },
            verdict="error",
            reason=reason,
            parse_note=None,
            backend=model,
        )
        _append_audit_record(audit_path, record)
        return record

    verdict, reason, parse_note = parse_adjudication(raw)
    backend = str(request_info.get("model_group") or model)
    _apply_verdict(attempt, verdict=verdict, reason=reason, backend=backend, cached=False)
    record = _audit_record(
        profile_label=profile_label,
        attempt=attempt,
        original_score=attempt.adjudication_original_score
        if attempt.adjudication_original_score is not None
        else attempt.identity_score,
        evidence={
            "name": name,
            "franchise": franchise,
            "aliases": aliases,
            "served_title": attempt.normalized_page_title,
            "intro": intro,
            "intro_status": intro_status,
        },
        verdict=verdict,
        reason=reason,
        parse_note=parse_note,
        backend=backend,
    )
    _append_audit_record(audit_path, record)
    memo[memo_key] = record
    return record


def _audit_record(
    *,
    profile_label: str,
    attempt: SourceAttempt,
    original_score: int,
    evidence: dict[str, Any],
    verdict: str,
    reason: str,
    parse_note: str | None,
    backend: str,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "profile": profile_label,
        "source_id": attempt.source_id,
        "served_title": attempt.normalized_page_title,
        "identity_score": original_score,
        "evidence": evidence,
        "verdict": verdict,
        "reason": reason,
        "parse_note": parse_note,
        "backend": backend,
        "model": adjudication_model(),
        "usage": None,
        "estimated_cost_usd": ESTIMATED_COST_USD_PER_CALL,
        "cached": False,
    }


async def maybe_adjudicate_attempts(
    profile: dict[str, Any],
    attempts: list[SourceAttempt],
    *,
    profile_path: Path | None = None,
    caller: Any | None = None,
    intro_fetcher: Any | None = None,
    audit_path: Path | None = None,
) -> list[SourceAttempt]:
    """Rescue pass over identity-rejected attempts. Inert unless enabled.

    Returns the same attempt list (mutated in place for rescued/memoized
    attempts). When the flag is off, this is a pure no-op: no calls, no file
    reads, no writes, no behavior change.
    """
    if not adjudication_enabled():
        return attempts
    profile_label = profile_path.stem if profile_path is not None else ""
    for attempt in attempts:
        if not _qualifies_for_adjudication(attempt):
            continue
        await adjudicate_attempt(
            profile,
            attempt,
            profile_label=profile_label,
            caller=caller,
            intro_fetcher=intro_fetcher,
            audit_path=audit_path,
        )
    return attempts
