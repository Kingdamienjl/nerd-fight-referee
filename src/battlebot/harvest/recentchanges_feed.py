"""Supplementary recentchanges feed for the profile harvester.

Polls the VS Battles Wiki MediaWiki ``recentchanges`` API, filters to the main
(character) namespace, and appends changed page titles to a queue file that the
harvester can later consume for re-harvest prioritization.

This module is intentionally STANDALONE and SAFE:

* It does not import or touch the core harvest loop (``auto_profile_harvester``)
  or the CSV roster cycling. CSV rosters remain the primary mechanism until this
  feed proves stable.
* It uses only the Python stdlib (``urllib``) for the API poll -- no pywikibot
  config state, no interactive setup, zero new dependency risk for the running
  harvester container. (pywikibot is installed in the container for other work;
  the raw ``action=query&list=recentchanges`` call was chosen here because it is
  the more reliable transport for a minimal unattended poll.)
* It is OFF by default: loop mode only runs when ``HARVEST_RC_FEED_ENABLED=1``.
  ``--once`` is the explicit manual entry point and always performs one poll.

State (incremental watermark) and the title queue live under the repo ``data/``
directory, which is bind-mounted into the harvester container (``/app/data``).

Usage::

    python -m battlebot.harvest.recentchanges_feed --once
    python -m battlebot.harvest.recentchanges_feed --loop --interval 600

Environment::

    HARVEST_RC_FEED_ENABLED   1/true to enable loop mode (default: off)
    HARVEST_RC_API_URL        MediaWiki api.php URL (default: vsbattles.fandom.com)
    HARVEST_RC_STATE_FILE     watermark file (default: <repo>/data/recentchanges_state.json)
    HARVEST_RC_QUEUE_FILE     queue file   (default: <repo>/data/recentchanges_queue.json)
    HARVEST_RC_INTERVAL       loop seconds (default: 600)
    HARVEST_RC_MAX_QUEUE      max queued titles kept (default: 2000)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_API_URL = "https://vsbattles.fandom.com/api.php"
USER_AGENT = "nerd-referee-rcfeed/1.0 (supplementary harvester poll; contact: repo maintainer)"

MAIN_NAMESPACE = 0  # character pages live in the main namespace

# First-run bootstrap: queue at most this many of the most recent changes so the
# queue is non-empty for verification, then switch to incremental polling.
BOOTSTRAP_LIMIT = 100
PER_POLL_LIMIT = 500  # MediaWiki max for normal users
MAX_QUEUE_DEFAULT = 2000
RETRIES = 3
RETRY_BACKOFF_S = 5
REQUEST_TIMEOUT_S = 30


# ---------------------------------------------------------------------------
# config helpers
# ---------------------------------------------------------------------------

def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def feed_enabled() -> bool:
    """Loop mode toggle. Default off."""
    return _truthy(os.environ.get("HARVEST_RC_FEED_ENABLED"))


def _repo_data_dir() -> Path:
    """Locate <repo>/data by walking up from this file to pyproject.toml."""
    here = Path(__file__).resolve()
    for parent in (here,) + tuple(here.parents):
        if (parent / "pyproject.toml").exists():
            data = parent / "data"
            data.mkdir(parents=True, exist_ok=True)
            return data
    fallback = Path("/opt/referee/data")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def default_state_path() -> Path:
    return Path(os.environ.get("HARVEST_RC_STATE_FILE", _repo_data_dir() / "recentchanges_state.json"))


def default_queue_path() -> Path:
    return Path(os.environ.get("HARVEST_RC_QUEUE_FILE", _repo_data_dir() / "recentchanges_queue.json"))


def api_url() -> str:
    return os.environ.get("HARVEST_RC_API_URL", DEFAULT_API_URL)


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# state + queue persistence
# ---------------------------------------------------------------------------

def load_state(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
        if isinstance(state, dict) and state.get("last_rcid"):
            return state
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_queue(path: Path) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict) and e.get("title")]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def save_queue(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def merge_into_queue(queue: list[dict], new_entries: list[dict], max_queue: int) -> list[dict]:
    """Merge new entries, deduped by title (newest wins), capped at max_queue."""
    by_title: dict[str, dict] = {e["title"]: e for e in queue}
    for entry in new_entries:
        by_title[entry["title"]] = entry
    merged = sorted(by_title.values(), key=lambda e: (e.get("timestamp", ""), e.get("rcid", 0)))
    if len(merged) > max_queue:
        merged = merged[-max_queue:]
    return merged


# ---------------------------------------------------------------------------
# MediaWiki recentchanges poll (stdlib only)
# ---------------------------------------------------------------------------

def _api_get(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
    last_exc: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
                return json.load(resp)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < RETRIES:
                time.sleep(RETRY_BACKOFF_S * attempt)
    raise RuntimeError(f"MediaWiki API request failed after {RETRIES} attempts: {last_exc}")


def fetch_recent_changes(
    url: str,
    *,
    since_timestamp: str | None = None,
    limit: int = PER_POLL_LIMIT,
    newest_first: bool = False,
) -> list[dict]:
    """Fetch recentchanges rows for the main namespace.

    With ``since_timestamp`` set, walks forward (``rcdir=newer``) from that
    timestamp, following ``continue`` until exhausted. Otherwise returns the
    most recent rows (``rcdir=older``), up to ``limit``.
    """
    rows: list[dict] = []
    cont: dict = {}
    while True:
        params = {
            "action": "query",
            "list": "recentchanges",
            "rcnamespace": str(MAIN_NAMESPACE),
            "rclimit": str(min(limit, PER_POLL_LIMIT)),
            "rcprop": "title|ids|timestamp|user|comment|sizes",
            "rctype": "edit|new",
            "rcdir": "older" if newest_first else "newer",
            "format": "json",
            "formatversion": "2",
        }
        if since_timestamp:
            params["rcstart"] = since_timestamp
        params.update(cont)
        data = _api_get(url, params)
        batch = data.get("query", {}).get("recentchanges", [])
        rows.extend(batch)
        cont = data.get("continue", {})
        if not cont or (since_timestamp is None and len(rows) >= limit):
            break
        if len(rows) >= 5000:  # sanity cap per poll
            break
    return rows[:limit] if since_timestamp is None else rows


def _to_queue_entry(row: dict) -> dict:
    return {
        "title": row.get("title", ""),
        "pageid": row.get("pageid"),
        "rcid": row.get("rcid"),
        "revid": row.get("revid"),
        "timestamp": row.get("timestamp", ""),
        "user": row.get("user", ""),
        "change_type": row.get("type", ""),
        "comment": (row.get("comment") or "")[:200],
        "queued_at": utcnow_iso(),
        "source": "recentchanges_feed",
    }


# ---------------------------------------------------------------------------
# poll orchestration
# ---------------------------------------------------------------------------

def poll_once(
    *,
    url: str | None = None,
    state_path: Path | None = None,
    queue_path: Path | None = None,
    bootstrap_limit: int = BOOTSTRAP_LIMIT,
    per_poll_limit: int = PER_POLL_LIMIT,
    max_queue: int = MAX_QUEUE_DEFAULT,
) -> dict:
    """Do one incremental poll. Returns a summary dict."""
    url = url or api_url()
    state_path = state_path or default_state_path()
    queue_path = queue_path or default_queue_path()

    state = load_state(state_path)
    last_rcid = int(state.get("last_rcid") or 0)
    last_ts = state.get("last_timestamp")

    if not last_rcid or not last_ts:
        # First run: bootstrap from the most recent changes so the queue is
        # non-empty and verifiable, then switch to incremental mode.
        rows = fetch_recent_changes(url, limit=bootstrap_limit, newest_first=True)
        fresh = [r for r in rows if r.get("ns") == MAIN_NAMESPACE and r.get("title")]
        bootstrapped = True
    else:
        rows = fetch_recent_changes(url, since_timestamp=last_ts, limit=per_poll_limit)
        # rcstart is inclusive: drop the boundary row(s) already watermarked.
        fresh = [r for r in rows if r.get("ns") == MAIN_NAMESPACE and int(r.get("rcid") or 0) > last_rcid]
        bootstrapped = False

    fresh.sort(key=lambda r: (r.get("timestamp", ""), int(r.get("rcid") or 0)))
    new_entries = [_to_queue_entry(r) for r in fresh if r.get("title")]

    if new_entries:
        queue = load_queue(queue_path)
        queue = merge_into_queue(queue, new_entries, max_queue)
        save_queue(queue_path, queue)
    else:
        queue = load_queue(queue_path)

    # Advance the watermark to the newest row seen (even if filtered out, so we
    # never re-scan the same window).
    watermark_src = rows if rows else fresh
    if watermark_src:
        newest = max(watermark_src, key=lambda r: int(r.get("rcid") or 0))
        state = {
            "last_rcid": int(newest.get("rcid") or 0),
            "last_timestamp": newest.get("timestamp", ""),
            "last_title": newest.get("title", ""),
            "updated_at": utcnow_iso(),
            "api_url": url,
        }
        save_state(state_path, state)

    return {
        "bootstrapped": bootstrapped,
        "rows_seen": len(rows),
        "titles_queued": len(new_entries),
        "queue_size": len(queue),
        "last_rcid": state.get("last_rcid"),
        "last_timestamp": state.get("last_timestamp"),
        "state_path": str(state_path),
        "queue_path": str(queue_path),
    }


def run_loop(*, interval_s: int, **poll_kwargs) -> None:
    print(f"[rc-feed] loop starting (interval={interval_s}s, enabled={feed_enabled()})", flush=True)
    while True:
        try:
            summary = poll_once(**poll_kwargs)
            print(
                f"[rc-feed] poll ok: +{summary['titles_queued']} titles "
                f"(queue={summary['queue_size']}, rcid={summary['last_rcid']})",
                flush=True,
            )
        except Exception as exc:  # never kill a loop on one bad poll
            print(f"[rc-feed] poll failed: {exc}", flush=True)
        time.sleep(interval_s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Supplementary recentchanges feed (default off).")
    parser.add_argument("--once", action="store_true", help="do a single poll and update state/queue")
    parser.add_argument("--loop", action="store_true", help="poll forever (requires HARVEST_RC_FEED_ENABLED=1)")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("HARVEST_RC_INTERVAL", "600")))
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--state-file", default=None)
    parser.add_argument("--queue-file", default=None)
    parser.add_argument("--bootstrap-limit", type=int, default=BOOTSTRAP_LIMIT)
    parser.add_argument("--max-queue", type=int, default=int(os.environ.get("HARVEST_RC_MAX_QUEUE", str(MAX_QUEUE_DEFAULT))))
    args = parser.parse_args(argv)

    poll_kwargs = {
        "url": args.api_url or api_url(),
        "state_path": Path(args.state_file) if args.state_file else None,
        "queue_path": Path(args.queue_file) if args.queue_file else None,
        "bootstrap_limit": args.bootstrap_limit,
        "max_queue": args.max_queue,
    }

    if args.loop:
        if not feed_enabled():
            print("[rc-feed] HARVEST_RC_FEED_ENABLED is not set -- loop mode disabled by default.", file=sys.stderr)
            return 2
        run_loop(interval_s=args.interval, **poll_kwargs)
        return 0

    if args.once:
        if not feed_enabled():
            print("[rc-feed] note: HARVEST_RC_FEED_ENABLED is off; --once runs anyway (explicit invocation).")
        summary = poll_once(**poll_kwargs)
        print(json.dumps(summary, indent=2))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
