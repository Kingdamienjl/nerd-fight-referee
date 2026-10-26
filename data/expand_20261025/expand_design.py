"""Part 1 design probe (READ-ONLY): populations, overlap, quarantine
coverage, universe ceiling. Runs inside referee-harvester-1 (/app).
Writes only its own report JSON under /app/data/expand_20261025/.
"""
import asyncio
import glob
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database
from battlebot.review import service

OUT = Path("/app/data/expand_20261025")
OUT.mkdir(parents=True, exist_ok=True)

report: dict = {}


def classify_entry(v):
    if not isinstance(v, dict):
        return "non_dict"
    if v.get("quarantined_frag11"):
        return "quarantined_flagged"
    if v.get("skipped"):
        return "skipped:" + str(v.get("skipped"))
    if v.get("error"):
        return "error"
    rf = v.get("recovered_fields") or []
    if rf:
        return "recovered"
    if v.get("identity_mismatch"):
        return "identity_mismatch"
    return "no_recovery"


async def main():
    # --- 1. cohort file on disk (frag-12 rebuild) + fresh in-memory rebuild
    cohort_file = json.loads(Path("/app/data/recovery_cohort.json").read_text())
    report["cohort_file_total"] = len(cohort_file)
    fresh: dict[str, list[str]] = {}
    needs_dir = service.DEFAULT_NEEDS_REVIEW_DIR
    for path in sorted(needs_dir.rglob("*.yaml")):
        try:
            with open(path) as handle:
                profile = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        if not isinstance(profile, dict):
            continue
        blockers = service.approval_blockers(profile)
        fresh[str(path)] = blockers
    # TARGET_BLOCKERS lives in recovery_run; import it without executing main
    import importlib.util
    spec = importlib.util.spec_from_file_location("recovery_run", "/app/data/recovery_run.py")
    rr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr)
    fresh_cohort = {p: b for p, b in fresh.items() if rr.TARGET_BLOCKERS & set(b)}
    report["cohort_fresh_total"] = len(fresh_cohort)
    report["cohort_in_file_not_fresh"] = sorted(set(cohort_file) - set(fresh_cohort))[:20]
    report["cohort_in_fresh_not_file"] = sorted(set(fresh_cohort) - set(cohort_file))[:20]
    report["cohort_in_file_not_fresh_count"] = len(set(cohort_file) - set(fresh_cohort))
    report["cohort_in_fresh_not_file_count"] = len(set(fresh_cohort) - set(cohort_file))
    # blocker distribution of fresh cohort
    bc = Counter()
    for b in fresh_cohort.values():
        for x in b:
            bc[x] += 1
    report["fresh_cohort_blockers"] = dict(bc.most_common())

    # --- 2. progress entries: outcome classes for cohort members
    progress = json.loads(Path("/app/data/recovery_progress.json").read_text())
    report["progress_keys"] = len(progress)
    classes = Counter()
    per_class: dict[str, list[str]] = {}
    for rel in fresh_cohort:
        c = classify_entry(progress.get(rel)) if rel in progress else "no_entry_todo"
        classes[c] += 1
        per_class.setdefault(c, []).append(rel)
    report["cohort_outcome_classes"] = dict(classes.most_common())
    report["cohort_outcome_samples"] = {k: sorted(v)[:5] for k, v in per_class.items()}
    # stale progress keys (not in fresh cohort)
    stale = [k for k in progress if k not in fresh_cohort]
    report["progress_stale_keys"] = len(stale)
    # quarantined entries (anywhere in progress)
    quar = sorted(k for k, v in progress.items()
                  if isinstance(v, dict) and v.get("quarantined_frag11"))
    report["quarantined_flagged"] = quar
    report["quarantined_in_fresh_cohort"] = [k for k in quar if k in fresh_cohort]

    # --- 3. profile files on disk by status dir
    prof_root = Path("/app/profiles")
    by_dir = Counter()
    total_yaml = 0
    if prof_root.exists():
        for p in prof_root.rglob("*.yaml"):
            total_yaml += 1
            parts = p.relative_to(prof_root).parts
            by_dir[parts[0] if parts else "?"] += 1
    report["profiles_yaml_total"] = total_yaml
    report["profiles_by_top_dir"] = dict(by_dir.most_common())
    # needs_review subdirs
    nr = prof_root / "needs_review"
    by_sub = Counter()
    if nr.exists():
        for p in nr.rglob("*.yaml"):
            parts = p.relative_to(nr).parts
            by_sub[parts[0] if parts else "?"] += 1
    report["needs_review_by_subdir"] = dict(by_sub.most_common())

    # --- 4. DB: jobs, characters, profiles
    async with connect_database() as conn:
        jobs = await conn.fetch(
            "SELECT status, count(*) AS n FROM profile_jobs GROUP BY status")
        report["jobs_by_status"] = {r["status"]: r["n"] for r in jobs}
        chars = await conn.fetchval("SELECT count(*) FROM characters")
        report["characters_total"] = chars
        cprof = await conn.fetchval("SELECT count(*) FROM character_profiles")
        report["character_profiles_total"] = cprof
        be = await conn.fetchval(
            "SELECT count(*) FROM character_profiles WHERE battle_eligible")
        report["battle_eligible_now"] = be
        nr_jobs = await conn.fetch(
            "SELECT profile_path FROM profile_jobs WHERE status='needs_review'")
        nr_paths = {r["profile_path"] for r in nr_jobs}
        report["needs_review_job_paths"] = len(nr_paths)
        report["overlap_cohort_and_jobs"] = len(set(fresh_cohort) & nr_paths)
        report["cohort_not_in_jobs"] = len(set(fresh_cohort) - nr_paths)
        report["jobs_not_in_cohort"] = len(nr_paths - set(fresh_cohort))
        # last_summary blocker keys over needs_review jobs
        rows = await conn.fetch(
            "SELECT key, count(*) AS n FROM profile_jobs, "
            "jsonb_object_keys(COALESCE(last_summary->'top_missing_fields','{}'::jsonb)) AS key "
            "WHERE status='needs_review' GROUP BY key ORDER BY n DESC")
        report["jobs_top_missing_fields"] = {r["key"]: r["n"] for r in rows}
        rows2 = await conn.fetch(
            "SELECT key, count(*) AS n FROM profile_jobs, "
            "jsonb_object_keys(COALESCE(last_summary->'failure_reasons','{}'::jsonb)) AS key "
            "WHERE status='needs_review' GROUP BY key ORDER BY n DESC")
        report["jobs_failure_reasons"] = {r["key"]: r["n"] for r in rows2}
        idr = await conn.fetchval(
            "SELECT count(*) FROM profile_jobs WHERE status='needs_review' "
            "AND (last_summary->>'identity_rejections')::int > 0")
        report["jobs_identity_rejections"] = idr
        # characters with no profile artifact on disk: compare character_id?
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='characters'")
        report["characters_columns"] = [r["column_name"] for r in cols]
        # characters with no row in character_profiles (by character_id)
        try:
            noc = await conn.fetchval(
                "SELECT count(*) FROM characters c WHERE NOT EXISTS "
                "(SELECT 1 FROM character_profiles p WHERE p.character_id = c.character_id)")
            report["characters_no_db_profile"] = noc
        except Exception as exc:  # noqa: BLE001
            report["characters_no_db_profile_error"] = str(exc)
        # jobs whose profile file no longer exists on disk
        missing = [p for p in nr_paths if not Path("/app/" + p).exists()]
        report["job_paths_missing_file"] = len(missing)
        report["job_paths_missing_file_sample"] = sorted(missing)[:10]

    # --- 5. quarantined profiles: current progress entries
    qdetail = {}
    for rel in quar:
        qdetail[rel] = progress.get(rel)
    report["quarantined_entries"] = qdetail

    # --- 6. frag-11 actuals: outcome tallies for the cohort run
    try:
        actual = json.load(open("/app/data/recovery_cohort11_actual.json"))
        report["cohort11_actual_type"] = type(actual).__name__
        if isinstance(actual, dict):
            report["cohort11_actual_keys"] = len(actual)
            oc = Counter()
            for v in actual.values():
                if isinstance(v, dict):
                    rf = v.get("recovered_fields") or []
                    if rf:
                        oc["recovered"] += 1
                    elif v.get("identity_mismatch"):
                        oc["identity_mismatch"] += 1
                    else:
                        oc["no_recovery"] += 1
                else:
                    oc["non_dict"] += 1
            report["cohort11_actual_outcomes"] = dict(oc)
    except Exception as exc:  # noqa: BLE001
        report["cohort11_actual_error"] = str(exc)

    Path("/app/data/expand_20261025/design_part1.json").write_text(
        json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str))
    print("DESIGN-PART1 DONE")


if __name__ == "__main__":
    asyncio.run(main())
