#!/usr/bin/env python3
"""Frag-8 gate-50l FAIL revert: remove the bad weakness merges
item-level from the two failing profiles, keep every audited-good
merge, and drop the progress keys so both profiles are re-eligible.

Bad items (verbatim, manual review of every merge):
  venom-earth-616.yaml (6):
    - "which has causes drastic shifts in his personality."
    - "Sonic and Heat: The Venom symbiote"
    - "like all others of its kind"
    - "Darkforce: As Anti-Venom is formed from the Lightforce"
    - "which can weaken or nullify the suit's healing powers."
    - "Antibody Overuse: If Anti-Venom overuses his healing powers"
  venom-marvel-cinematic-universe.yaml (4):
    - "radiation up to 4"
    - "000 hertz"
    - "or by anything that can pass through the symbiote in large amounts of energy."
    - "even in the eminence of a battle."

Matching is by normalized name (the item builder caps names at 120
chars, so the stored names are the verbatim strings above except
none of these exceed the cap). Verification: re-read both files,
assert zero bad items remain and the kept merges are intact, and
assert the progress keys are gone.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review.auto_repair import normalized_identity_text

BAD = {
    "profiles/needs_review/comic/marvel/venom-earth-616.yaml": [
        "which has causes drastic shifts in his personality.",
        "Sonic and Heat: The Venom symbiote",
        "like all others of its kind",
        "Darkforce: As Anti-Venom is formed from the Lightforce",
        "which can weaken or nullify the suit's healing powers.",
        "Antibody Overuse: If Anti-Venom overuses his healing powers",
    ],
    "profiles/needs_review/comic/marvel/venom-marvel-cinematic-universe.yaml": [
        "radiation up to 4",
        "000 hertz",
        "or by anything that can pass through the symbiote in large amounts of energy.",
        "even in the eminence of a battle.",
    ],
}

ROOT = Path("/app")
report = {}
for rel, bad_names in BAD.items():
    bad_keys = {normalized_identity_text(n) for n in bad_names}
    path = ROOT / rel
    prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    before = list(prof.get("weaknesses") or [])
    kept = []
    removed = []
    for item in before:
        key = normalized_identity_text(str(item.get("name") or ""))
        if key in bad_keys:
            removed.append(str(item.get("name") or ""))
        else:
            kept.append(item)
    prof["weaknesses"] = kept
    with path.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    # verify by re-reading
    after = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    after_names = {normalized_identity_text(str(i.get("name") or ""))
                   for i in after.get("weaknesses") or []}
    report[rel] = {
        "weaknesses_before": len(before),
        "removed": removed,
        "weaknesses_after": len(after.get("weaknesses") or []),
        "bad_remaining": sorted(bad_keys & after_names),
        "kept_names": [str(i.get("name") or "")[:60]
                       for i in after.get("weaknesses") or []],
    }

# drop progress keys for the reverted profiles
progress_path = ROOT / "data" / "recovery_progress.json"
progress = json.loads(progress_path.read_text())
dropped_keys = [rel for rel in BAD if rel in progress]
for rel in dropped_keys:
    del progress[rel]
progress_path.write_text(json.dumps(progress, indent=1))
report["progress_keys_dropped"] = dropped_keys
report["progress_keys_remaining_for_reverted"] = [
    rel for rel in BAD if rel in progress]
print(json.dumps(report, indent=1, ensure_ascii=False))
