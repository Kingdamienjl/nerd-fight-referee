"""Re-approve profiles that are fully clean but never got promoted.

Scans needs_review for profiles with zero approval_blockers that carry
the provisional/verified + battle_eligible stamp, and promotes them
through service.approve_profile (the real gate), then imports.
Born from Fix B: 52 profiles scoped by the version-scope rule reached
the gate clean but bounced on the version_scope schema issue (fixed in
2e08f045); this pass lands them and any other clean stragglers.
Results -> data/reapprove_clean_results.json.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import yaml

from battlebot.common.db import database_url
from battlebot.review import queue_worker, service

RESULTS_PATH = Path("data/reapprove_clean_results.json")


def main() -> int:
    needs_dir = service.DEFAULT_NEEDS_REVIEW_DIR
    generated_dir = service.DEFAULT_GENERATED_DIR
    promoted: list[str] = []
    gate_errors: list[dict] = []
    scanned = 0
    started = time.time()
    for path in sorted(needs_dir.rglob("*.yaml")):
        scanned += 1
        try:
            with open(path) as handle:
                profile = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        if not isinstance(profile, dict):
            continue
        if not profile.get("battle_eligible") or profile.get("status") not in {"provisional", "verified"}:
            continue
        if service.approval_blockers(profile):
            continue
        approval = service.approve_profile(
            path,
            needs_review_dir=needs_dir,
            generated_dir=generated_dir,
            notes_path=service.DEFAULT_REVIEW_NOTES_PATH,
            approved_by="auto_repair",
        )
        if approval.get("ok"):
            promoted.append(str(path))
        else:
            gate_errors.append({"path": str(path), "error": approval.get("error"),
                                "schema": approval.get("schema_validation_blockers")})
    imported = 0
    if promoted:
        imported = asyncio.run(
            queue_worker.import_generated_profiles(generated_dir, database_url=database_url())
        )
    summary = {"scanned": scanned, "promoted": len(promoted), "promoted_paths": promoted,
               "imported": imported, "gate_errors": gate_errors,
               "elapsed_seconds": round(time.time() - started, 1)}
    RESULTS_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in summary.items() if k != "promoted_paths"}, indent=2))
    print("promoted_paths:", promoted[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
