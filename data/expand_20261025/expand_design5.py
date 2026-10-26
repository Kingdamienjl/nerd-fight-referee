"""Part 1 design probe #5 (READ-ONLY + dry-runs only).
Harvester-side confirmation (full parsers: wikitextparser + bs4 present
here, absent in workers) + the 205-clean-profiles question:
  A. Harvester dry-runs (12): the 3 quarantined in-cohort profiles
     (identity verdict under full parsers?), spongebob, the 2 other-pop
     hits, giyu, + a small other-pop sample. Diff vs on-disk per section.
  B. The 205 zero-blocker needs_review profiles: full promotion-contract
     evaluation (blockers, revision metadata, confidence, schema
     blockers, missing core fields) -- how many are actually promotable,
     and what is missing on the rest?
  C. destination_for() for non-needs_review sources (what would
     approve_profile do with request_recovery_v2 / expansion_staging /
     review_archive / quarantined / generated sources?).
  D. Worker/drain promotion path: what conditions gate worker promotion
     of a clean needs_review profile (code grep, read-only).
Runs inside referee-harvester-1 (/app). Short by design (harvester
exits on its own rotation schedule). Writes only its own report
under /app/data/expand_20261025/.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair, service

OUT = Path("/app/data/expand_20261025")
report: dict = {}

DRY12 = [
    "profiles/needs_review/mixed/the-boys/soldier-boy.yaml",
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml",
    "profiles/needs_review/recentchanges/unknown/ronova.yaml",
    "profiles/needs_review/mixed/adult-cartoons/spongebob-squarepants.yaml",
    "profiles/expansion_staging/generated/game/castlevania/trevor-belmont.yaml",
    "profiles/request_recovery/needs_review/anime/bleach/as-nodt-bleach.yaml",
    "profiles/needs_review/anime/demon-slayer/giyu-tomioka.yaml",
    "profiles/request_recovery_v2/generated/anime/bleach/szayelaporro-granz.yaml",
    "profiles/request_recovery_v2/generated/anime/demon-slayer/daki.yaml",
    "profiles/generated/anime/bleach/uryu-ishida.yaml",
    "profiles/generated/anime/chainsaw-man/quanxi.yaml",
    "profiles/quarantined/bootstrap_stubs/anime/dragon-ball/whis-classic.yaml",
]


def item_names(sec):
    if isinstance(sec, list):
        return [str((a or {}).get("name") or "") for a in sec]
    return []


def diff_profiles(old, new):
    out = {}
    for sec in ("abilities", "weaknesses"):
        o = set(item_names(old.get(sec)))
        n = item_names(new.get(sec))
        added = [x for x in n if x not in o]
        out[sec] = {"old_count": len(o), "new_count": len(n),
                    "added_count": len(added), "added_names": added[:15]}
    for key in ("tier",):
        out[key] = {"old": str(old.get(key) or "")[:80],
                    "new": str(new.get(key) or "")[:80],
                    "changed": old.get(key) != new.get(key)}
    ps_old = old.get("power_scale") or {}
    ps_new = new.get("power_scale") or {}
    ps = {}
    for axis in ("attack_potency", "durability", "speed"):
        ps[axis] = {"changed": ps_old.get(axis) != ps_new.get(axis),
                    "old": str(ps_old.get(axis) or "")[:80],
                    "new": str(ps_new.get(axis) or "")[:80]}
    out["power_scale"] = ps
    return out


async def main():
    # --- A. harvester dry-runs
    dry = {}
    for rel in DRY12:
        p = Path("/app") / rel
        if not p.exists():
            dry[rel] = {"exists": False}
            continue
        old = yaml.load(p.open(), Loader=yaml.CSafeLoader) or {}
        try:
            rep = await auto_repair.recover_profile_evidence(
                p, notes_path=service.DEFAULT_REVIEW_NOTES_PATH, dry_run=True)
        except Exception as exc:  # noqa: BLE001
            dry[rel] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        dry[rel] = {
            "blockers_before": rep.get("blockers_before"),
            "blockers_after": rep.get("blockers_after"),
            "recovered_fields": rep.get("recovered_fields"),
            "identity_mismatch": bool(rep.get("identity_mismatch")),
            "merges_count": len(rep.get("merges") or []),
            "merge_fields": [m.get("recovered_fields") for m in (rep.get("merges") or [])],
            "sources_tried": len(rep.get("sources_tried") or []),
            "diff": diff_profiles(old, rep.get("profile") or {}),
            "error": rep.get("error") or "",
        }
    report["harvester_dry12"] = dry

    # --- B. the 205 zero-blocker needs_review profiles: contract check
    nr = Path("/app/profiles/needs_review")
    clean = []
    for f in sorted(nr.rglob("*.yaml")):
        try:
            prof = yaml.load(f.open(), Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        if isinstance(prof, dict) and not service.approval_blockers(prof):
            clean.append(str(f.relative_to("/app")))
    report["zero_blocker_needs_review_total"] = len(clean)
    contract = {"pass_all": 0, "fail_reasons": {}}
    fail_examples = {}
    from collections import Counter
    fail_counter: Counter = Counter()
    for rel in clean:
        prof = yaml.load((Path("/app") / rel).open(), Loader=yaml.CSafeLoader) or {}
        reasons = []
        # revision metadata: profile carries revision info?
        rev = prof.get("revision") or prof.get("revid") or prof.get("revision_id")
        if not rev:
            reasons.append("no_revision_metadata")
        conf = prof.get("confidence")
        if conf is None:
            reasons.append("no_confidence")
        elif isinstance(conf, (int, float)) and conf < 0.55:
            reasons.append("confidence_below_0.55")
        try:
            sb = service.schema_validation_blockers(prof)
        except Exception as exc:  # noqa: BLE001
            sb = [f"schema_check_error:{type(exc).__name__}"]
        if sb:
            reasons.append("schema_blockers:" + ",".join(str(s) for s in sb[:3]))
        mc = service.missing_core_fields(prof)
        if mc:
            reasons.append("missing_core:" + ",".join(str(m) for m in mc[:5]))
        if not reasons:
            contract["pass_all"] += 1
        for r in reasons:
            fail_counter[r] += 1
            fail_examples.setdefault(r, []).append(rel)
    contract["fail_reasons"] = dict(fail_counter)
    contract["fail_examples"] = {k: v[:3] for k, v in fail_examples.items()}
    # sample detail on 3 clean profiles
    samples = {}
    for rel in clean[:3]:
        prof = yaml.load((Path("/app") / rel).open(), Loader=yaml.CSafeLoader) or {}
        samples[rel] = {
            "status": prof.get("status"),
            "profile_type": prof.get("profile_type"),
            "confidence": prof.get("confidence"),
            "revision_keys": [k for k in prof.keys() if "rev" in k.lower()],
            "top_keys": sorted(prof.keys())[:25],
        }
    contract["samples"] = samples
    report["clean_contract"] = contract

    # --- C. destination_for for non-needs_review sources
    dests = {}
    for src in [
        "profiles/needs_review/anime/bleach/as-nodt.yaml",
        "profiles/request_recovery_v2/generated/anime/bleach/as-nodt.yaml",
        "profiles/expansion_staging/generated/game/castlevania/trevor-belmont.yaml",
        "profiles/review_archive/anime/bleach/uryu-ishida.yaml",
        "profiles/quarantined/bootstrap_stubs/anime/dragon-ball/whis-classic.yaml",
        "profiles/generated/anime/bleach/uryu-ishida.yaml",
        "profiles/request_recovery/needs_review/anime/bleach/as-nodt-bleach.yaml",
    ]:
        try:
            d = service.destination_for(
                Path(src),
                Path(service.DEFAULT_NEEDS_REVIEW_DIR),
                Path(service.DEFAULT_GENERATED_DIR))
            dests[src] = str(d)
        except Exception as exc:  # noqa: BLE001
            dests[src] = f"ERROR {type(exc).__name__}: {exc}"
    report["destination_for"] = dests

    # --- D. worker promotion gating (code grep, read-only)
    import subprocess
    g = subprocess.run(
        ["grep", "-rn", "approve_profile\\|contract_ok\\|promotion_allowed",
         "/app/src/battlebot/review/queue_worker.py",
         "/app/src/battlebot/review/queue.py",
         "/app/data/recovery_run.py"],
        capture_output=True, text=True)
    report["promotion_grep"] = g.stdout.strip().splitlines()[:30]

    Path("/app/data/expand_20261025/design_part5.json").write_text(
        json.dumps(report, indent=1, default=str))
    print("DESIGN-PART5 DONE")


if __name__ == "__main__":
    asyncio.run(main())
