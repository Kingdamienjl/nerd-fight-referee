"""Phase 4 evaluation, part 2: join sole-cluster profiles to their jobs.

For each needs_review file, compute approval_blockers() and sole-cluster
membership (same definitions as phase4_tally.py), then look up the job
row for that profile_path and read identity_rejections from last_summary.
Reports, per cluster: sole-cluster profiles, of those how many have a
job, and of those how many have identity_rejections > 0 (i.e. would
STILL be blocked after the readiness rule cleared, because the repair
attempt ends on identity first).
Read-only (SELECTs + YAML loads).
"""
import asyncio
import json
import os
from collections import Counter
from pathlib import Path

from battlebot.common.db import connect_database
from battlebot.review import service

ROOT = Path("/app/profiles/needs_review")
OUT = Path("/app/data/phase4_20261025/blocker_join.json")

CLUSTERS = {
    "version_scope_axis": lambda b: b.startswith("unresolved_version_scope:")
    and b != "unresolved_version_scope:multiple_source_keys",
    "multiple_source_keys": lambda b: b == "unresolved_version_scope:multiple_source_keys",
    "defensive_evidence": lambda b: b == "unclassified_defensive_evidence",
}


async def main():
    async with connect_database(os.environ["DATABASE_URL"]) as conn:
        rows = await conn.fetch(
            "SELECT profile_path, last_summary FROM profile_jobs "
            "WHERE status = 'needs_review'"
        )
    jobs = {str(r["profile_path"]): (r["last_summary"] or {}) for r in rows}
    stats: dict[str, Counter] = {k: Counter() for k in CLUSTERS}
    scanned = 0
    for path in sorted(ROOT.rglob("*.yaml")):
        scanned += 1
        try:
            blockers = service.approval_blockers(service.load_yaml(path))
        except Exception:
            continue
        present = {k for k, pred in CLUSTERS.items() if any(pred(b) for b in blockers)}
        if len(present) != 1:
            continue
        k = next(iter(present))
        if len(blockers) != len([b for b in blockers if CLUSTERS[k](b)]):
            continue
        c = stats[k]
        c["sole_profiles"] += 1
        # Job rows key on the needs_review path as stored; the file path
        # under /app matches the stored relative form.
        rel = str(path.relative_to(Path("/app")))
        summary = jobs.get(rel) or jobs.get(str(path))
        if summary is None:
            c["no_job_row"] += 1
            continue
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                summary = {}
        c["with_job"] += 1
        try:
            rej = int(summary.get("identity_rejections") or 0)
        except (TypeError, ValueError):
            rej = 0
        if rej > 0:
            c["identity_blocked"] += 1
        else:
            c["identity_clean"] += 1
    result = {"scanned": scanned, "jobs_seen": len(jobs), "clusters": {k: dict(v) for k, v in stats.items()}}
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("WROTE", OUT)


asyncio.run(main())
