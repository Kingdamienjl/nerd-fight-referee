"""One-time backfill of character_profiles.revid / rev_timestamp.

Step 1 (no API calls): copy the harvest-time revision_id/revision_timestamp
from each profile's primary mediawiki source (smallest source_id) into the
new character_profiles columns. This is the semantically correct seed: the
revid the profile was actually harvested from, so the revid gate skips it
until the wiki page really changes.

Step 2 (--live): for profiles still missing a revid after step 1, query the
live MediaWiki API in batches of 50 and store the result. (In practice step 1
covers every profile; --live exists for gaps and is exercised by the test
script on a small sample.)

Usage:
    python -m battlebot.harvest.backfill_revids [--live] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import urlparse

from battlebot.common.db import connect_database
from battlebot.harvest.revid_checker import (
    REVID_BATCH_SIZE,
    batch_fetch_revids,
    build_mediawiki_client,
    parse_rev_timestamp,
)

COPY_SQL = """
WITH ranked AS (
    SELECT ps.profile_id, ps.revision_id, ps.revision_timestamp,
           ROW_NUMBER() OVER (PARTITION BY ps.profile_id ORDER BY ps.source_id) AS rn
    FROM profile_sources ps
    WHERE ps.source_type = 'mediawiki'
      AND ps.revision_id ~ '^[0-9]+$'
      AND ps.revision_timestamp ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
)
UPDATE character_profiles cp
SET revid = r.revision_id::bigint,
    rev_timestamp = r.revision_timestamp::timestamptz,
    updated_at = now()
FROM ranked r
WHERE r.rn = 1
  AND cp.profile_id = r.profile_id
  AND (cp.revid IS NULL OR cp.revid <> r.revision_id::bigint)
"""

MISSING_SQL = """
WITH ranked AS (
    SELECT ps.profile_id, ps.title, ps.url,
           ROW_NUMBER() OVER (PARTITION BY ps.profile_id ORDER BY ps.source_id) AS rn
    FROM profile_sources ps
    WHERE ps.source_type = 'mediawiki'
)
SELECT r.profile_id, r.title, r.url
FROM ranked r
JOIN character_profiles cp ON cp.profile_id = r.profile_id
WHERE r.rn = 1 AND cp.revid IS NULL AND r.title IS NOT NULL AND r.title <> ''
"""


async def backfill_from_sources(dry_run: bool = False) -> int:
    async with connect_database() as conn:
        if dry_run:
            row = await conn.fetchrow(
                "SELECT count(*) AS n FROM character_profiles WHERE revid IS NULL"
            )
            print(f"DRY RUN: {row['n']} profiles currently have NULL revid")
            return 0
        result = await conn.execute(COPY_SQL)
        # asyncpg returns e.g. "UPDATE 123"
        updated = int(result.split()[-1]) if result.split()[-1].isdigit() else -1
        print(f"backfill step 1 (from profile_sources): updated {updated} profiles")
        return updated


async def backfill_live(batch_size: int = REVID_BATCH_SIZE) -> int:
    """Query live revids for profiles still missing one; store them."""
    async with connect_database() as conn:
        rows = await conn.fetch(MISSING_SQL)
    if not rows:
        print("backfill step 2 (live API): no profiles missing revids")
        return 0
    by_host: dict[str, list[tuple[str, str]]] = {}
    for row in rows:
        host = urlparse(row["url"] or "").netloc.lower()
        if host and row["title"]:
            by_host.setdefault(host, []).append((row["profile_id"], row["title"]))
    mw = build_mediawiki_client()
    stored = 0
    for host, items in by_host.items():
        api_url = f"https://{host}/api.php"
        titles = [title for _pid, title in items]
        live = await batch_fetch_revids(mw, api_url, titles, batch_size=batch_size)
        async with connect_database() as conn:
            for profile_id, title in items:
                revid, ts = live.get(title, (None, None))
                if revid is None:
                    continue
                await conn.execute(
                    """
                    UPDATE character_profiles
                    SET revid = $1, rev_timestamp = $2, updated_at = now()
                    WHERE profile_id = $3 AND revid IS NULL
                    """,
                    revid,
                    parse_rev_timestamp(ts),
                    profile_id,
                )
                stored += 1
    print(f"backfill step 2 (live API): stored {stored} revids across {len(by_host)} wikis")
    return stored


async def report() -> None:
    async with connect_database() as conn:
        total = await conn.fetchval("SELECT count(*) FROM character_profiles")
        with_revid = await conn.fetchval(
            "SELECT count(*) FROM character_profiles WHERE revid IS NOT NULL"
        )
        with_ts = await conn.fetchval(
            "SELECT count(*) FROM character_profiles WHERE rev_timestamp IS NOT NULL"
        )
    print(f"character_profiles: total={total} with_revid={with_revid} with_rev_timestamp={with_ts}")


async def async_main(args: argparse.Namespace) -> int:
    await backfill_from_sources(dry_run=args.dry_run)
    if args.live and not args.dry_run:
        await backfill_live()
    await report()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="also query the live API for profiles still missing revids")
    parser.add_argument("--dry-run", action="store_true",
                        help="report counts without writing")
    args = parser.parse_args()
    sys.exit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
