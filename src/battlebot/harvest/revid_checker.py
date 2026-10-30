"""Revision-ID change detection for the profile harvester.

Round 2 of the harvester overhaul (throughput win): before the harvester
spends a full MediaWiki content fetch + parse on a roster row, compare the
page's live revision ID against the revid stored on ``character_profiles``.
Unchanged pages are skipped; only new/changed pages pay the full harvest
cost.

Design notes
------------
* The batch query uses ``prop=revisions&rvprop=ids|timestamp`` in batches of
  50 titles per API request, grouped by wiki (one api.php endpoint per
  batch). ~2,063 profiles => ~42 requests instead of ~2,063 full fetches.
* The check bypasses :class:`RawCache` on purpose: the cache has no expiry,
  so a cached revid would make every later check look "unchanged" and pages
  would never be re-harvested. Only the cooldown wait is reused so we stay
  polite to the wiki.
* The stored revid is the revision the profile was *harvested from*
  (``profile_sources.revision_id`` at harvest time, copied to
  ``character_profiles.revid`` by the importer). Skip iff
  ``live_revid == stored_revid``.
* The "primary" wiki source of a profile is the mediawiki source with the
  smallest ``source_id`` (deterministic; ``source_id`` embeds the page id).
  Backfill, gate lookups, and the importer all use this same rule.

``auto_profile_harvester.py`` is intentionally NOT modified here (it carries
uncommitted parser work from another process). See
``docs/REVID_GATE_INTEGRATION.md`` for the exact hook points.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from battlebot.common.db import connect_database
from battlebot.harvest.auto_profile_harvester import (
    DEFAULT_MEDIAWIKI_API,
    MediaWikiClient,
    RawCache,
    mediawiki_api_from_url,
    profile_output_path,
    title_from_wiki_url,
)

log = logging.getLogger(__name__)

REVID_BATCH_SIZE = 50
PRIMARY_SOURCE_TYPE = "mediawiki"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def parse_rev_timestamp(value: Any) -> datetime | None:
    """Parse a MediaWiki revision timestamp into an aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def primary_mediawiki_revid(
    sources: Any,
) -> tuple[int | None, datetime | None]:
    """Pick the primary mediawiki source's (revid, timestamp) from sources.

    ``sources`` is an iterable of mappings (or objects) with ``source_type``,
    ``source_id``, ``revision_id`` and ``revision_timestamp`` attributes/keys,
    e.g. the dicts produced by ``compile_sources`` in the importer or the
    YAML ``sources`` list. Primary = smallest ``source_id`` among mediawiki
    sources with a numeric revision id. Returns ``(None, None)`` when no
    usable source exists.
    """
    best_key: str | None = None
    best_revid: int | None = None
    best_ts: datetime | None = None
    for source in sources or []:
        if isinstance(source, dict):
            source_type = source.get("source_type")
            raw_revid = source.get("revision_id")
            raw_ts = source.get("revision_timestamp")
            source_key = source.get("source_id")
        else:
            source_type = getattr(source, "source_type", None)
            raw_revid = getattr(source, "revision_id", None)
            raw_ts = getattr(source, "revision_timestamp", None)
            source_key = getattr(source, "source_id", None)
        if source_type != PRIMARY_SOURCE_TYPE:
            continue
        revid = _as_int(raw_revid)
        if revid is None:
            continue
        key = str(source_key or "")
        if best_key is None or key < best_key:
            best_key = key
            best_revid = revid
            best_ts = parse_rev_timestamp(raw_ts)
    return best_revid, best_ts


def build_mediawiki_client(
    *,
    cache_dir: str | Path = "data/revid_cache",
    user_agent: str = "ai-nerd-fight-bot/0.1",
    min_interval_seconds: float = 2.0,
) -> MediaWikiClient:
    """Standalone MediaWikiClient for the backfill script / tests."""
    return MediaWikiClient(
        cache=RawCache(Path(cache_dir)),
        user_agent=user_agent,
        min_interval_seconds=min_interval_seconds,
        use_cache=False,
    )


# ---------------------------------------------------------------------------
# batch live-revid query
# ---------------------------------------------------------------------------

def _canonical_title_map(
    body: dict[str, Any], requested: list[str]
) -> dict[str, str]:
    """Map each requested title to its canonical page title.

    Follows the API's ``normalized`` and ``redirects`` chains so the caller
    can match response pages back to the titles it asked for.
    """
    query = body.get("query", {}) or {}
    alias: dict[str, str] = {}
    for entry in query.get("normalized", []) or []:
        alias[entry["from"]] = entry["to"]
    for entry in query.get("redirects", []) or []:
        alias[entry["from"]] = entry["to"]
    result: dict[str, str] = {}
    for title in requested:
        current = title
        seen = {current}
        while current in alias and alias[current] not in seen:
            current = alias[current]
            seen.add(current)
        result[title] = current
    return result


async def _fetch_revid_batch(
    mw: MediaWikiClient, api_url: str, titles: list[str]
) -> dict[str, tuple[int | None, str | None]]:
    """One API request for up to ``REVID_BATCH_SIZE`` titles.

    Bypasses RawCache (no expiry there -- a cached revid would freeze change
    detection); keeps the per-host cooldown wait.
    """
    # NOTE: no rvlimit -- the API forbids revision-limiting params on
    # multi-page queries; without them each page returns its latest revision.
    params: dict[str, Any] = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "revisions",
        "rvprop": "ids|timestamp",
        "rvslots": "main",
        "redirects": "1",
        "titles": "|".join(titles),
    }
    host = urlparse(api_url).netloc
    await mw.cache.wait_for_cooldown(host, mw.min_interval_seconds)
    # NOTE: _api_get is the tenacity-wrapped transport; going through it
    # directly skips RawCache read+write on purpose (see module docstring).
    body = await asyncio.to_thread(mw._api_get, api_url, params)

    out: dict[str, tuple[int | None, str | None]] = {
        title: (None, None) for title in titles
    }
    canonical = _canonical_title_map(body, titles)
    pages = {
        page.get("title"): page
        for page in (body.get("query", {}) or {}).get("pages", [])
    }
    for requested in titles:
        page = pages.get(canonical.get(requested, requested))
        if not page or page.get("missing") or page.get("invalid"):
            continue
        revisions = page.get("revisions") or []
        if not revisions:
            continue
        rev = revisions[0]
        revid = _as_int(rev.get("revid"))
        out[requested] = (revid, rev.get("timestamp"))
    return out


async def batch_fetch_revids(
    mw: MediaWikiClient,
    api_url: str,
    titles: list[str],
    *,
    batch_size: int = REVID_BATCH_SIZE,
) -> dict[str, tuple[int | None, str | None]]:
    """Return ``{requested_title: (revid, timestamp)}`` for many titles.

    Titles are de-duplicated and queried in batches of ``batch_size`` (50)
    against a single api.php endpoint. Missing/invalid pages map to
    ``(None, None)``.
    """
    ordered = list(dict.fromkeys(t for t in titles if t))
    out: dict[str, tuple[int | None, str | None]] = {
        title: (None, None) for title in ordered
    }
    for start in range(0, len(ordered), batch_size):
        chunk = ordered[start : start + batch_size]
        try:
            out.update(await _fetch_revid_batch(mw, api_url, chunk))
        except Exception as exc:
            log.warning("revid batch failed for %d titles @ %s: %s", len(chunk), api_url, exc)
    return out


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------

_STORED_SQL = """
WITH ranked AS (
    SELECT ps.profile_id, ps.title, ps.url, cp.revid, cp.rev_timestamp,
           ROW_NUMBER() OVER (PARTITION BY ps.profile_id ORDER BY ps.source_id) AS rn
    FROM profile_sources ps
    JOIN character_profiles cp ON cp.profile_id = ps.profile_id
    WHERE ps.source_type = 'mediawiki'
)
SELECT profile_id, title, url, revid, rev_timestamp FROM ranked WHERE rn = 1
"""


@dataclass
class StoredRevid:
    profile_id: str
    revid: int | None
    rev_timestamp: datetime | None


@dataclass
class RevidDecision:
    title: str
    api_url: str
    profile_id: str | None
    stored_revid: int | None
    live_revid: int | None
    live_timestamp: str | None
    decision: str  # "harvest" | "skip" | "skip_existing"
    reason: str


class RevidGate:
    """Batch revid change detection for one harvest cycle.

    Usage (see docs/REVID_GATE_INTEGRATION.md for the harvester hook)::

        gate = RevidGate(harvester.mw)
        to_harvest, decisions = await gate.filter_rows(selected_rows)
        ... harvest to_harvest ...
        gate.log_summary()
    """

    def __init__(
        self,
        mw: MediaWikiClient,
        *,
        default_api: str = DEFAULT_MEDIAWIKI_API,
        dsn: str | None = None,
    ) -> None:
        self.mw = mw
        self.default_api = default_api
        self.dsn = dsn
        self.stats: dict[str, int] = {
            "revid_checked": 0,
            "revid_skipped": 0,
            "revid_changed": 0,
        }
        self._stored: dict[tuple[str, str], StoredRevid] | None = None

    # -- stored revids ----------------------------------------------------

    async def load_stored(self) -> dict[tuple[str, str], StoredRevid]:
        """Load {(host, canonical_title): StoredRevid} for primary sources."""
        if self._stored is not None:
            return self._stored
        stored: dict[tuple[str, str], StoredRevid] = {}
        async with connect_database(self.dsn) as conn:
            rows = await conn.fetch(_STORED_SQL)
        for row in rows:
            title = (row["title"] or "").strip()
            host = urlparse(row["url"] or "").netloc.lower()
            if not title or not host:
                continue
            key = (host, title)
            if key in stored:
                log.debug("duplicate primary source for %s; keeping first", key)
                continue
            stored[key] = StoredRevid(
                profile_id=row["profile_id"],
                revid=_as_int(row["revid"]),
                rev_timestamp=row["rev_timestamp"],
            )
        self._stored = stored
        log.info("revid gate: loaded %d stored primary-source revids", len(stored))
        return stored

    # -- live check -------------------------------------------------------

    @staticmethod
    def row_target(row: Any, default_api: str) -> tuple[str, str]:
        """(api_url, title) the harvester would fetch for this roster row."""
        api_url = mediawiki_api_from_url(getattr(row, "wiki_url", None)) or default_api
        title = (
            getattr(row, "wiki_title", None)
            or title_from_wiki_url(getattr(row, "wiki_url", None))
            or getattr(row, "name", "")
        )
        return api_url, (title or "").strip()

    async def check_batch(
        self, api_url: str, titles: list[str]
    ) -> list[RevidDecision]:
        """Check live revids for titles on one wiki; update stats."""
        stored = await self.load_stored()
        host = urlparse(api_url).netloc.lower()
        live = await batch_fetch_revids(self.mw, api_url, titles)
        decisions: list[RevidDecision] = []
        for title in titles:
            entry = stored.get((host, title))
            live_revid, live_ts = live.get(title, (None, None))
            self.stats["revid_checked"] += 1
            if live_revid is not None and entry is not None and entry.revid == live_revid:
                self.stats["revid_skipped"] += 1
                decisions.append(
                    RevidDecision(
                        title=title, api_url=api_url,
                        profile_id=entry.profile_id,
                        stored_revid=entry.revid,
                        live_revid=live_revid, live_timestamp=live_ts,
                        decision="skip", reason="revid_unchanged",
                    )
                )
                log.debug("revid skip: %s (revid %s unchanged)", title, live_revid)
            else:
                self.stats["revid_changed"] += 1
                reason = (
                    "no_live_revid" if live_revid is None
                    else "no_stored_revid" if entry is None or entry.revid is None
                    else "revid_changed"
                )
                decisions.append(
                    RevidDecision(
                        title=title, api_url=api_url,
                        profile_id=entry.profile_id if entry else None,
                        stored_revid=entry.revid if entry else None,
                        live_revid=live_revid, live_timestamp=live_ts,
                        decision="harvest", reason=reason,
                    )
                )
        return decisions

    async def filter_rows(
        self,
        rows: list[Any],
        *,
        output_dir: Path | None = None,
        needs_review_dir: Path | None = None,
    ) -> tuple[list[Any], list[RevidDecision]]:
        """Split roster rows into (to_harvest, decisions).

        Rows whose profile YAML already exists are marked ``skip_existing``
        without spending an API call (the harvester would skip them anyway);
        they are NOT counted in the revid stats.
        """
        pending: list[tuple[Any, str, str]] = []
        decisions: list[RevidDecision] = []
        for row in rows:
            if output_dir is not None and (
                profile_output_path(output_dir, row).exists()
                or (
                    needs_review_dir is not None
                    and profile_output_path(needs_review_dir, row).exists()
                )
            ):
                api_url, title = self.row_target(row, self.default_api)
                decisions.append(
                    RevidDecision(
                        title=title, api_url=api_url, profile_id=None,
                        stored_revid=None, live_revid=None, live_timestamp=None,
                        decision="skip_existing", reason="profile_yaml_exists",
                    )
                )
                continue
            api_url, title = self.row_target(row, self.default_api)
            if not title:
                decisions.append(
                    RevidDecision(
                        title="", api_url=api_url, profile_id=None,
                        stored_revid=None, live_revid=None, live_timestamp=None,
                        decision="harvest", reason="no_title",
                    )
                )
                self.stats["revid_checked"] += 1
                self.stats["revid_changed"] += 1
                pending.append((row, api_url, ""))
                continue
            pending.append((row, api_url, title))

        by_api: dict[str, list[str]] = {}
        for _row, api_url, title in pending:
            if title:
                by_api.setdefault(api_url, []).append(title)
        api_decisions: dict[tuple[str, str], RevidDecision] = {}
        for api_url, titles in by_api.items():
            for decision in await self.check_batch(api_url, titles):
                api_decisions[(api_url, decision.title)] = decision

        to_harvest: list[Any] = []
        for row, api_url, title in pending:
            if not title:
                to_harvest.append(row)
                continue
            decision = api_decisions[(api_url, title)]
            decisions.append(decision)
            if decision.decision == "harvest":
                to_harvest.append(row)
        return to_harvest, decisions

    # -- store ------------------------------------------------------------

    async def store_revid(
        self,
        profile_id: str,
        revid: int | None,
        rev_timestamp: datetime | str | None,
    ) -> None:
        """Persist the revid a profile was harvested from."""
        if revid is None:
            return
        ts = parse_rev_timestamp(rev_timestamp)
        async with connect_database(self.dsn) as conn:
            await conn.execute(
                """
                UPDATE character_profiles
                SET revid = $1, rev_timestamp = $2, updated_at = now()
                WHERE profile_id = $3
                """,
                int(revid),
                ts,
                profile_id,
            )

    # -- metrics ----------------------------------------------------------

    def summary(self) -> dict[str, int]:
        return dict(self.stats)

    def log_summary(self) -> None:
        s = self.stats
        log.info(
            "revid gate cycle: checked=%d skipped=%d changed=%d",
            s["revid_checked"], s["revid_skipped"], s["revid_changed"],
        )
        print(
            f"REVID GATE revid_checked={s['revid_checked']} "
            f"revid_skipped={s['revid_skipped']} "
            f"revid_changed={s['revid_changed']}",
            flush=True,
        )
