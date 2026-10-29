#!/usr/bin/env python3
"""Frag-6 gate 50j FAIL revert.

New shape found by manual review (battery-clean): the-immortal and
the-immortal-image-comics merged the weakness item 'Out Orbital
Punch' -- a bare Notable Attacks/Techniques entry name (the source
page 'The Immortal (Comics)' lists Weaknesses: 'None notable' and
Notable Attacks/Techniques: 'Out Orbital Punch', 'Air Strike')
filed into weaknesses with no description. A name-only technique
entry escapes the frag-6 technique screen (which keys on attack
predicates in a label/description). Item-level removal; weaknesses
must end exactly at the pre-run snapshot state; audited-good merges
(stats on both profiles, all other profiles) kept; progress keys
for both profiles removed. Run from /opt/referee (host paths)."""
import json
from pathlib import Path

import yaml

REMOVALS = {
    "profiles/needs_review/comic/image-comics/the-immortal.yaml": [
        "Out Orbital Punch",
    ],
    "profiles/needs_review/comic/image-comics/the-immortal-image-comics.yaml": [
        "Out Orbital Punch",
    ],
}

expected = json.loads(
    Path("data/recovery_sample50j_expected.json").read_text())

report = {}
for rel, prefixes in REMOVALS.items():
    path = Path(rel)
    profile = yaml.safe_load(path.read_text())
    removed, kept = [], []
    out_items = []
    for item in profile.get("weaknesses") or []:
        name = str(item.get("name") or "") if isinstance(item, dict) else ""
        if any(name.strip().startswith(p) for p in prefixes):
            removed.append(name)
        else:
            out_items.append(item)
            kept.append(name[:60])
    assert len(removed) == len(prefixes), (rel, removed)
    profile["weaknesses"] = out_items
    assert out_items == (expected[rel].get("weaknesses") or []), (
        rel, "weaknesses do not match the pre-run snapshot")
    path.write_text(
        yaml.safe_dump(profile, sort_keys=False, allow_unicode=True, width=4096)
    )
    report[rel] = {"removed": removed, "weaknesses_left": kept}

progress_path = Path("data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
popped = {}
for rel in REMOVALS:
    popped[rel] = progress.pop(rel, None) is not None
tmp = progress_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(progress, indent=1, sort_keys=True))
tmp.replace(progress_path)
report["progress_keys_removed"] = popped

print(json.dumps(report, indent=2, ensure_ascii=False))
Path("data/frag6_20261023/revert50j_report.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)
