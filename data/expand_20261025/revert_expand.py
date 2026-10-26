"""Expand mass-run quarantine revert (Part 3): remove the bad merges
item-level from the 3 affected profiles, keep every audited-good merge,
verify by re-reading, and flag the 3 profiles quarantined in the
progress file so they are NOT re-queued until frag-13 screens exist
for the two new shapes (frag-11 quarantine precedent).

Bad items (verbatim, from the mass-run manual review of every merge):
  H1 wiki-footer instructional sentence as a weakness:
    "etc. You can judge a person's power by their feats."
    (animal-man-rebirth, harley-quinn-post-flashpoint,
     superman-prime-earth)
  H2 editor note as an ability:
    "This profile is so far from done but i am sleepy (Last issue
     recorded Issue #14 of Animal Man 1988)"
    (animal-man-rebirth only)

Matching is by normalized name (the audit's item_key). profile_hash is
NOT recomputed (drain owns it). A review note records the revert on
each profile (provenance). Verification: re-read each file, assert zero
bad items remain and the kept merges are intact; recompute blockers.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review.auto_repair import normalized_identity_text
from battlebot.review import service

FOOTER = "etc. You can judge a person's power by their feats."
EDITOR_NOTE = ("This profile is so far from done but i am sleepy "
               "(Last issue recorded Issue #14 of Animal Man 1988)")

BAD = {
    "profiles/needs_review/comic/dc/animal-man-rebirth.yaml": {
        "abilities": [EDITOR_NOTE],
        "weaknesses": [FOOTER],
    },
    "profiles/needs_review/comic/dc/harley-quinn-post-flashpoint.yaml": {
        "weaknesses": [FOOTER],
    },
    "profiles/needs_review/comic/dc/superman-prime-earth.yaml": {
        "weaknesses": [FOOTER],
    },
}

SHAPES = {
    "profiles/needs_review/comic/dc/animal-man-rebirth.yaml": ["H1", "H2"],
    "profiles/needs_review/comic/dc/harley-quinn-post-flashpoint.yaml": ["H1"],
    "profiles/needs_review/comic/dc/superman-prime-earth.yaml": ["H1"],
}

ROOT = Path("/app")
report: dict = {"profiles": {}, "progress": {}}

for rel, sections in BAD.items():
    path = ROOT / rel
    prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    per_profile: dict = {}
    for section, bad_names in sections.items():
        bad_keys = {normalized_identity_text(n) for n in bad_names}
        before = list(prof.get(section) or [])
        kept = []
        removed = []
        for item in before:
            key = normalized_identity_text(str(item.get("name") or ""))
            if key in bad_keys:
                removed.append(str(item.get("name") or ""))
            else:
                kept.append(item)
        prof[section] = kept
        per_profile[section] = {
            "before": len(before),
            "removed": removed,
            "after": len(kept),
        }
    with path.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    # verify by re-reading
    after_prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    verify: dict = {}
    for section, bad_names in sections.items():
        bad_keys = {normalized_identity_text(n) for n in bad_names}
        after_names = {normalized_identity_text(str(i.get("name") or ""))
                       for i in after_prof.get(section) or []}
        verify[section] = {
            "bad_remaining": sorted(bad_keys & after_names),
            "kept_count": len(after_prof.get(section) or []),
        }
    per_profile["verify"] = verify
    per_profile["blockers_after_revert"] = service.approval_blockers(after_prof)
    per_profile["profile_hash_untouched"] = (
        after_prof.get("profile_hash") == prof.get("profile_hash"))
    service.add_review_note(
        path,
        field_path="evidence_recovery",
        issue_type="auto_repair",
        note=("Expand mass-run quarantine revert: removed bad merge(s) "
              + "; ".join(f"{s}: {', '.join(v['removed'])}"
                          for s, v in per_profile.items()
                          if isinstance(v, dict) and v.get("removed"))
              + " (shapes " + ",".join(SHAPES[rel]) + ")"),
        notes_path=service.DEFAULT_REVIEW_NOTES_PATH,
    )
    report["profiles"][rel] = per_profile

# quarantine flags in the progress file (do NOT drop the keys: without
# frag-13 screens the bad items would re-merge on re-processing).
progress_path = ROOT / "data" / "recovery_progress.json"
progress = json.loads(progress_path.read_text())
for rel in BAD:
    entry = progress.get(rel) or {}
    # Drop a recovered field only if the revert emptied that section
    # (animal-man keeps 'abilities': 15 good items remain; its
    # 'weaknesses' drops because the footer was its only weakness item).
    rec = list(entry.get("recovered_fields") or [])
    for section in BAD[rel]:
        after_count = len((yaml.load((ROOT / rel).open(), Loader=yaml.CSafeLoader) or {}).get(section) or [])
        if after_count == 0 and section in rec:
            rec.remove(section)
    entry["recovered_fields"] = rec
    entry["blockers_after"] = report["profiles"][rel]["blockers_after_revert"]
    entry["quarantined_expand"] = {
        "shapes": SHAPES[rel],
        "reverted_items": [n for s in BAD[rel].values() for n in s],
    }
    progress[rel] = entry
    report["progress"][rel] = {
        "recovered_fields_now": rec,
        "quarantined_expand": entry["quarantined_expand"],
    }
tmp = progress_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(progress, indent=1, sort_keys=True))
tmp.replace(progress_path)

# final verification: progress file re-read
progress_now = json.loads(progress_path.read_text())
report["progress_verify"] = {
    rel: bool(progress_now.get(rel, {}).get("quarantined_expand"))
    for rel in BAD
}
Path("/app/data/expand_20261025/revert_expand_report.json").write_text(
    json.dumps(report, indent=1, ensure_ascii=False, default=str))
print(json.dumps(report, indent=1, ensure_ascii=False, default=str))
print("REVERT DONE")
