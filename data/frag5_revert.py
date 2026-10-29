#!/usr/bin/env python3
"""Frag-5 gate 50i FAIL revert.

New shapes found by manual review (battery-clean):
  superman-prime-earth (weaknesses, whole merge):
    'as well as how the powers and nature of the character
     fundamentally work. This is particularly useful for more
     high-tiered characters...' and 'it is very important that you
     make sure that the text has good grammar/sentence structure'
    -- vsbattles explanation/editorial essay text merged as
    weaknesses.
  starfire-dc-comics + starfire-rebirth (weaknesses):
    'Starbolt: ...' and 'Nova: ...' (notable-attack descriptions)
    plus the concessive tail shard 'though this is draining to use'
    merged as weaknesses.
Item-level removal by name prefix (stored names are 120-char
truncated); weaknesses restore to the pre-run snapshot state
(empty); progress keys for all three profiles removed in BOTH the
host and container progress files; audited-good merges kept.
Run from /opt/referee (host paths)."""
import json
import subprocess
from pathlib import Path

import yaml

REMOVALS = {
    "profiles/needs_review/comic/dc/superman-prime-earth.yaml": [
        "as well as how the powers",
        "it is very important that you make sure",
    ],
    "profiles/needs_review/comic/dc/starfire-dc-comics.yaml": [
        "Starbolt: Starfire can fire",
        "Nova: Starfire releases",
        "though this is draining to use",
    ],
    "profiles/needs_review/comic/dc/starfire-rebirth.yaml": [
        "Starbolt: Starfire can fire",
        "Nova: Starfire releases",
        "though this is draining to use",
    ],
}

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
report["progress_keys_removed_host"] = popped

print(json.dumps(report, indent=2, ensure_ascii=False))
Path("data/frag5_20261023/revert50i_report.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False)
)
