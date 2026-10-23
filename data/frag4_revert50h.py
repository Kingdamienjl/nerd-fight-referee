#!/usr/bin/env python3
"""Frag-4 gate 50h FAIL revert.

New shape: weakness prose shards carrying an auxiliary verb or
exceeding the fragment screen's word caps --
  raven-rebirth:    'have it carry her',
                    'use it to absorb energy from something or
                     trap someone in a pocket dimension'
  raven-prime-earth:'Can be sometimes exhausted by using her'
All three are comma/verb-chain shards of one source sentence each.
Item-level removal; progress keys for both profiles removed so a
future screened run can redo them; audited-good merges kept.
"""
import json
from pathlib import Path

import yaml

REMOVALS = {
    "profiles/needs_review/comic/dc/raven-rebirth.yaml": {
        "have it carry her",
        "use it to absorb energy from something or trap someone in a pocket dimension",
    },
    "profiles/needs_review/comic/dc/raven-prime-earth.yaml": {
        "Can be sometimes exhausted by using her",
    },
}

report = {}
for rel, names in REMOVALS.items():
    path = Path(rel)
    profile = yaml.safe_load(path.read_text())
    removed, kept = [], []
    out_items = []
    for item in profile.get("weaknesses") or []:
        name = str(item.get("name") or "") if isinstance(item, dict) else ""
        if name.strip() in names:
            removed.append(name)
        else:
            out_items.append(item)
            kept.append(name[:60])
    assert len(removed) == len(names), (rel, removed)
    profile["weaknesses"] = out_items
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
Path("data/frag4_20261022/revert50h_report.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)
