#!/usr/bin/env python3
"""Record durable Nerd Referee verification-funnel metrics."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def state_counts(state: dict[str, Any]) -> tuple[Counter[str], Counter[str]]:
    statuses: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    for row in state.values():
        if not isinstance(row, dict):
            continue
        statuses[str(row.get("status") or "unknown")] += 1
        for blocker in row.get("blockers") or []:
            blockers[str(blocker)] += 1
    return statuses, blockers


def generated_counts(root: Path) -> tuple[int, int, Counter[str]]:
    """Count top-level readiness fields without fully parsing large evidence blobs."""
    total = 0
    eligible = 0
    statuses: Counter[str] = Counter()
    for path in root.rglob("*.yaml"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            statuses["unreadable"] += 1
            continue
        total += 1
        status = "unknown"
        for line in text.splitlines():
            if line.startswith("battle_eligible:"):
                value = line.split(":", 1)[1].strip().casefold()
                eligible += int(value in {"true", "yes", "1"})
            elif line.startswith("status:"):
                status = line.split(":", 1)[1].strip().strip("'\"") or "unknown"
        statuses[status] += 1
    return total, eligible, statuses


async def database_counts() -> tuple[int | None, int | None]:
    try:
        from battlebot.common.db import connect_database

        async with connect_database(None) as database:
            row = await database.fetchrow(
                """
                SELECT
                    count(*)::bigint AS total,
                    count(*) FILTER (
                        WHERE COALESCE((profile_json->>'battle_eligible')::boolean, false)
                    )::bigint AS eligible
                FROM character_profiles
                """
            )
        return int(row["total"]), int(row["eligible"])
    except Exception as exc:
        print(json.dumps({"database_metrics_error": str(exc)[:300]}))
        return None, None


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-root", type=Path, default=Path("profiles/generated"))
    parser.add_argument("--needs-review-root", type=Path, default=Path("profiles/needs_review"))
    parser.add_argument("--state-root", type=Path, default=Path("backups/legacy-repair-20260922"))
    parser.add_argument("--output", type=Path, default=Path("logs/verification/progress.json"))
    parser.add_argument("--history", type=Path, default=Path("logs/verification/progress.jsonl"))
    parser.add_argument("--target", type=int, default=40_000)
    parser.add_argument("--skip-database", action="store_true")
    args = parser.parse_args()

    preview = load_json(args.state_root / "preview-state.json")
    applied = load_json(args.state_root / "apply-state.json")
    preview_statuses, preview_blockers = state_counts(preview)
    apply_statuses, apply_blockers = state_counts(applied)
    generated_total, generated_eligible, generated_statuses = generated_counts(args.generated_root)
    database_total, database_eligible = (None, None) if args.skip_database else asyncio.run(database_counts())
    needs_review_total = sum(1 for path in args.needs_review_root.rglob("*.yaml") if path.is_file())
    promoted = apply_statuses.get("promoted", 0)

    report: dict[str, Any] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "target_profiles": args.target,
        "generated_profiles": generated_total,
        "stored_battle_eligible_yaml": generated_eligible,
        "database_profiles": database_total,
        "database_battle_eligible": database_eligible,
        "remaining_to_target_by_database_eligible": (
            max(args.target - database_eligible, 0) if database_eligible is not None else None
        ),
        "source_verified_repair_promotions": promoted,
        "needs_review_files": needs_review_total,
        "preview_records": len(preview),
        "apply_records": len(applied),
        "preview_statuses": dict(preview_statuses),
        "apply_statuses": dict(apply_statuses),
        "preview_blockers": dict(preview_blockers.most_common()),
        "apply_blockers": dict(apply_blockers.most_common()),
        "generated_statuses": dict(generated_statuses.most_common()),
    }
    write_json_atomic(args.output, report)

    args.history.parent.mkdir(parents=True, exist_ok=True)
    previous_core: dict[str, Any] | None = None
    if args.history.exists():
        try:
            last = args.history.read_text(encoding="utf-8").splitlines()[-1]
            previous_core = json.loads(last)
        except (IndexError, json.JSONDecodeError, OSError):
            previous_core = None
    core_keys = (
        "generated_profiles",
        "stored_battle_eligible_yaml",
        "database_profiles",
        "database_battle_eligible",
        "source_verified_repair_promotions",
        "needs_review_files",
        "preview_statuses",
        "apply_statuses",
        "preview_blockers",
    )
    changed = previous_core is None or any(previous_core.get(key) != report.get(key) for key in core_keys)
    if changed:
        with args.history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report, sort_keys=True) + "\n")

    print(json.dumps({
        "changed": changed,
        "stored_battle_eligible_yaml": generated_eligible,
        "database_battle_eligible": database_eligible,
        "source_verified_repair_promotions": promoted,
        "needs_review_files": needs_review_total,
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
