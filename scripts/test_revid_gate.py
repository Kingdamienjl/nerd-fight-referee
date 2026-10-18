"""Tests for the revid change-detection gate.

Run inside the harvester container (has deps + DATABASE_URL), with the new
modules copied in -- does NOT disturb the running harvester process:

    docker cp src/battlebot/harvest/revid_checker.py \
        referee-harvester-1:/app/src/battlebot/harvest/revid_checker.py
    docker cp scripts/test_revid_gate.py referee-harvester-1:/tmp/test_revid_gate.py
    docker exec referee-harvester-1 python /tmp/test_revid_gate.py

Covers:
  1. batch_fetch_revids against 10 real wiki pages (live API)
  2. gate skip/harvest decisions (forged stored revids -- no DB writes)
  3. load_stored() against the backfilled DB (read-only)
  4. primary_mediawiki_revid unit checks
  5. per-cycle metric accounting
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from battlebot.common.db import connect_database
from battlebot.harvest.auto_profile_harvester import (
    DEFAULT_MEDIAWIKI_API,
    RosterRow,
)
from battlebot.harvest.revid_checker import (
    RevidGate,
    StoredRevid,
    batch_fetch_revids,
    build_mediawiki_client,
    primary_mediawiki_revid,
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not cond else ""))


async def test_batch_query_live() -> None:
    """10 real pages -> every one returns an int revid + ISO timestamp."""
    async with connect_database() as conn:
        rows = await conn.fetch(
            """
            SELECT ps.title, max(cp.rev_timestamp) AS ts
            FROM profile_sources ps
            JOIN character_profiles cp ON cp.profile_id = ps.profile_id
            WHERE ps.source_type = 'mediawiki'
              AND ps.url LIKE '%vsbattles.fandom.com%'
              AND ps.title IS NOT NULL AND ps.title <> ''
            GROUP BY ps.title
            ORDER BY ts DESC
            LIMIT 10
            """
        )
    titles = [r["title"] for r in rows]
    check("batch: got 10 titles from DB", len(titles) == 10, f"got {len(titles)}")
    if not titles:
        return
    mw = build_mediawiki_client(cache_dir=tempfile.mkdtemp(prefix="revid_test_"))
    out = await batch_fetch_revids(mw, DEFAULT_MEDIAWIKI_API, titles)
    check("batch: all titles present in result", set(out) == set(titles))
    good = {
        t: v for t, v in out.items()
        if isinstance(v[0], int) and v[0] > 0 and isinstance(v[1], str) and "T" in v[1]
    }
    missing = [t for t, v in out.items() if v == (None, None)]
    # Some wiki pages get renamed/deleted after harvest; those legitimately
    # come back (None, None) and the gate treats them as "harvest".
    check("batch: most titles -> (int revid, ISO timestamp)", len(good) >= 8,
          f"good={len(good)} missing={missing}")
    print(f"       sample: {next(iter(good))!r} -> revid={good[next(iter(good))][0]}"
          if good else "       (no resolving titles)")
    if missing:
        print(f"       note: {len(missing)} renamed/deleted since harvest: {missing}")


async def test_gate_decisions() -> None:
    """Simulate skip / changed / missing-stored without touching the DB."""
    async with connect_database() as conn:
        row = await conn.fetchrow(
            """
            SELECT ps.profile_id, ps.title, ps.url, cp.revid
            FROM profile_sources ps
            JOIN character_profiles cp ON cp.profile_id = ps.profile_id
            WHERE ps.source_type = 'mediawiki'
              AND ps.url LIKE '%vsbattles.fandom.com%'
              AND cp.revid IS NOT NULL
            LIMIT 1
            """
        )
    check("sim: found a backfilled profile", row is not None)
    if not row:
        return
    profile_id, title, url, stored_revid = row["profile_id"], row["title"], row["url"], int(row["revid"])
    host = urlparse(url).netloc.lower()
    mw = build_mediawiki_client(cache_dir=tempfile.mkdtemp(prefix="revid_test_"))
    roster_row = RosterRow(category="test", franchise="test", name=title, wiki_title=title)
    tmp = Path(tempfile.mkdtemp(prefix="revid_out_"))

    async def decide_with(stored: dict | None) -> tuple:
        gate = RevidGate(mw)
        if stored is not None:
            gate._stored = stored
        else:
            gate._stored = {}
        to_harvest, decisions = await gate.filter_rows(
            [roster_row], output_dir=tmp, needs_review_dir=tmp
        )
        return gate, to_harvest, decisions[0]

    # live revid straight from the API for ground truth
    live = await batch_fetch_revids(mw, DEFAULT_MEDIAWIKI_API, [title])
    live_revid, _live_ts = live[title]
    check("sim: live revid fetched", isinstance(live_revid, int) and live_revid > 0,
          f"live={live_revid} stored={stored_revid}")

    # case A: stored == live -> skip
    gate, to_harvest, d = await decide_with(
        {(host, title): StoredRevid(profile_id, live_revid, None)}
    )
    check("sim: unchanged revid -> skip", d.decision == "skip" and not to_harvest,
          f"decision={d.decision} reason={d.reason}")

    # case B: stored revid differs -> harvest
    gate2, to_harvest2, d2 = await decide_with(
        {(host, title): StoredRevid(profile_id, 1, None)}
    )
    check("sim: changed revid -> harvest", d2.decision == "harvest" and to_harvest2 == [roster_row]
          and d2.reason == "revid_changed",
          f"decision={d2.decision} reason={d2.reason}")

    # case C: no stored revid -> harvest
    gate3, to_harvest3, d3 = await decide_with({})
    check("sim: no stored revid -> harvest", d3.decision == "harvest"
          and d3.reason == "no_stored_revid",
          f"decision={d3.decision} reason={d3.reason}")

    # metrics: 3 checked == 1 skipped + 2 changed  (fresh gate for clean counts)
    gate4 = RevidGate(mw)
    gate4._stored = {(host, title): StoredRevid(profile_id, live_revid, None)}
    await gate4.filter_rows([roster_row], output_dir=tmp, needs_review_dir=tmp)
    gate4._stored = {(host, title): StoredRevid(profile_id, 1, None)}
    await gate4.filter_rows([roster_row], output_dir=tmp, needs_review_dir=tmp)
    gate4._stored = {}
    await gate4.filter_rows([roster_row], output_dir=tmp, needs_review_dir=tmp)
    s = gate4.summary()
    check("metrics: checked == skipped + changed",
          s["revid_checked"] == 3 and s["revid_skipped"] == 1 and s["revid_changed"] == 2,
          str(s))


async def test_load_stored_readonly() -> None:
    """load_stored() returns sane data from the backfilled DB (read-only)."""
    mw = build_mediawiki_client(cache_dir=tempfile.mkdtemp(prefix="revid_test_"))
    gate = RevidGate(mw)
    stored = await gate.load_stored()
    # 2063 profiles but fewer unique (host, title) pairs: classic/modern/
    # composite variants of one character share the same wiki source page.
    check("load_stored: non-empty", len(stored) > 1500, f"n={len(stored)}")
    with_revid = sum(1 for s in stored.values() if s.revid)
    check("load_stored: most entries have a revid", with_revid > 1500, f"n={with_revid}")
    sample = next(iter(stored.items()))
    check("load_stored: key=(host,title) value has profile_id",
          isinstance(sample[0][0], str) and isinstance(sample[0][1], str)
          and bool(sample[1].profile_id),
          str(sample))


def test_primary_mediawiki_revid_unit() -> None:
    sources = [
        {"source_type": "anilist", "source_id": "anilist:1", "revision_id": None,
         "revision_timestamp": None},
        {"source_type": "mediawiki", "source_id": "mediawiki:zzz",
         "revision_id": "999", "revision_timestamp": "2026-10-10T00:00:00Z"},
        {"source_type": "mediawiki", "source_id": "mediawiki:aaa",
         "revision_id": "12345", "revision_timestamp": "2026-10-11T01:02:03Z"},
        {"source_type": "mediawiki", "source_id": "mediawiki:mmm",
         "revision_id": "", "revision_timestamp": None},
    ]
    revid, ts = primary_mediawiki_revid(sources)
    check("primary_mediawiki_revid: picks smallest source_id with numeric revid",
          revid == 12345 and ts is not None and ts.year == 2026,
          f"got {(revid, ts)}")
    check("primary_mediawiki_revid: empty -> (None, None)",
          primary_mediawiki_revid([]) == (None, None))


async def async_main() -> int:
    test_primary_mediawiki_revid_unit()
    await test_batch_query_live()
    await test_gate_decisions()
    await test_load_stored_readonly()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILURES:", FAIL)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(async_main()))
