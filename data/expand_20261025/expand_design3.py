"""Part 1 design probe #3 (READ-ONLY + dry-runs only).
Fixes probe #2's coverage bug (fragment_item_reasons takes a STRING,
not a dict) and completes the design evidence:
  A. G-screen coverage on verbatim quarantined items, as strings.
  B. TARGET_BLOCKERS intersection per on-disk population (all 7 dirs).
  C. Dry-run deep dive: full merge dicts for giyu/gabumon + 20-profile
     sample (10 recovered-before, 10 identity-mismatch-before) with
     duplicate check against the merge's own target section.
Runs inside referee-harvester-1 (/app). Writes only its own report
under /app/data/expand_20261025/.
"""
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair, service
from battlebot.review.auto_repair import fragment_item_reasons

OUT = Path("/app/data/expand_20261025")
report: dict = {}

QUAR_ITEMS = {
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
    "profiles/needs_review/mixed/the-boys/soldier-boy.yaml": [
        "The Boys", "Season 1", "Episode 2", "Season 4", "Episode 8",
        '"Season Four Finale" Additionally',
    ],
    "profiles/needs_review/mixed/invincible/omni-man.yaml": [
        "Episode 2 - I'll Give You The Grand Tour",
        "Episode 7 - Don't Do Anything Rash",
    ],
    "profiles/needs_review/mixed/the-boys/black-noir.yaml": [
        "Black Noir has the following",
    ],
    "profiles/needs_review/mixed/the-boys/starlight.yaml": [
        "Starlight has the following",
    ],
    "profiles/needs_review/mixed/the-boys/stormfront.yaml": [
        "Stormfront has the following",
    ],
    "profiles/needs_review/mixed/steven-universe/amethyst.yaml": [
        "Amethyst's upgraded whip.",
    ],
}

TARGET = {
    "missing_ability", "missing_clean_linked_ability",
    "missing_attack_potency", "missing_durability", "missing_speed",
    "unlinked_stat:attack_potency", "unlinked_stat:durability",
    "unlinked_stat:speed",
}


async def main():
    # --- A. G-coverage, corrected: plain strings, section="weaknesses"
    cov = {}
    uncovered = []
    for rel, names in QUAR_ITEMS.items():
        rows = []
        for n in names:
            reasons = [str(r) for r in (fragment_item_reasons(n, section="weaknesses") or [])]
            rows.append({"name": n, "reasons": reasons})
            if not reasons:
                uncovered.append({"profile": rel, "name": n})
        cov[rel] = rows
    # steven-universe corpus items as strings (name, desc, name+desc)
    corpus = json.loads(Path("/app/data/frag12_20261025/corpus.json").read_text())
    su_rows = []
    su_uncovered = 0
    su_total = 0
    for prof_key, items in corpus.items():
        if "steven-universe.yaml" not in prof_key:
            continue
        for it in items:
            su_total += 1
            nm = str(it.get("name") or "")
            dc = str(it.get("desc") or "")
            r_name = [str(r) for r in (fragment_item_reasons(nm, section="weaknesses") or [])]
            r_desc = [str(r) for r in (fragment_item_reasons(dc, section="weaknesses") or [])]
            r_both = [str(r) for r in (fragment_item_reasons((nm + " " + dc).strip(), section="weaknesses") or [])]
            su_rows.append({"name": nm[:100], "reasons_name": r_name,
                           "reasons_desc": r_desc, "reasons_both": r_both})
            if not (r_name or r_desc or r_both):
                su_uncovered += 1
    report["g_coverage_corrected"] = cov
    report["g_uncovered_items"] = uncovered
    report["g_uncovered_count"] = len(uncovered)
    report["g_covered_count"] = sum(len(v) for v in cov.values()) - len(uncovered)
    report["steven_corpus_items"] = su_total
    report["steven_uncovered_all_three_forms"] = su_uncovered
    report["steven_rows"] = su_rows

    # --- B. TARGET_BLOCKERS intersection per on-disk population
    pops = {}
    prof_root = Path("/app/profiles")
    for d in ["needs_review", "generated", "quarantined", "review_archive",
              "request_recovery_v2", "expansion_staging", "request_recovery"]:
        sub = prof_root / d
        files = sorted(sub.rglob("*.yaml")) if sub.exists() else []
        n_total = len(files)
        n_target = 0
        n_zero_blockers = 0
        blocker_counter: Counter = Counter()
        target_blocker_counter: Counter = Counter()
        errors = 0
        for f in files:
            try:
                prof = yaml.load(f.open(), Loader=yaml.CSafeLoader) or {}
            except Exception:
                errors += 1
                continue
            if not isinstance(prof, dict):
                errors += 1
                continue
            bl = service.approval_blockers(prof)
            if not bl:
                n_zero_blockers += 1
            for b in bl:
                blocker_counter[b] += 1
            inter = TARGET & set(bl)
            if inter:
                n_target += 1
                for b in inter:
                    target_blocker_counter[b] += 1
        pops[d] = {
            "yaml_total": n_total,
            "target_intersect": n_target,
            "zero_blockers": n_zero_blockers,
            "load_errors": errors,
            "top_blockers": dict(blocker_counter.most_common(12)),
            "target_blockers": dict(target_blocker_counter),
        }
    report["populations_target"] = pops

    # --- C. dry-run deep dive
    dry = {}
    progress = json.loads(Path("/app/data/recovery_progress.json").read_text())
    recovered_keys = [k for k, v in progress.items()
                      if isinstance(v, dict) and (v.get("recovered_fields") or [])
                      and not v.get("quarantined_frag11")]
    mismatch_keys = [k for k, v in progress.items()
                     if isinstance(v, dict) and v.get("identity_mismatch")]
    report["progress_counts"] = {
        "total_keys": len(progress),
        "recovered_before": len(recovered_keys),
        "identity_mismatch": len(mismatch_keys),
    }

    async def dry_one(rel):
        p = Path("/app") / rel
        if not p.exists():
            return {"exists": False}
        prof = yaml.load(p.open(), Loader=yaml.CSafeLoader) or {}
        # current item names per section, for duplicate checks
        cur = {}
        for sec in ("abilities", "weaknesses"):
            cur[sec] = [str((a or {}).get("name") or "") for a in (prof.get(sec) or [])]
        cur["tier"] = str(prof.get("tier") or "")
        try:
            rep = await auto_repair.recover_profile_evidence(
                p, notes_path=service.DEFAULT_REVIEW_NOTES_PATH, dry_run=True)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}
        merges = rep.get("merges") or []
        # duplicate analysis per merge: which section does it target and
        # is its name already present there?
        dup_detail = []
        for m in merges:
            if isinstance(m, dict):
                sec = m.get("section") or m.get("field") or ""
                nm = str(m.get("name") or m.get("item") or "")
                dup_detail.append({
                    "merge_keys": sorted(m.keys()),
                    "section": sec,
                    "name": nm[:120],
                    "dup_in_section": bool(sec and nm and nm in cur.get(sec, [])),
                    "dup_in_abilities": bool(nm and nm in cur.get("abilities", [])),
                    "dup_in_weaknesses": bool(nm and nm in cur.get("weaknesses", [])),
                })
            else:
                dup_detail.append({"merge_raw": str(m)[:200]})
        return {
            "blockers_before": rep.get("blockers_before"),
            "recovered_fields": rep.get("recovered_fields"),
            "identity_mismatch": bool(rep.get("identity_mismatch")),
            "merges_count": len(merges),
            "merges_full": merges,
            "dup_detail": dup_detail,
            "error": rep.get("error") or "",
        }

    # the two probe-#2 ambiguous cases, full merges
    for rel in ("profiles/needs_review/anime/demon-slayer/giyu-tomioka.yaml",
                "profiles/needs_review/anime/digimon/gabumon.yaml"):
        dry[rel] = await dry_one(rel)
    # 10 recovered-before + 10 identity-mismatch-before (sorted, skip
    # the two already done; only existing needs_review files)
    rec_picks = [k for k in sorted(recovered_keys)
                 if k not in dry and (Path("/app") / k).exists()][:10]
    mis_picks = [k for k in sorted(mismatch_keys)
                 if k not in dry and (Path("/app") / k).exists()][:10]
    report["dry_sample_picks"] = {"recovered_before": rec_picks,
                                  "identity_mismatch_before": mis_picks}
    for rel in rec_picks:
        dry[rel] = await dry_one(rel)
    for rel in mis_picks:
        dry[rel] = await dry_one(rel)
    report["dry_run_deep"] = dry

    Path("/app/data/expand_20261025/design_part3.json").write_text(
        json.dumps(report, indent=1, default=str))
    print("DESIGN-PART3 DONE")
    print(json.dumps({
        "g_uncovered": report["g_uncovered_count"],
        "g_covered": report["g_covered_count"],
        "steven_total": su_total,
        "steven_uncovered": su_uncovered,
        "pops_target": {k: v["target_intersect"] for k, v in pops.items()},
    }, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
