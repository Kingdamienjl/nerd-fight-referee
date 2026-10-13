"""Batch auto-repair and promote needs_review profiles."""

from __future__ import annotations

import argparse
import asyncio
import json
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from battlebot.profiles import yaml_io
from battlebot.schemas.profile import CharacterProfile
from battlebot.review import auto_repair, enrich_sources, service


DEFAULT_PROVIDERS = "vsbattles,character_stats_profiles,superherodb,kaggle_superherodb"


@dataclass
class BatchSummary:
    scanned: int = 0
    repaired: int = 0
    promoted: int = 0
    provisional: int = 0
    verified: int = 0
    archived: int = 0
    still_needs_review: int = 0
    failed: int = 0
    quarantined: int = 0
    retry: int = 0
    retryable_failures: int = 0
    deterministic_failures: int = 0
    parser_crashes: int = 0
    identity_rejections: int = 0
    disagreement_warnings: int = 0
    missing_fields: Counter[str] = field(default_factory=Counter)
    failure_reasons: Counter[str] = field(default_factory=Counter)
    promoted_paths: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "repaired": self.repaired,
            "promoted": self.promoted,
            "promoted_total": self.promoted,
            "provisional": self.provisional,
            "verified": self.verified,
            "archived": self.archived,
            "still_needs_review": self.still_needs_review,
            "failed": self.failed,
            "quarantined": self.quarantined,
            "retry": self.retry,
            "retryable_failures": self.retryable_failures,
            "deterministic_failures": self.deterministic_failures,
            "parser_crashes": self.parser_crashes,
            "identity_rejections": self.identity_rejections,
            "disagreement_warnings": self.disagreement_warnings,
            "top_missing_fields": dict(self.missing_fields.most_common(10)),
            "failure_reasons": dict(self.failure_reasons.most_common(10)),
            "promoted_paths": self.promoted_paths,
            "failures": self.failures,
        }


def generated_destination(path: Path, needs_review_dir: Path, generated_dir: Path) -> Path:
    return service.destination_for(path, needs_review_dir, generated_dir)


def archive_review_copy(path: Path, needs_review_dir: Path, archive_dir: Path) -> Path:
    archive_path = archive_dir / service.relative_profile_tail(path, needs_review_dir)
    if archive_path.exists():
        stem = archive_path.stem
        suffix = archive_path.suffix
        counter = 2
        while archive_path.exists():
            archive_path = archive_path.with_name(f"{stem}-{counter}{suffix}")
            counter += 1
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    path.replace(archive_path)
    return archive_path


def generated_profile_validates(path: Path) -> bool:
    CharacterProfile.model_validate(service.load_yaml(path))
    return True


def is_transient_exception(exc: Exception) -> bool:
    text = str(exc).casefold()
    transient_markers = (
        "timeout",
        "temporarily unavailable",
        "too many requests",
        "rate limit",
        "connection",
        "network",
        "dns",
        "maxlag",
    )
    return any(marker in text for marker in transient_markers)


def malformed_quarantine_dir(args: argparse.Namespace) -> Path:
    return Path(args.quarantine_dir) / "malformed_yaml"


def is_malformed_yaml_exception(exc: Exception) -> bool:
    return yaml_io.is_yaml_parse_error(exc) or isinstance(exc, yaml_io.YAMLProfileWriteError)


def quarantine_malformed_profile(path: Path, *, exc: Exception, args: argparse.Namespace) -> yaml_io.QuarantineResult | None:
    if not path.exists():
        return None
    return yaml_io.quarantine_file(path, error=exc, quarantine_dir=malformed_quarantine_dir(args))


def record_retry_or_quarantine(
    path: Path,
    *,
    exc: Exception,
    args: argparse.Namespace,
) -> str:
    if is_malformed_yaml_exception(exc):
        quarantine_malformed_profile(path, exc=exc, args=args)
        return "quarantined"
    data = service.load_yaml(path)
    repair = data.get("repair") if isinstance(data.get("repair"), dict) else {}
    attempts = int(repair.get("attempts") or 0) + 1
    deterministic = not is_transient_exception(exc)
    status = "quarantined" if attempts >= args.max_attempts else "retry"
    repair.update(
        {
            "status": status,
            "attempts": attempts,
            "last_error": str(exc),
            "last_exception_type": type(exc).__name__,
            "deterministic_failure": deterministic,
            "last_traceback": traceback.format_exc(limit=8),
            "updated_at": service.utc_now(),
        }
    )
    data["repair"] = repair
    data["status"] = status
    data["battle_eligible"] = False
    generation = data.get("generation") if isinstance(data.get("generation"), dict) else {}
    generation["ineligible_reasons"] = sorted(
        set(list(generation.get("ineligible_reasons") or []) + [status])
    )
    data["generation"] = generation
    service.write_yaml(path, data)
    if status == "quarantined" and not args.dry_run:
        quarantine_path = args.quarantine_dir / service.relative_profile_tail(path, args.needs_review_dir)
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        path.replace(quarantine_path)
    return status


def update_attempt_stats(summary: BatchSummary, result: auto_repair.RepairResult) -> None:
    for attempt in result.source_attempts:
        if attempt.fetch_status == "error":
            summary.parser_crashes += 1
            if attempt.retryable:
                summary.retryable_failures += 1
            else:
                summary.deterministic_failures += 1
        elif attempt.fetch_status == "timeout":
            summary.retryable_failures += 1
        if attempt.fetch_status == "fetched" and attempt.promotion_allowed and not attempt.identity_match:
            summary.identity_rejections += 1
    warnings = []
    try:
        profile = service.load_yaml(result.path)
        warnings = ((profile.get("review") or {}).get("warnings") or [])
    except Exception:  # noqa: BLE001 - stats should not mask the result.
        warnings = []
    summary.disagreement_warnings += len(
        [warning for warning in warnings if str(warning).startswith("secondary_core_disagreement_warning")]
    )


async def batch_promote(args: argparse.Namespace) -> BatchSummary:
    summary = BatchSummary()
    provider_ids = auto_repair.parse_provider_ids(args.providers)
    paths = auto_repair.profile_paths(args.target, args.max_profiles)
    for path in paths:
        summary.scanned += 1
        try:
            if not args.dry_run:
                enrich_sources.enrich_path(path)
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
            summary.parser_crashes += 1
            if is_malformed_yaml_exception(exc):
                summary.deterministic_failures += 1
                summary.failures.append(f"{path}: malformed_yaml_quarantined: {exc}")
                try:
                    quarantine_malformed_profile(path, exc=exc, args=args)
                    summary.quarantined += 1
                except Exception as quarantine_exc:  # noqa: BLE001 - preserve the parse failure.
                    summary.failures.append(f"{path}: failed_to_quarantine_malformed_yaml: {quarantine_exc}")
                continue
            if is_transient_exception(exc):
                summary.retryable_failures += 1
            else:
                summary.deterministic_failures += 1
            summary.failures.append(f"{path}: {exc}")
            try:
                status = record_retry_or_quarantine(path, exc=exc, args=args)
            except Exception as record_exc:  # noqa: BLE001 - preserve the original failure too.
                summary.failures.append(f"{path}: failed_to_record_failure: {record_exc}")
                continue
            if status == "quarantined":
                summary.quarantined += 1
            elif status == "retry":
                summary.retry += 1
            continue

        if result.changed:
            summary.repaired += 1
        update_attempt_stats(summary, result)
        if result.promoted:
            generated_path = generated_destination(path, args.needs_review_dir, args.generated_dir)
            try:
                generated_profile_validates(generated_path)
            except ValidationError as exc:
                summary.failed += 1
                summary.failures.append(f"{generated_path}: generated_profile_validation_failed: {exc}")
                continue
            generated_profile = service.load_yaml(generated_path)
            if generated_profile.get("status") == "verified":
                summary.verified += 1
            else:
                summary.provisional += 1
            summary.promoted += 1
            summary.promoted_paths.append(
                str(generated_path)
            )
            if not args.dry_run and not args.keep_review_copy and path.exists():
                archive_review_copy(path, args.needs_review_dir, args.review_archive_dir)
                summary.archived += 1
            continue

        summary.still_needs_review += 1
        summary.missing_fields.update(result.unresolved_fields or ["needs_human_source_choice"])
        if result.errors:
            summary.failures.extend(f"{path}: {error}" for error in result.errors)
            summary.failure_reasons.update(error.split(":", 1)[0] for error in result.errors)
        for attempt in result.source_attempts:
            reason = attempt.extraction_failure_reason or attempt.fetch_status or attempt.note
            if reason:
                summary.failure_reasons.update([reason])
    return summary


def format_summary(summary: BatchSummary) -> str:
    data = summary.as_dict()
    lines = [
        f"scanned: {data['scanned']}",
        f"repaired: {data['repaired']}",
        f"provisional: {data['provisional']}",
        f"verified: {data['verified']}",
        f"promoted_total: {data['promoted_total']}",
        f"archived: {data['archived']}",
        f"still_needs_review: {data['still_needs_review']}",
        f"quarantined: {data['quarantined']}",
        f"retryable_failures: {data['retryable_failures']}",
        f"deterministic_failures: {data['deterministic_failures']}",
        f"parser_crashes: {data['parser_crashes']}",
        f"identity_rejections: {data['identity_rejections']}",
        f"disagreement_warnings: {data['disagreement_warnings']}",
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
    parser.add_argument("--review-archive-dir", type=Path, default=Path("profiles/review_archive"))
    parser.add_argument("--quarantine-dir", type=Path, default=Path("profiles/quarantined"))
    parser.add_argument("--keep-review-copy", action="store_true", help="Leave promoted source files in needs_review for debugging.")
    parser.add_argument("--max-attempts", type=int, default=3)
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
