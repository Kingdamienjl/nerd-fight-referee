"""Requeue profile jobs blocked only on human source choice."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any

from battlebot.common.db import apply_schema, connect_database
from battlebot.review import batch_promote


SOURCE_CHOICE_FILTER_SQL = """
status = 'needs_review'
AND (
    profile_path LIKE 'profiles/needs_review/%'
    OR position('/profiles/needs_review/' in profile_path) > 0
)
AND position('/user-requests/' in profile_path) = 0
AND position('/profiles/quarantined/' in profile_path) = 0
AND target NOT ILIKE '%user request%'
AND (
    COALESCE(last_summary->'top_missing_fields' ? 'needs_human_source_choice', false)
    OR COALESCE(last_summary->'failure_reasons' ? 'needs_human_source_choice', false)
    OR COALESCE(last_summary::text LIKE '%needs_human_source_choice%', false)
)
"""


@dataclass
class RequeueSummary:
    matched: int = 0
    requeued: int = 0
    dry_run: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"matched": self.matched, "requeued": self.requeued, "dry_run": self.dry_run}


async def requeue_needs_human_source_choice(
    connection: Any,
    *,
    providers: str = batch_promote.DEFAULT_PROVIDERS,
    priority: int = 10,
    dry_run: bool = False,
) -> RequeueSummary:
    matched = int(
        await connection.fetchval(
            f"""
SELECT count(*)
FROM profile_jobs
WHERE {SOURCE_CHOICE_FILTER_SQL}
"""
        )
        or 0
    )
    if dry_run or matched == 0:
        return RequeueSummary(matched=matched, requeued=0, dry_run=dry_run)

    requeued = int(
        await connection.fetchval(
            f"""
WITH updated AS (
    UPDATE profile_jobs
SET status = 'pending',
    providers = $1,
    priority = $2,
    next_attempt_at = now(),
    locked_at = NULL,
    worker_id = NULL,
    last_error = NULL,
    updated_at = now()
WHERE {SOURCE_CHOICE_FILTER_SQL}
    RETURNING 1
)
SELECT count(*) FROM updated
""",
            providers,
            priority,
        )
        or 0
    )
    return RequeueSummary(matched=matched, requeued=requeued, dry_run=False)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Requeue profile jobs blocked by needs_human_source_choice")
    parser.add_argument("--database-url")
    parser.add_argument("--providers", default=batch_promote.DEFAULT_PROVIDERS)
    parser.add_argument("--priority", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    async with connect_database(args.database_url) as connection:
        await apply_schema(connection)
        summary = await requeue_needs_human_source_choice(
            connection,
            providers=args.providers,
            priority=args.priority,
            dry_run=args.dry_run,
        )
    if args.json:
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    else:
        for key, value in summary.as_dict().items():
            print(f"{key}: {value}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
