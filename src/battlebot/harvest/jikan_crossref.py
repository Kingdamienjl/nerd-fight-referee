"""Optional Jikan API (MyAnimeList) cross-reference for the Nerd Referee harvester.

Round 1 supplementary module — NOT wired into the harvest cycle. This module
only builds the cross-reference; a later round will wire it into the harvest
loop. Chris enables it after seeing standalone test results.

Enable with::

    HARVEST_JIKAN_ENABLED=1

Status 2026-10-18: the public api.jikan.moe host was DISCONTINUED 2026-10-01
(jikan-me/jikan-rest#613) — it no longer answers. Set HARVEST_JIKAN_BASE_URL
to a self-hosted jikan-rest instance or compatible drop-in to actually use
this. The module ships correct against Jikan REST v4 and is logic-tested
with mocked v4 responses; it is NOT live-tested against a live host.

When the env var is off (default "0"), :func:`crossref_character` returns
``None`` immediately without any network calls.

Supplied fields (when wired in):
    - ``identity.external_ids.mal``  — MAL character id (numeric)
    - ``mal_favorites``               — MAL favorites count
    - ``mal_about``                   — MAL bio/about text
    - ``mal_image_url``               — MAL character image URL

These are additive and do not disturb any existing profile fields.

Standalone test::

    python3 -m battlebot.harvest.jikan_crossref "Goku" "Dragon Ball"
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import os
import re
import threading
import time
from typing import Any

import requests

LOG = logging.getLogger("battlebot.harvest.jikan_crossref")

ENV_VAR = "HARVEST_JIKAN_ENABLED"
BASE_URL_VAR = "HARVEST_JIKAN_BASE_URL"

# NOTE (2026-10-18): the Jikan PUBLIC API (api.jikan.moe) was discontinued
# 2026-10-01 (jikan-me/jikan-rest#613). The public host no longer answers.
# This module speaks plain Jikan REST v4, so point HARVEST_JIKAN_BASE_URL at a
# self-hosted jikan-rest instance or a compatible drop-in (Jikan-Edge, Tenrai)
# to use it. Default keeps the historic public host for documentation.
JIKAN_BASE = os.environ.get(BASE_URL_VAR, "https://api.jikan.moe/v4").rstrip("/")
JIKAN_CHARACTERS_URL = f"{JIKAN_BASE}/characters"

# Jikan free tier: 3 requests/second, 60/minute. Keep comfortably under.
MIN_INTERVAL_S = 1.0 / 3.0 + 0.05  # >= 0.383s between requests
MAX_RETRIES = 5
REQUEST_TIMEOUT_S = 20

# Minimum difflib ratio for a fuzzy name match to be accepted.
FUZZY_THRESHOLD = 0.85

_rate_lock = threading.Lock()
_last_request_ts = 0.0


def is_enabled() -> bool:
    """Return True only when HARVEST_JIKAN_ENABLED is truthy (default: off)."""
    return os.environ.get(ENV_VAR, "0").strip().lower() in ("1", "true", "yes", "on")


def _throttled_get(url: str, params: dict[str, Any]) -> requests.Response:
    """GET with Jikan rate limiting (<=3 req/s) and backoff on 429.

    Raises the last exception / HTTPError after MAX_RETRIES attempts.
    """
    global _last_request_ts

    for attempt in range(1, MAX_RETRIES + 1):
        with _rate_lock:
            now = time.monotonic()
            wait = MIN_INTERVAL_S - (now - _last_request_ts)
            if wait > 0:
                time.sleep(wait)
            _last_request_ts = time.monotonic()

        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_S)
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)
            continue

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            backoff = float(retry_after) if retry_after else 2 ** attempt
            LOG.warning(
                "jikan 429 (attempt %d/%d); backing off %.1fs",
                attempt,
                MAX_RETRIES,
                backoff,
            )
            time.sleep(backoff)
            continue

        if resp.status_code >= 500 and attempt < MAX_RETRIES:
            backoff = 2 ** attempt
            LOG.warning(
                "jikan %d (attempt %d/%d); backing off %.1fs",
                resp.status_code,
                attempt,
                MAX_RETRIES,
                backoff,
            )
            time.sleep(backoff)
            continue

        resp.raise_for_status()
        return resp

    raise requests.HTTPError(f"jikan request failed after {MAX_RETRIES} attempts")


def _search_characters(name: str, limit: int = 10) -> list[dict[str, Any]]:
    resp = _throttled_get(
        JIKAN_CHARACTERS_URL,
        {"q": name, "limit": limit, "order_by": "favorites", "sort": "desc"},
    )
    payload = resp.json()
    return payload.get("data", []) or []


def _normalize(text: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _tokens(text: str | None) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


def _token_set_score(
    query_tokens: list[str], candidate_tokens: list[str]
) -> float:
    """Order-insensitive token similarity (handles 'Lastname, Firstname')."""
    if not query_tokens or not candidate_tokens:
        return 0.0
    total = 0.0
    for qt in query_tokens:
        best = max(
            difflib.SequenceMatcher(None, qt, ct).ratio()
            for ct in candidate_tokens
        )
        total += best
    return total / max(len(query_tokens), len(candidate_tokens))


def _candidate_name_score(query: str, candidate: dict[str, Any]) -> tuple[float, str]:
    """Return (score, reason) for how well *query* matches a MAL candidate."""
    q = _normalize(query)
    q_tokens = _tokens(query)
    names = [candidate.get("name") or ""]
    nicknames = candidate.get("nicknames") or []
    if candidate.get("name_kanji"):
        names.append(candidate["name_kanji"])

    # 1. full-string exact match (case/punctuation insensitive)
    for name in names:
        if q and _normalize(name) == q:
            return 1.0, "exact_name"

    # 2. nickname exact match
    for nick in nicknames:
        if q and _normalize(nick) == q:
            return 0.95, "exact_nickname"

    # 3. every query token appears in the candidate name
    #    ("Goku" -> "Son Goku", "Levi Ackerman" -> "Ackerman, Levi")
    for name in names:
        c_tokens = _tokens(name)
        if q_tokens and all(t in c_tokens for t in q_tokens):
            return 0.95, "token_subset"

    # 4. order-insensitive fuzzy token-set score (tolerates misspellings)
    best = 0.0
    for name in names:
        best = max(best, _token_set_score(q_tokens, _tokens(name)))
    return best, "fuzzy_tokens"


def _series_in_animeography(
    series: str, candidate: dict[str, Any]
) -> bool:
    s = _normalize(series)
    for entry in candidate.get("anime") or []:
        anime = entry.get("anime", {}) or {}
        # v4 character animeography uses "name"; accept "title" as fallback.
        title = anime.get("name") or anime.get("title") or ""
        if s and (s == _normalize(title) or s in _normalize(title)):
            return True
    return False


def _pick_best(
    name: str, series: str | None, candidates: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, float, str]:
    """Return (candidate, confidence, reason).

    Prefers exact name matches, then best fuzzy >= FUZZY_THRESHOLD. When
    *series* is given, a series-confirmed candidate wins ties.
    """
    scored: list[tuple[float, float, bool, str, dict[str, Any]]] = []
    for cand in candidates:
        name_score, reason = _candidate_name_score(name, cand)
        confirmed = bool(series) and _series_in_animeography(series, cand)
        scored.append((name_score, 1.0 if confirmed else 0.0, confirmed, reason, cand))

    # Sort: name score first, then series confirmation, then raw favorites.
    scored.sort(
        key=lambda s: (s[0], s[1], s[4].get("favorites") or 0), reverse=True
    )
    if not scored:
        return None, 0.0, "no_results"

    top_score, _, confirmed, reason, top = scored[0]
    if top_score < FUZZY_THRESHOLD:
        LOG.info(
            "jikan no confident match for %r (best %.2f via %s)",
            name,
            top_score,
            reason,
        )
        return None, 0.0, "below_threshold"

    if series and not confirmed:
        reason = f"{reason}+series_unconfirmed"

    return top, top_score, reason


def crossref_character(
    name: str, series: str | None = None, limit: int = 10
) -> dict[str, Any] | None:
    """Cross-reference a character against the Jikan / MyAnimeList API.

    Returns ``{"mal_id", "name", "favorites", "about", "image_url",
    "match_confidence", "match_reason"}`` or ``None`` when the module is
    disabled (env ``HARVEST_JIKAN_ENABLED``) or no confident match is found.
    """
    if not is_enabled():
        LOG.debug("jikan crossref disabled (%s not set); skipping %r", ENV_VAR, name)
        return None

    try:
        candidates = _search_characters(name, limit=limit)
    except Exception:
        LOG.exception("jikan search failed for %r", name)
        return None

    if not candidates:
        LOG.info("jikan: no candidates for %r", name)
        return None

    best, confidence, reason = _pick_best(name, series, candidates)
    if best is None:
        return None

    images = best.get("images", {}).get("jpg", {}) or {}
    image_url = images.get("image_url")

    result = {
        "mal_id": best.get("mal_id"),
        "name": best.get("name"),
        "favorites": best.get("favorites") or 0,
        "about": best.get("about"),
        "image_url": image_url,
        "match_confidence": round(confidence, 3),
        "match_reason": reason,
    }

    LOG.info(
        "jikan match: %r%s -> MAL %s %r (favorites=%s, confidence=%.2f, %s)",
        name,
        f" [{series}]" if series else "",
        result["mal_id"],
        result["name"],
        result["favorites"],
        confidence,
        reason,
    )
    return result


def supplementary_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Convert a crossref result into additive profile YAML fields."""
    return {
        "mal_favorites": result.get("favorites"),
        "mal_about": result.get("about"),
        "mal_image_url": result.get("image_url"),
    }


def apply_to_profile(
    profile: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Add Jikan supplementary fields to a loaded profile dict (in place).

    Sets ``identity.external_ids.mal`` plus the top-level ``mal_*`` fields.
    Existing fields are never modified or removed.
    """
    identity = profile.setdefault("identity", {})
    external_ids = identity.setdefault("external_ids", {})
    external_ids["mal"] = result.get("mal_id")
    profile.update(supplementary_fields(result))
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Jikan/MAL character cross-reference (standalone test)"
    )
    parser.add_argument("name", help="character name to look up")
    parser.add_argument("series", nargs="?", default=None, help="anime series")
    parser.add_argument(
        "--no-guard",
        action="store_true",
        help="bypass the HARVEST_JIKAN_ENABLED guard (testing only)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.no_guard:
        os.environ[ENV_VAR] = "1"
    elif not is_enabled():
        print(f"refusing: set {ENV_VAR}=1 (or use --no-guard) to run")
        return 2

    result = crossref_character(args.name, args.series)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
