"""Batch auto-repair and promote needs_review profiles."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from battlebot.review import auto_repair, service


DEFAULT_PROVIDERS = "vsbattles,character_stats_profiles,superherodb,kaggle_superherodb"


@dataclass
class BatchSummary:
    scanned: int = 0
    repaired: int = 0
    promoted: int = 0
    still_needs_review: int = 0
    failed: int = 0
    missing_fields: Counter[str] = field(default_factory=Counter)
    failure_reasons: Counter[str] = field(default_factory=Counter)
    promoted_paths: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "repaired": self.repaired,
            "promoted": self.promoted,
            "still_needs_review": self.still_needs_review,
            "failed": self.failed,
            "top_missing_fields": dict(self.missing_fields.most_common(10)),
            "failure_reasons": dict(self.failure_reasons.most_common(10)),
            "promoted_paths": self.promoted_paths,
            "failures": self.failures,
        }


def generated_destination(path: Path, needs_review_dir: Path, generated_dir: Path) -> Path:
    return service.destination_for(path, needs_review_dir, generated_dir)


async def batch_promote(args: argparse.Namespace) -> BatchSummary:
    summary = BatchSummary()
    provider_ids = auto_repair.parse_provider_ids(args.providers)
    paths = auto_repair.profile_paths(args.target, args.max_profiles)
    for path in paths:
        summary.scanned += 1
        try:
            result = await auto_repair.repair_profile(
                path,
                dry_run=args.dry_run,
                overwrite=args.overwrite,
                promote_if_valid=not args.dry_run,
                move=args.move,
                needs_review_dir=args.needs_review_dir,
                generated_dir=args.generated_dir,
                roster_dir=args.roster_dir,
                notes_path=args.notes_path,
                source_timeout_seconds=args.source_timeout_seconds,
                fetch_sources=not args.dry_run or args.fetch_in_dry_run,
                debug_dir=args.debug_dir,
                verbose=args.verbose,
                max_source_candidates=args.max_source_candidates,
                provider_ids=provider_ids,
            )
        except Exception as exc:  # noqa: BLE001 - batch mode must continue across bad profiles.
            summary.failed += 1
            summary.failures.append(f"{path}: {exc}")
            continue

        if result.changed:
            summary.repaired += 1
        if result.promoted:
            summary.promoted += 1
            summary.promoted_paths.append(
                str(generated_destination(path, args.needs_review_dir, args.generated_dir))
            )
            continue

        summary.still_needs_review += 1
        summary.missing_fields.update(result.unresolved_fields or ["needs_human_source_choice"])
        if result.errors:
            summary.failures.extend(f"{path}: {error}" for error in result.errors)
            summary.failure_reasons.update(error.split(":", 1)[0] for error in result.errors)
        for attempt in result.source_attempts:
            reason = attempt.extraction_failure_reason or attempt.fetch_status or attempt.status
            if reason:
                summary.failure_reasons.update([reason])
    return summary


def format_summary(summary: BatchSummary) -> str:
    data = summary.as_dict()
    lines = [
        f"scanned: {data['scanned']}",
        f"repaired: {data['repaired']}",
        f"promoted: {data['promoted']}",
        f"still_needs_review: {data['still_needs_review']}",
        f"failed: {data['failed']}",
        f"top_missing_fields: {data['top_missing_fields']}",
        f"failure_reasons: {data['failure_reasons']}",
        "promoted_paths:",
    ]
    lines.extend(f"- {path}" for path in data["promoted_paths"])
    if not data["promoted_paths"]:
        lines.append("- none")
    if data["failures"]:
        lines.append("failures:")
        lines.extend(f"- {failure}" for failure in data["failures"][:20])
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch repair and promote valid needs_review profiles")
    parser.add_argument("target", type=Path, nargs="?", default=service.DEFAULT_NEEDS_REVIEW_DIR)
    parser.add_argument("--max-profiles", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--move", action="store_true")
    parser.add_argument("--needs-review-dir", type=Path, default=service.DEFAULT_NEEDS_REVIEW_DIR)
    parser.add_argument("--generated-dir", type=Path, default=service.DEFAULT_GENERATED_DIR)
    parser.add_argument("--roster-dir", type=Path, default=Path("profiles/rosters"))
    parser.add_argument("--notes-path", type=Path, default=service.DEFAULT_REVIEW_NOTES_PATH)
    parser.add_argument("--source-timeout-seconds", type=float, default=4.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug-dir", type=Path, default=auto_repair.DEFAULT_DEBUG_DIR)
    parser.add_argument("--max-source-candidates", type=int, default=8)
    parser.add_argument("--providers", default=DEFAULT_PROVIDERS)
    parser.add_argument(
        "--fetch-in-dry-run",
        action="store_true",
        help="Attempt live source fetches during --dry-run instead of only planning attempts.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON.")
    return parser


async def async_main(args: argparse.Namespace) -> int:
    summary = await batch_promote(args)
    if args.json:
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    else:
        print(format_summary(summary))
    return 1 if summary.failed else 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
