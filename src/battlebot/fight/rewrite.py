"""SB rewrite caller: cloud rewrite with checker-gated retry + overflow.

Draft narration (local 8B) goes through the strong prompt to Gemini
3.8-flash first, with DeepSeek-V4.1-Flash-1017 (Together) as the overflow
when Gemini hits its rate limit / daily cap. Checker-gated retry, max 3
attempts total. Any failure returns None and the caller serves the local
draft -- the rewrite never fails a fight.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from battlebot.fight.llm_judge import call_ollama
from battlebot.fight.rewrite_check import check_rewrite
from battlebot.fight.rewrite_prompt import build_rewrite_prompt

LOGGER = logging.getLogger("battlebot.fight.rewrite")

REWRITE_MODEL_GEMINI = "referee-rewrite-gemini"
REWRITE_MODEL_TOGETHER = "referee-rewrite-together"
REWRITE_TEMPERATURE = 0.1
REWRITE_MAX_TOKENS = 32768  # REQUIRED: thinking tokens eat small caps.
REWRITE_TIMEOUT = 600.0
MAX_ATTEMPTS = 3


def parse_rewrite(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(raw), None
    except Exception:
        LOGGER.debug("direct JSON parse failed; trying brace extraction")
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return json.loads(raw[start:end]), "brace-extracted"
    except Exception as exc:  # record parse failure, don't crash
        return None, f"parse-failed: {type(exc).__name__}"


def _is_quota_error(exc: Exception) -> bool:
    """True when the failure is a rate limit / quota / daily-cap hit."""
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        if resp is not None and resp.status_code == 429:
            return True
    text = str(exc).casefold()
    return ("resource_exhausted" in text or "rate limit" in text
            or "rate_limit" in text or "quota" in text)


async def rewrite_narration(
    draft_rs: dict[str, Any],
    analyst_breakdown: str,
    *,
    caller: Any | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Rewrite one draft narration. Returns (rewritten, info).

    rewritten is None when every attempt failed (call error, unparseable
    output, or checker failure). info carries the per-attempt record plus
    the serving model and any adjudication flags on success.
    """
    info: dict[str, Any] = {"attempts": []}
    try:
        messages, _winner, _difficulty, _confidence = build_rewrite_prompt(
            draft_rs, analyst_breakdown
        )
    except Exception as exc:  # no prompt, no rewrite
        info["error"] = f"prompt build failed: {type(exc).__name__}"
        return None, info
    quota_hit = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        model = REWRITE_MODEL_TOGETHER if quota_hit else REWRITE_MODEL_GEMINI
        record: dict[str, Any] = {"attempt": attempt, "model": model}
        info["attempts"].append(record)
        try:
            raw = await (caller or call_ollama)(
                messages,
                model=model,
                format_json=True,
                temperature=REWRITE_TEMPERATURE,
                num_predict=REWRITE_MAX_TOKENS,
                timeout=REWRITE_TIMEOUT,
            )
        except Exception as exc:  # retry or overflow, never crash
            kind = "quota" if _is_quota_error(exc) else "error"
            record["kind"] = kind
            record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            if kind == "quota" and model == REWRITE_MODEL_GEMINI:
                quota_hit = True
                LOGGER.warning("Gemini quota hit; overflowing to DeepSeek")
            continue
        rewritten, parse_note = parse_rewrite(raw)
        record["parse_note"] = parse_note
        if rewritten is None:
            record["kind"] = "parse"
            continue
        fail, flags, detail = check_rewrite(draft_rs, rewritten)
        record["check_fail"] = fail
        record["check_flags"] = flags
        record["check_detail"] = detail
        if fail:
            record["kind"] = "check"
            continue
        record["accepted"] = True
        info["model"] = model
        info["flags"] = flags
        return rewritten, info
    return None, info
