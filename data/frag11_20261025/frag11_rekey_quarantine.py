#!/usr/bin/env python3
"""Re-add progress keys for the 2 quarantined profiles (asmoday, ronova)
so the 4th cohort run does NOT re-process them (which would re-merge the
quarantined lore-fragment weakness items -- the screens do not catch that
shape yet; frag-12 must fix the screens first, then these keys come out).
The entries record the truth: weaknesses were recovered (3 good items
kept) and the bad items were reverted by the quarantine."""
import json
from pathlib import Path

progress_path = Path("/app/data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
for rel in (
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml",
    "profiles/needs_review/recentchanges/unknown/ronova.yaml",
):
    progress[rel] = {
        "recovered_fields": ["weaknesses"],
        "promoted": False,
        "error": "",
        "identity_mismatch": False,
        "quarantined_frag11": True,
        "note": "frag-11 quarantine: lore-fragment weakness items reverted; re-process in frag-12 after screen fix",
    }
progress_path.write_text(json.dumps(progress, indent=1, sort_keys=True))
print("rekeyed:", [k for k in progress if "quarantined_frag11" in str(progress[k])][:5])
print("progress_keys_after:", len(progress))
print("REKEY DONE")
