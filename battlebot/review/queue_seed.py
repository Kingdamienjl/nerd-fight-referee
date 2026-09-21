"""Seed profile repair jobs into the PostgreSQL queue."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from battlebot.common.db import apply_schema, connect_database
from battlebot.review import batch_promote, service
from battlebot.review.queue import enqueue_job


@dataclass
class SeedSummary:
    scanned: int = 0
    seeded: int = 0
    skipped_existing_output: int = 0
    skipped_existing_job: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "seeded": self.seeded,
            "skipped_existing_output": self.skipped_existing_output,
            "skipped_existing_job": self.skipped_existing_job,
        }


def profile_paths(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(target.rglob("*.yaml"))
    return [target] if target.exists() else []


def archived_destination(path: Path, *, needs_review_dir: Path, review_archive_dir: Path) -> Path:
    return review_archive_dir / service.relative_profile_tail(path, needs_review_dir)


def should_skip_output(path: Path, *, needs_review_dir: Path, generated_dir: Path, review_archive_dir: Path) -> bool:
    generated = batch_promote.generated_destination(path, needs_review_dir, generated_dir)
    archived = archived_destination(path, needs_review_dir=needs_review_dir, review_archive_dir=review_archive_dir)
    return generated.exists() or archived.exists()


async def seed_queue(
    connection: Any,
    *,
    target: Path,
    providers: str,
    priority: int,
    needs_review_dir: Path,
    generated_dir: Path,
    review_archive_dir: Path,
    max_attempts: int = 3,
) -> SeedSummary:
    summary = SeedSummary()
    for path in profile_paths(target):
        summary.scanned += 1
        if should_skip_output(
            path,
            needs_review_dir=needs_review_dir,
            generated_dir=generated_dir,
            review_archive_dir=review_archive_dir,
        ):
            summary.skipped_existing_output += 1
            continue
        inserted = await enqueue_job(
            connection,
            profile_path=str(path),
            target=str(target),
            providers=providers,
            priority=priority,
            max_attempts=max_attempts,
        )
        if inserted:
            summary.seeded += 1
        else:
            summary.skipped_existing_job += 1
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed needs_review profile repair jobs")
    parser.add_argument("--target", type=Path, default=service.DEFAULT_NEEDS_REVIEW_DIR)
    parser.add_argument("--providers", default=batch_promote.DEFAULT_PROVIDERS)
    parser.add_argument("--priority", type=int, default=100)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--database-url")
    parser.add_argument("--needs-review-dir", type=Path, default=service.DEFAULT_NEEDS_REVIEW_DIR)
    parser.add_argument("--generated-dir", type=Path, default=service.DEFAULT_GENERATED_DIR)
    parser.add_argument("--review-archive-dir", type=Path, default=Path("profiles/review_archive"))
    parser.add_argument("--json", action="store_true")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    async with connect_database(args.database_url) as connection:
        await apply_schema(connection)
        summary = await seed_queue(
            connection,
            target=args.target,
            providers=args.providers,
            priority=args.priority,
            needs_review_dir=args.needs_review_dir,
            generated_dir=args.generated_dir,
            review_archive_dir=args.review_archive_dir,
            max_attempts=args.max_attempts,
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
