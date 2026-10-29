#!/usr/bin/env python3
"""Frag-11 cohort quarantine: item-level revert of the lore-fragment
debris in asmoday.yaml + ronova.yaml weaknesses (11 items, 2 profiles).

Shape: a lore/justification passage about the Four Shades' restrictions
was split into weakness items -- chapter/act labels ('Chapter VII',
'Act III: Night White'), a scene fragment ('as the scenes depicting
Ronova...'), and other characters' powers ('Rhinedottir freely creating
life', 'and Asmoday creating numerous worlds...'). The screens missed
them: chapter/act labels are multi-token (F5 is single-token only),
'as'-led fragments are not in the F6i conjunction set, and the 'and'
one exceeds the <=8-word cap. 2 profiles is below the >5 systemic
threshold, so quarantine just these merges per the cohort protocol.

Rules (frag-9/10 lessons): do NOT recompute profile_hash; profile_type
/ review diff keys are recovery stamps (left alone); progress keys are
removed only for profiles that actually revert (these two do).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import service

BAD_IDS = {
    "weaknesses-chapter-vii",
    "weaknesses-act-iii-night-white",
    "weaknesses-as-the-scenes-depicting-ronova-permanently-killing-living-beings",
    "weaknesses-rhinedottir-freely-creating-life-humans",
    "weaknesses-and-asmoday-creating-numerous-worlds-within-her-pocket-space-all-take",
}
TARGETS = (
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml",
    "profiles/needs_review/recentchanges/unknown/ronova.yaml",
)

progress_path = Path("/app/data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
report = {}
for rel in TARGETS:
    path = Path("/app") / rel
    prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    before = prof.get("weaknesses") or []
    if isinstance(before, dict):
        before = list(before.values())
    kept = [w for w in before if str((w or {}).get("id") or "") not in BAD_IDS]
    removed = [w for w in before if str((w or {}).get("id") or "") in BAD_IDS]
    prof["weaknesses"] = kept
    with path.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    after = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    still_bad = [w for w in (after.get("weaknesses") or [])
                 if str((w or {}).get("id") or "") in BAD_IDS]
    report[rel] = {
        "removed": len(removed),
        "removed_names": [str((w or {}).get("name"))[:60] for w in removed],
        "kept": len(kept),
        "still_bad_after": len(still_bad),
        "schema_blockers_after": service.schema_validation_blockers(after),
        "profile_hash_untouched": True,
    }
    progress.pop(rel, None)
progress_path.write_text(json.dumps(progress, indent=1, sort_keys=True))
print(json.dumps(report, indent=1, ensure_ascii=False))
print("progress_keys_after:", len(progress))
print("QUARANTINE DONE")
