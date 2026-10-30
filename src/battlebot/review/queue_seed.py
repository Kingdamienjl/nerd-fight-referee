"""Seed profile repair jobs into the PostgreSQL queue."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from battlebot.common.db import apply_schema, connect_database
from battlebot.review import batch_promote, service
from battlebot.review.queue import enqueue_job, priority_for_blocker_count


@dataclass
class SeedSummary:
    scanned: int = 0
    seeded: int = 0
    skipped_existing_output: int = 0
    skipped_existing_job: int = 0
    requeued: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "seeded": self.seeded,
            "skipped_existing_output": self.skipped_existing_output,
            "skipped_existing_job": self.skipped_existing_job,
            "requeued": self.requeued,
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


def assessed_priority(path: Path, *, default: int) -> int:
    """Priority for a job about to be (re)inserted: 1 + blocker count.

    Falls back to the caller's default when the profile cannot be
    loaded or assessed, so a malformed file never blocks seeding.
    """
    try:
        profile = service.load_yaml(path)
        blockers = service.approval_blockers(profile)
    except Exception:
        return default
    return priority_for_blocker_count(len(blockers))


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
    terminal_rows = await connection.fetch(
        "SELECT profile_path, status, updated_at FROM profile_jobs "
        "WHERE status IN ('needs_review', 'failed')"
    )
    terminal_jobs = {
        str(row["profile_path"]): (str(row["status"]), row["updated_at"])
        for row in terminal_rows
    }
    active_rows = await connection.fetch(
        "SELECT profile_path FROM profile_jobs "
        "WHERE status IN ('pending', 'retry', 'running')"
    )
    active_jobs = {str(row["profile_path"]) for row in active_rows}
    now = datetime.now(UTC)
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
        # A terminal job may be re-queued only when its inputs plausibly
        # changed: the profile file was rewritten after the job's last
        # attempt, or a failed job has been sitting for a week. Anything
        # else stays terminal so blocked profiles cannot spin the queue.
        requeue = False
        terminal = terminal_jobs.get(str(path))
        if terminal is not None:
            job_status, job_updated_at = terminal
            try:
                file_changed = datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ) > job_updated_at + timedelta(hours=1)
            except OSError:
                file_changed = False
            stale_failed = job_status == "failed" and job_updated_at < now - timedelta(days=7)
            requeue = file_changed or stale_failed
        # Only genuinely new inserts and terminal requeues pay for a
        # fresh blocker assessment: a file with no job row at all, or a
        # terminal job whose inputs changed. A terminal job that stays
        # parked is a no-op in enqueue_job(), and a job that already
        # exists and is claimable keeps the priority it was stored
        # with — assessing either is pure waste, and the computed
        # priority is discarded. (The old guard assessed every
        # non-active file: ~2,365 full load_yaml + approval_blockers
        # calls per worker per cycle, ~7 min/cycle, host load 6+ on
        # 4 CPUs, for zero effect.)
        job_priority = priority
        if (terminal is None and str(path) not in active_jobs) or requeue:
            job_priority = assessed_priority(path, default=priority)
        inserted = await enqueue_job(
            connection,
            profile_path=str(path),
            target=str(target),
            providers=providers,
            priority=job_priority,
            max_attempts=max_attempts,
            requeue=requeue,
        )
        if inserted:
            summary.seeded += 1
            if terminal is not None:
                summary.requeued += 1
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
