"""Fix B cohort run: version-scope defaulting over needs_review.

Applies auto_repair.apply_version_scope_default to every needs_review
profile carrying an unresolved_version_scope blocker, writes back the
profiles the rule fired on (with a provenance review note each), and
promotes profiles that come fully clean through the real approval gate
(service.approve_profile, approved_by="auto_repair") -- the same clean
conditions the bulk sweep used. Local only: no network, no LLM.
Results -> data/scope_sweep_results.json.
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

RESULTS_PATH = Path("data/scope_sweep_results.json")


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

    cohort = 0
    fired = 0
    refused_profiles: list[str] = []
    axis_refusals: Counter[str] = Counter()
    vs_cleared = 0
    promoted = 0
    promoted_paths: list[str] = []
    canaries: list[dict] = []
    blocker_counts: dict[str, int] = {}
    hist_before: Counter[str] = Counter()
    hist_after: Counter[str] = Counter()
    errors: list[dict[str, str]] = []
    started = time.time()

    for path in paths:
        key = str(path)
        try:
            profile = service.load_yaml(path)
            if not isinstance(profile, dict):
                raise TypeError(f"profile is {type(profile).__name__}, not a mapping")
        except Exception as exc:
            errors.append({"path": key, "stage": "load", "error": f"{type(exc).__name__}: {exc}"})
            continue
        try:
            before = service.approval_blockers(profile)
        except Exception as exc:
            errors.append({"path": key, "stage": "blockers_before", "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not any(b.startswith("unresolved_version_scope") for b in before):
            continue
        cohort += 1
        hist_before.update(before)
        was_vs_only = all(b.startswith("unresolved_version_scope") for b in before)
        try:
            rep = auto_repair.apply_version_scope_default(profile)
        except Exception as exc:
            errors.append({"path": key, "stage": "scope", "error": f"{type(exc).__name__}: {exc}"})
            continue
        for refused_axis in rep.get("refused") or []:
            axis_refusals[refused_axis] += 1
        if rep.get("fired"):
            fired += 1
            if not args.dry_run:
                try:
                    service.write_yaml(path, profile)
                    service.add_review_note(
                        path,
                        field_path="version_scope",
                        issue_type="auto_repair",
                        note=(
                            "Version-scope defaulting: attributed multi-key stat "
                            f"text to key '{rep.get('key')}' ({rep.get('key_origin')}) "
                            f"via {auto_repair.VERSION_SCOPE_RULE_ID}; axes: "
                            + ", ".join(sorted((rep.get('axes') or {}).keys()))
                        ),
                        notes_path=notes_path,
                    )
                except Exception as exc:
                    errors.append({"path": key, "stage": "write", "error": f"{type(exc).__name__}: {exc}"})
                    continue
        else:
            refused_profiles.append(key)
        try:
            after = service.approval_blockers(profile)
        except Exception as exc:
            errors.append({"path": key, "stage": "blockers_after", "error": f"{type(exc).__name__}: {exc}"})
            continue
        hist_after.update(after)
        blocker_counts[key] = len(after)
        if not any(b.startswith("unresolved_version_scope") for b in after):
            vs_cleared += 1
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
            except Exception as exc:
                errors.append({"path": key, "stage": "approve", "error": f"{type(exc).__name__}: {exc}"})
                continue
            if approval.get("ok"):
                promoted += 1
                promoted_paths.append(key)
                if was_vs_only and len(canaries) < 5:
                    canaries.append({
                        "path": key,
                        "blockers_before": before,
                        "scoped_key": rep.get("key"),
                        "key_origin": rep.get("key_origin"),
                        "axes": rep.get("axes"),
                        "destination": approval.get("destination"),
                    })
            else:
                errors.append({
                    "path": key,
                    "stage": "approve_gate",
                    "error": json.dumps({
                        "error": approval.get("error"),
                        "approval_blockers": approval.get("approval_blockers"),
                        "schema_validation_blockers": approval.get("schema_validation_blockers"),
                    }),
                })

    imported = 0
    if promoted and not args.dry_run:
        imported = asyncio.run(
            queue_worker.import_generated_profiles(generated_dir, database_url=None)
        )
    summary = {
        "dry_run": args.dry_run,
        "cohort": cohort,
        "fired": fired,
        "refused_profiles": refused_profiles,
        "axis_refusals": dict(axis_refusals.most_common()),
        "vs_cleared": vs_cleared,
        "promoted": promoted,
        "promoted_paths": promoted_paths,
        "canaries": canaries,
        "imported": imported,
        "errors": errors,
        "blocker_histogram_before": dict(hist_before.most_common()),
        "blocker_histogram_after": dict(hist_after.most_common()),
        "blocker_counts": blocker_counts,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    if not args.dry_run:
        RESULTS_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("blocker_counts", "refused_profiles")}, indent=2, sort_keys=True))
    print("refused_profiles:", len(refused_profiles))
    return 0


if __name__ == "__main__":
    sys.exit(main())
