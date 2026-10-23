"""Bulk local sweep over profiles/needs_review.

Applies the repair path's local source-id collapse
(auto_repair._collapse_duplicate_source_ids) to every needs_review
profile, recomputes approval_blockers, and promotes profiles that come
fully clean through the real approval gate (service.approve_profile,
approved_by="auto_repair"). No network fetches, no LLM calls.

Writes a JSON summary (including per-profile blocker counts used for
queue prioritisation) to data/bulk_sweep_results.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

from battlebot.review import auto_repair, queue_worker, service

RESULTS_PATH = Path("data/bulk_sweep_results.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    needs_dir = service.DEFAULT_NEEDS_REVIEW_DIR
    generated_dir = service.DEFAULT_GENERATED_DIR
    notes_path = service.DEFAULT_REVIEW_NOTES_PATH

    paths = sorted(needs_dir.rglob("*.yaml"))
    if args.limit:
        paths = paths[: args.limit]

    hist_before: Counter[str] = Counter()
    hist_after: Counter[str] = Counter()
    blocker_counts: dict[str, int] = {}
    swept = 0
    collapsed_profiles = 0
    dropped_records = 0
    promoted = 0
    promoted_paths: list[str] = []
    errors: list[dict[str, str]] = []
    started = time.time()

    for path in paths:
        key = str(path)
        try:
            profile = service.load_yaml(path)
            if not isinstance(profile, dict):
                raise TypeError(
                    f"profile is {type(profile).__name__}, not a mapping"
                )
        except Exception as exc:  # noqa: BLE001 - per-file isolation
            errors.append(
                {"path": key, "stage": "load", "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        try:
            before = service.approval_blockers(profile)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "path": key,
                    "stage": "blockers_before",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        hist_before.update(before)
        try:
            dropped = auto_repair._collapse_duplicate_source_ids(profile)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "path": key,
                    "stage": "collapse",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        swept += 1
        if dropped:
            collapsed_profiles += 1
            dropped_records += dropped
            if not args.dry_run:
                try:
                    service.write_yaml(path, profile)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "path": key,
                            "stage": "write",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
        try:
            after = service.approval_blockers(profile)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "path": key,
                    "stage": "blockers_after",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        hist_after.update(after)
        blocker_counts[key] = len(after)
        clean = (
            not after
            and bool(profile.get("battle_eligible"))
            and profile.get("status") in {"provisional", "verified"}
        )
        if clean and not args.dry_run:
            try:
                approval = service.approve_profile(
                    path,
                    needs_review_dir=needs_dir,
                    generated_dir=generated_dir,
                    notes_path=notes_path,
                    approved_by="auto_repair",
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "path": key,
                        "stage": "approve",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            if approval.get("ok"):
                promoted += 1
                promoted_paths.append(key)
            else:
                errors.append(
                    {
                        "path": key,
                        "stage": "approve_gate",
                        "error": json.dumps(
                            {
                                "error": approval.get("error"),
                                "approval_blockers": approval.get("approval_blockers"),
                                "schema_validation_blockers": approval.get(
                                    "schema_validation_blockers"
                                ),
                            }
                        ),
                    }
                )

    imported = 0
    if promoted and not args.dry_run:
        imported = asyncio.run(
            queue_worker.import_generated_profiles(generated_dir, database_url=None)
        )

    summary = {
        "dry_run": args.dry_run,
        "scanned": len(paths),
        "swept": swept,
        "collapsed_profiles": collapsed_profiles,
        "dropped_records": dropped_records,
        "promoted": promoted,
        "promoted_paths": promoted_paths,
        "imported": imported,
        "errors": errors,
        "blocker_histogram_before": dict(hist_before.most_common()),
        "blocker_histogram_after": dict(hist_after.most_common()),
        "blocker_counts": blocker_counts,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    if not args.dry_run:
        RESULTS_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "blocker_counts"},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
