"""Part 1 design probe #4 (READ-ONLY + dry-runs only).
Settles the design's remaining open questions:
  A. Duplicate safety, done right: diff dry-run rep["profile"] vs the
     on-disk original per section (added item names; any added name
     already present on-disk = duplicate). Sample: 10 recovered-before,
     10 no_recovery-before. Plus a hash-before/after proof that dry-run
     does not touch the file.
  B. The 3 in-cohort quarantined profiles, dry-run: do the verbatim
     uncovered items re-appear as would-be merges?
  C. Other-population yield: 4 dry-runs each from request_recovery_v2,
     generated, expansion_staging, review_archive, quarantined (sources
     present). Plus per-population sources-present fraction.
  D. The 10 error profiles from probe #1, dry-run (SpongeBob regex fix
     may unblock them).
  E. DB join: for each dir's TARGET-intersecting + zero-blocker files,
     character_profiles rows by profile_path and battle_eligible counts;
     filename-stem overlap between other dirs and needs_review.
Runs inside referee-harvester-1 (/app). Writes only its own report
under /app/data/expand_20261025/.
"""
import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.common.db import connect_database
from battlebot.review import auto_repair, service

OUT = Path("/app/data/expand_20261025")
report: dict = {}

TARGET = {
    "missing_ability", "missing_clean_linked_ability",
    "missing_attack_potency", "missing_durability", "missing_speed",
    "unlinked_stat:attack_potency", "unlinked_stat:durability",
    "unlinked_stat:speed",
}

QUAR_VERBATIM = {
    "profiles/needs_review/mixed/the-boys/soldier-boy.yaml": [
        "The Boys", "Season 1", "Episode 2", "Season 4", "Episode 8",
        '"Season Four Finale" Additionally',
    ],
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml": [
        "Chapter VII", "Act III: Night White",
        "as the scenes depicting Ronova permanently killing living beings",
        "Rhinedottir freely creating life",
        "and Asmoday creating numerous worlds within her pocket space",
    ],
    "profiles/needs_review/recentchanges/unknown/ronova.yaml": [
        "Chapter VII", "Act III: Night White",
        "as the scenes depicting Ronova permanently killing living beings",
        "Rhinedottir freely creating life",
        "and Asmoday creating numerous worlds within her pocket space",
    ],
}


def item_names(sec):
    if isinstance(sec, list):
        return [str((a or {}).get("name") or "") for a in sec]
    return []


def diff_profiles(old, new):
    """Added item names per section + scalar changes, new-vs-old."""
    out = {}
    for sec in ("abilities", "weaknesses"):
        o = set(item_names(old.get(sec)))
        n = item_names(new.get(sec))
        added = [x for x in n if x not in o]
        dups = [x for x in added if x in o]  # always [] by construction
        out[sec] = {"old_count": len(o), "new_count": len(n),
                    "added_count": len(added), "added_names": added[:15],
                    "dups_vs_old": dups}
    for key in ("tier",):
        out[key] = {"old": str(old.get(key) or "")[:80],
                    "new": str(new.get(key) or "")[:80],
                    "changed": old.get(key) != new.get(key)}
    ps_old = old.get("power_scale") or {}
    ps_new = new.get("power_scale") or {}
    ps = {}
    for axis in ("attack_potency", "durability", "speed"):
        ps[axis] = {"old": str(ps_old.get(axis) or "")[:80],
                    "new": str(ps_new.get(axis) or "")[:80],
                    "changed": ps_old.get(axis) != ps_new.get(axis)}
    out["power_scale"] = ps
    return out


async def dry_one(rel):
    p = Path("/app") / rel
    if not p.exists():
        return {"exists": False}
    before_hash = hashlib.md5(p.read_bytes()).hexdigest()
    old = yaml.load(p.open(), Loader=yaml.CSafeLoader) or {}
    try:
        rep = await auto_repair.recover_profile_evidence(
            p, notes_path=service.DEFAULT_REVIEW_NOTES_PATH, dry_run=True)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    after_hash = hashlib.md5(p.read_bytes()).hexdigest()
    new = rep.get("profile") or {}
    return {
        "file_unchanged_by_dry_run": before_hash == after_hash,
        "blockers_before": rep.get("blockers_before"),
        "blockers_after": rep.get("blockers_after"),
        "recovered_fields": rep.get("recovered_fields"),
        "identity_mismatch": bool(rep.get("identity_mismatch")),
        "merges_count": len(rep.get("merges") or []),
        "merge_fields": [m.get("recovered_fields") for m in (rep.get("merges") or [])],
        "sources_tried": len(rep.get("sources_tried") or []),
        "guard_rejections": rep.get("guard_rejections") or [],
        "diff": diff_profiles(old, new),
        "error": rep.get("error") or "",
        "wall_seconds": rep.get("wall_seconds"),
    }


async def main():
    progress = json.loads(Path("/app/data/recovery_progress.json").read_text())
    recovered_keys = sorted(k for k, v in progress.items()
                            if isinstance(v, dict) and (v.get("recovered_fields") or [])
                            and not v.get("quarantined_frag11"))
    norecov_keys = sorted(k for k, v in progress.items()
                          if isinstance(v, dict)
                          and v.get("recovered_fields") == []
                          and not v.get("identity_mismatch")
                          and not v.get("error")
                          and not v.get("quarantined_frag11"))
    error_keys = sorted(k for k, v in progress.items()
                        if isinstance(v, dict) and v.get("error"))
    report["sample_pools"] = {
        "recovered_before": len(recovered_keys),
        "no_recovery_before": len(norecov_keys),
        "error_before": len(error_keys),
    }

    # --- A. duplicate safety: 10 recovered + 10 no_recovery
    dry_a = {}
    for rel in [k for k in recovered_keys if (Path("/app") / k).exists()][:10]:
        dry_a[rel] = await dry_one(rel)
    for rel in [k for k in norecov_keys if (Path("/app") / k).exists()][:10]:
        dry_a[rel] = await dry_one(rel)
    report["dry_dup_safety"] = dry_a
    tot_added = sum(
        (r.get("diff") or {}).get("abilities", {}).get("added_count", 0)
        + (r.get("diff") or {}).get("weaknesses", {}).get("added_count", 0)
        for r in dry_a.values() if isinstance(r, dict))
    report["dup_safety_totals"] = {
        "profiles": len(dry_a),
        "total_added_items": tot_added,
        "any_file_changed": any(
            r.get("file_unchanged_by_dry_run") is False for r in dry_a.values()
            if isinstance(r, dict)),
    }

    # --- B. quarantined 3: do verbatim items re-appear?
    dry_b = {}
    for rel, verbatim in QUAR_VERBATIM.items():
        r = await dry_one(rel)
        if isinstance(r, dict) and "diff" in r:
            added_w = (r["diff"].get("weaknesses") or {}).get("added_names") or []
            added_a = (r["diff"].get("abilities") or {}).get("added_names") or []
            r["verbatim_reappearing"] = [v for v in verbatim
                                         if v in added_w or v in added_a]
            r["added_weakness_names"] = added_w
            r["added_ability_names"] = added_a
        dry_b[rel] = r
    report["dry_quarantined3"] = dry_b

    # --- C. other-population yield sample
    pops = {}
    dry_c = {}
    for d in ["request_recovery_v2", "generated", "expansion_staging",
              "review_archive", "quarantined", "request_recovery"]:
        sub = Path("/app/profiles") / d
        files = sorted(sub.rglob("*.yaml"))
        target_files = []
        with_sources = 0
        for f in files:
            try:
                prof = yaml.load(f.open(), Loader=yaml.CSafeLoader) or {}
            except Exception:
                continue
            if not isinstance(prof, dict):
                continue
            if TARGET & set(service.approval_blockers(prof)):
                target_files.append(str(f.relative_to("/app")))
                if prof.get("sources"):
                    with_sources += 1
        pops[d] = {"target_total": len(target_files),
                   "target_with_sources": with_sources}
        picks = [t for t in target_files
                 if (yaml.load((Path("/app") / t).open(), Loader=yaml.CSafeLoader) or {}).get("sources")][:4]
        pops[d]["dry_picks"] = picks
        for rel in picks:
            dry_c[rel] = await dry_one(rel)
    report["other_pops"] = pops
    report["dry_other_pops"] = dry_c

    # --- D. error profiles (all 10)
    dry_d = {}
    for rel in [k for k in error_keys if (Path("/app") / k).exists()]:
        dry_d[rel] = await dry_one(rel)
    report["dry_error_profiles"] = dry_d

    # --- E. DB join
    async with connect_database() as conn:
        sample_path = await conn.fetchval(
            "SELECT profile_path FROM character_profiles "
            "WHERE profile_path LIKE 'profiles/generated/%' LIMIT 1")
        report["db_profile_path_sample_generated"] = sample_path
        counts = {}
        for d in ["needs_review", "generated", "quarantined",
                  "review_archive", "request_recovery_v2",
                  "expansion_staging", "request_recovery"]:
            n_rows = await conn.fetchval(
                "SELECT count(*) FROM character_profiles "
                "WHERE profile_path LIKE $1", f"profiles/{d}/%")
            n_elig = await conn.fetchval(
                "SELECT count(*) FROM character_profiles "
                "WHERE profile_path LIKE $1 AND battle_eligible", f"profiles/{d}/%")
            counts[d] = {"db_rows": n_rows, "db_battle_eligible": n_elig}
        report["db_rows_by_dir"] = counts
        # zero-blocker files: DB status
        zb = {}
        for d in ["needs_review", "generated"]:
            sub = Path("/app/profiles") / d
            zpaths = []
            for f in sorted(sub.rglob("*.yaml")):
                try:
                    prof = yaml.load(f.open(), Loader=yaml.CSafeLoader) or {}
                except Exception:
                    continue
                if isinstance(prof, dict) and not service.approval_blockers(prof):
                    zpaths.append(str(f.relative_to("/app")))
            rows = await conn.fetch(
                "SELECT profile_path, battle_eligible FROM character_profiles "
                "WHERE profile_path = ANY($1)", zpaths)
            by_path = {r["profile_path"]: r["battle_eligible"] for r in rows}
            zb[d] = {"zero_blocker_files": len(zpaths),
                     "in_db": len(by_path),
                     "in_db_eligible": sum(1 for v in by_path.values() if v),
                     "in_db_not_eligible": sum(1 for v in by_path.values() if not v),
                     "not_in_db": len(zpaths) - len(by_path)}
        report["zero_blocker_db"] = zb

    # filename-stem overlap: other dirs vs needs_review
    nr_stems = {p.stem for p in (Path("/app/profiles/needs_review")).rglob("*.yaml")}
    overlap = {}
    for d in ["generated", "quarantined", "review_archive",
              "request_recovery_v2", "expansion_staging", "request_recovery"]:
        stems = {p.stem for p in (Path("/app/profiles") / d).rglob("*.yaml")}
        overlap[d] = {"stems": len(stems), "shared_with_needs_review": len(stems & nr_stems)}
    report["stem_overlap_vs_needs_review"] = overlap

    Path("/app/data/expand_20261025/design_part4.json").write_text(
        json.dumps(report, indent=1, default=str))
    print("DESIGN-PART4 DONE")


if __name__ == "__main__":
    asyncio.run(main())
