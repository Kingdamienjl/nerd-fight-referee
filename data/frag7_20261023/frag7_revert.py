#!/usr/bin/env python3
"""Frag-7 gate 50k FAIL revert.

Manual review (the automated battery flagged only the known
120-char name-cap parenthesis class + bare-name 'insubstantive')
found battery-clean debris in weaknesses on 3 of 8 recovered
profiles:
  - carnage-marvel-cinematic-universe: a fan-page disclaimer merged
    as a weakness ('any information displayed on any profile based
    on Death Battle are solely based on whatever is said in their
    videos and not my own').
  - darwin: one prose explanation split into 4 weakness items
    ('His body will adapt to whatever means to make Darwin survive',
    'but will not meet his desires in many situations. For example',
    'during his fight with the Hulk',
    'rather than supplying a combat-related power.').
  - kraven-the-hunter-marvel-cinematic-universe: continuation shard
    'leading to mistakes.' (its lead clause, a substantive
    limitation statement, is kept as an audited-good merge).
Item-level removal; each profile's weaknesses must end at the
pre-run snapshot plus the explicitly kept audited-good items;
progress keys for the 3 profiles removed (re-eligible). All other
merges (incl. knull's promotion) kept. Run from /opt/referee."""
import json
from pathlib import Path

import yaml

# rel -> (remove-by-name-prefix list, expected remaining weakness names)
REMOVALS = {
    "profiles/needs_review/comic/marvel/carnage-marvel-cinematic-universe.yaml": (
        ["any information displayed on any profile"],
        ["Is weak to fire"],
    ),
    "profiles/needs_review/comic/marvel/darwin.yaml": (
        [
            "His body will adapt to whatever means",
            "but will not meet his desires",
            "during his fight with the Hulk",
            "rather than supplying a combat-related power",
        ],
        [],
    ),
    "profiles/needs_review/comic/marvel/kraven-the-hunter-marvel-cinematic-universe.yaml": (
        ["leading to mistakes"],
        ["His belief in his superior hunting abilities may cause him "
         "to underestimate opponents"],
    ),
}

report = {}
for rel, (prefixes, keep_names) in REMOVALS.items():
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
            kept.append(name)
    assert len(removed) == len(prefixes), (rel, removed)
    assert kept == keep_names, (rel, kept, keep_names)
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
Path("data/frag7_20261023/revert50k_report.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)
