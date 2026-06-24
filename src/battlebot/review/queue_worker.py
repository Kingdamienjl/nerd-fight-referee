"""Process PostgreSQL-backed profile repair jobs."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from battlebot.common.db import apply_schema, connect_database
from battlebot.profiles import yaml_io
from battlebot.ingest import import_profiles
from battlebot.review import batch_promote, service
from battlebot.review.queue import claim_jobs, mark_job, mark_retry


PROVIDER_HOSTS = {
    "vsbattles": "vsbattles.fandom.com",
    "character_stats_profiles": "character-stats-and-profiles.fandom.com",
    "superherodb": "superherodb.com",
    "kaggle_superherodb": "kaggle.local",
}


@dataclass
class WorkerSummary:
    claimed: int = 0
    promoted: int = 0
    needs_review: int = 0
    retry: int = 0
    failed: int = 0
    quarantined: int = 0
    imported: int = 0
    errors: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "claimed": self.claimed,
            "promoted": self.promoted,
            "needs_review": self.needs_review,
            "retry": self.retry,
            "failed": self.failed,
            "quarantined": self.quarantined,
            "imported": self.imported,
            "errors": self.errors or [],
        }


class ProviderPoliteness:
    def __init__(self, sleep_seconds: float = 1.0):
        self.sleep_seconds = sleep_seconds
        self._locks: dict[str, asyncio.Lock] = {}

    def hosts_for(self, providers: str) -> list[str]:
        hosts = []
        for provider in [value.strip() for value in providers.split(",") if value.strip()]:
            hosts.append(PROVIDER_HOSTS.get(provider, provider))
        return sorted(set(hosts))

    async def run(self, providers: str, callback):
        hosts = self.hosts_for(providers)
        locks = [self._locks.setdefault(host, asyncio.Lock()) for host in hosts]
        for lock in locks:
            await lock.acquire()
        try:
            return await callback()
        finally:
            if self.sleep_seconds > 0:
                await asyncio.sleep(self.sleep_seconds)
            for lock in reversed(locks):
                lock.release()


def args_for_job(job: dict[str, Any], args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        target=Path(job["profile_path"]),
        max_profiles=1,
        dry_run=False,
        overwrite=args.overwrite,
        move=args.move,
        needs_review_dir=args.needs_review_dir,
        generated_dir=args.generated_dir,
        review_archive_dir=args.review_archive_dir,
        quarantine_dir=args.quarantine_dir,
        keep_review_copy=args.keep_review_copy,
        max_attempts=int(job.get("max_attempts") or args.max_attempts),
        roster_dir=args.roster_dir,
        notes_path=args.notes_path,
        source_timeout_seconds=args.source_timeout_seconds,
        verbose=args.verbose,
        debug_dir=args.debug_dir,
        max_source_candidates=args.max_source_candidates,
        providers=job["providers"],
        fetch_in_dry_run=False,
    )


async def import_generated_profiles(generated_dir: Path, *, database_url: str | None) -> int:
    compiled, summary = import_profiles.build_import_plan(
        generated_dir,
        import_profiles.ImportOptions(changed_only=False),
    )
    await import_profiles.import_compiled_profiles(
        compiled,
        database_url=database_url,
        wipe_profiles=False,
    )
    return summary.imported


def job_error(summary: dict[str, Any]) -> str:
    failures = summary.get("failures") or []
    if failures:
        return str(failures[0])
    reasons = summary.get("failure_reasons") or {}
    if reasons:
        return ", ".join(str(key) for key in reasons)
    return "profile repair did not promote"


def slugify_user_request(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unknown"


def ensure_user_request_profile(job: dict[str, Any]) -> None:
    profile_path = Path(str(job.get("profile_path") or ""))
    target = str(job.get("target") or "").strip()

    if not target or profile_path.exists():
        return

    if "profiles/needs_review/mixed/user-requests/" not in profile_path.as_posix():
        return

    slug = slugify_user_request(target)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        "\n".join(
            [
                f"id: mixed-user-requests-{slug}",
                f"name: {target}",
                "category: mixed",
                "franchise: User Requests",
                "status: needs_review",
                "battle_eligible: false",
                "generation:",
                "  generator: battlebot.review.queue_worker",
                "  confidence: 0.05",
                "  ineligible_reasons:",
                "  - queued_user_request",
                "approval_blockers:",
                "  - user_request_skeleton_schema_incomplete",
                "review:",
                "  reasons:",
                "  - queued_user_request",
                "sources: []",
                "",
            ]
        ),
        encoding="utf-8",
    )


async def process_job(connection: Any, job: dict[str, Any], args: argparse.Namespace) -> str:
    try:
        ensure_user_request_profile(job)
        summary = await batch_promote.batch_promote(args_for_job(job, args))
        data = summary.as_dict()
        if summary.promoted:
            await mark_job(connection, int(job["id"]), status="promoted", summary=data)
            return "promoted"
        if summary.retry or summary.retryable_failures:
            return await mark_retry(connection, job, summary=data, error=job_error(data))
        if summary.quarantined:
            await mark_job(connection, int(job["id"]), status="quarantined", summary=data, error=job_error(data))
            return "quarantined"
        if summary.failed or summary.deterministic_failures:
            if int(job.get("attempts") or 0) >= int(job.get("max_attempts") or args.max_attempts):
                await mark_job(connection, int(job["id"]), status="failed", summary=data, error=job_error(data))
                return "failed"
            return await mark_retry(connection, job, summary=data, error=job_error(data))
        await mark_job(connection, int(job["id"]), status="needs_review", summary=data)
        return "needs_review"
    except Exception as exc:  # noqa: BLE001 - one job must not kill the worker batch.
        data = {"exception": type(exc).__name__, "error": str(exc)}
        if batch_promote.is_malformed_yaml_exception(exc):
            if Path(job["profile_path"]).exists():
                result = yaml_io.quarantine_file(
                    Path(job["profile_path"]),
                    error=exc,
                    quarantine_dir=Path(args.quarantine_dir) / "malformed_yaml",
                )
                data["quarantine_path"] = str(result.quarantine_path)
            await mark_job(connection, int(job["id"]), status="quarantined", summary=data, error=str(exc))
            return "quarantined"
        if batch_promote.is_transient_exception(exc):
            return await mark_retry(connection, job, summary=data, error=str(exc))
        if int(job.get("attempts") or 0) >= int(job.get("max_attempts") or args.max_attempts):
            await mark_job(connection, int(job["id"]), status="failed", summary=data, error=str(exc))
            return "failed"
        return await mark_retry(connection, job, summary=data, error=str(exc))


async def run_worker(connection: Any, args: argparse.Namespace) -> WorkerSummary:
    jobs = await claim_jobs(connection, worker_id=args.worker_id, limit=args.limit)
    summary = WorkerSummary(claimed=len(jobs), errors=[])
    politeness = ProviderPoliteness(args.sleep_seconds)
    promotions_since_import = 0
    for job in jobs:
        async def callback():
            return await process_job(connection, job, args)

        status = await politeness.run(job["providers"], callback)
        if status == "promoted":
            summary.promoted += 1
            promotions_since_import += 1
        elif status == "needs_review":
            summary.needs_review += 1
        elif status == "retry":
            summary.retry += 1
        elif status == "failed":
            summary.failed += 1
        elif status == "quarantined":
            summary.quarantined += 1

        if args.import_every > 0 and promotions_since_import >= args.import_every:
            try:
                summary.imported += await import_generated_profiles(args.generated_dir, database_url=args.database_url)
            except Exception as exc:  # noqa: BLE001 - import failure should not kill claimed jobs.
                summary.errors.append(f"import_generated_profiles: {exc}")
            promotions_since_import = 0
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run queued profile repair jobs")
    parser.add_argument("--database-url")
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os_getpid()}")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--import-every", type=int, default=5)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--move", action="store_true")
    parser.add_argument("--needs-review-dir", type=Path, default=service.DEFAULT_NEEDS_REVIEW_DIR)
    parser.add_argument("--generated-dir", type=Path, default=service.DEFAULT_GENERATED_DIR)
    parser.add_argument("--review-archive-dir", type=Path, default=Path("profiles/review_archive"))
    parser.add_argument("--quarantine-dir", type=Path, default=Path("profiles/quarantined"))
    parser.add_argument("--keep-review-copy", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--roster-dir", type=Path, default=Path("profiles/rosters"))
    parser.add_argument("--notes-path", type=Path, default=service.DEFAULT_REVIEW_NOTES_PATH)
    parser.add_argument("--source-timeout-seconds", type=float, default=4.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug-dir", type=Path, default=Path("data/repair_debug"))
    parser.add_argument("--max-source-candidates", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    return parser


def os_getpid() -> int:
    import os

    return os.getpid()


async def async_main(args: argparse.Namespace) -> int:
    async with connect_database(args.database_url) as connection:
        await apply_schema(connection)
        summary = await run_worker(connection, args)
    if args.json:
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    else:
        for key, value in summary.as_dict().items():
            print(f"{key}: {value}")
    return 1 if summary.failed else 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
