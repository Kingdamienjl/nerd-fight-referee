"""Expand gate prep (Part 2, step 1): snapshot + reset + manifest.
- Aborts if a recovery_run.py process is active anywhere in this container.
- Snapshots recovery_progress.json (before reset).
- Rebuilds the cohort from disk (recovery_run.build_cohort).
- Classifies every fresh-cohort progress entry; RESET set = every member
  whose last outcome was NOT a recovery:
    identity_mismatch, no_recovery (empty recovered_fields, no identity,
    no error), error, quarantined_flagged, skipped-only.
  KEEP = recovered_fields non-empty. Stale keys (not in fresh cohort)
  are left untouched.
- Atomically rewrites recovery_progress.json without the reset keys
  (tmp+replace, same pattern as the runner's save_progress).
- Recomputes todo = sorted(cohort) minus new progress; snapshots the
  expected (before) YAML of EVERY todo profile for the post-run audit.
- Writes expand_manifest.json with all counts + the first-50 list.
Read-only w.r.t. profiles (writes only progress/cohort/snapshot files).
"""
import asyncio
import importlib.util
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database

OUT = Path("/app/data/expand_20261025")
DATA = Path("/app/data")


def recovery_running():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        except Exception:
            continue
        if b"recovery_run.py" in cmd and int(pid) != os.getpid():
            return pid
    return None


async def main():
    running = recovery_running()
    if running:
        print(json.dumps({"abort": "recovery_run_active", "pid": running}))
        return 1

    # snapshot progress before reset
    progress_path = DATA / "recovery_progress.json"
    progress = json.loads(progress_path.read_text())
    (OUT / "recovery_progress.before_reset.json").write_text(
        json.dumps(progress, indent=1, sort_keys=True))
    n_progress_before = len(progress)

    # rebuild cohort from disk
    spec = importlib.util.spec_from_file_location(
        "recovery_run", "/app/data/recovery_run.py")
    rr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr)
    cohort = rr.build_cohort()

    # classify + reset set
    classes: Counter = Counter()
    reset_keys: list[str] = []
    for rel in cohort:
        entry = progress.get(rel)
        if entry is None:
            classes["no_entry_todo"] += 1
            continue
        if not isinstance(entry, dict):
            classes["non_dict_entry"] += 1
            continue
        if entry.get("quarantined_frag11"):
            classes["quarantined_flagged"] += 1
            reset_keys.append(rel)
        elif entry.get("identity_mismatch"):
            classes["identity_mismatch"] += 1
            reset_keys.append(rel)
        elif entry.get("error"):
            classes["error"] += 1
            reset_keys.append(rel)
        elif entry.get("recovered_fields"):
            classes["recovered_KEEP"] += 1
        elif entry.get("skipped") == "active_elsewhere" and len(entry) == 1:
            classes["skipped_only"] += 1
            reset_keys.append(rel)
        else:
            classes["no_recovery"] += 1
            reset_keys.append(rel)
    stale = [k for k in progress if k not in cohort]
    classes["stale_keys_untouched"] = len(stale)

    # atomic reset write
    progress2 = {k: v for k, v in progress.items() if k not in set(reset_keys)}
    tmp = progress_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(progress2, indent=1, sort_keys=True))
    tmp.replace(progress_path)

    # recompute todo + snapshot expected for the whole todo
    progress_now = json.loads(progress_path.read_text())
    todo = [p for p in sorted(cohort) if p not in progress_now]
    expected = {}
    for rel in todo:
        try:
            with open(Path("/app") / rel) as handle:
                expected[rel] = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"WARN skip snapshot {rel}: {exc}", file=sys.stderr)
    (OUT / "expand_expected.json").write_text(
        json.dumps(expected, indent=1, ensure_ascii=False, default=str))

    # live DB + disk numbers for the manifest
    async with connect_database() as conn:
        be = await conn.fetchval(
            "SELECT count(*) FROM character_profiles WHERE battle_eligible")
        nr_jobs = await conn.fetchval(
            "SELECT count(*) FROM profile_jobs WHERE status='needs_review'")
        prom = await conn.fetchval(
            "SELECT count(*) FROM profile_jobs WHERE status='promoted'")
    du = shutil.disk_usage("/")

    manifest = {
        "cohort_total": len(cohort),
        "progress_keys_before": n_progress_before,
        "progress_keys_after_reset": len(progress_now),
        "reset_removed": len(reset_keys),
        "reset_classes": dict(classes),
        "reset_keys": sorted(reset_keys),
        "todo_total": len(todo),
        "todo": todo,
        "first50": todo[:50],
        "snapshotted_expected": len(expected),
        "battle_eligible_before": be,
        "needs_review_jobs": nr_jobs,
        "promoted_jobs": prom,
        "disk_free_mb": du.free // (1024 * 1024),
    }
    (OUT / "expand_manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True))
    print(json.dumps({k: v for k, v in manifest.items()
                      if k not in ("reset_keys", "todo")}, indent=1, sort_keys=True))
    print("PREP DONE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
