#!/usr/bin/env python3
"""Frag-11 cohort totals: processed / recovered / promoted /
identity-refused / errors, from the progress file + expected/actual
snapshots. Run-1's log was lost to the harvester container restart, so
run-level counts come from run 3's summary + the snapshots (which cover
the whole 547 todo regardless of which run/worker processed a profile)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

exp = json.loads(Path("/app/data/recovery_cohort11_expected.json").read_text())
act = json.loads(Path("/app/data/recovery_cohort11_actual.json").read_text())
todo = json.loads(Path("/app/data/recovery_cohort11_list.json").read_text())["todo"]
prog = json.loads(Path("/app/data/recovery_progress.json").read_text())

new_elig = [t for t in todo
            if not (exp[t].get("battle_eligible")) and (act[t].get("battle_eligible"))]
rec = [t for t in todo if (prog.get(t) or {}).get("recovered_fields")]
# progress entry shapes: report what keys exist on a recovered entry
sample = next(((prog.get(t) or {}) for t in rec), {})
print(json.dumps({
    "todo": len(todo),
    "with_progress_key": sum(1 for t in todo if t in prog),
    "recovered": len(rec),
    "newly_battle_eligible": len(new_elig),
    "newly_eligible_list": new_elig,
    "progress_entry_keys": sorted(sample.keys()),
}, indent=1))
# identity / error signals in progress entries, if present
idm = [t for t in todo if (prog.get(t) or {}).get("identity_mismatch")]
err = [t for t in todo if (prog.get(t) or {}).get("error") or (prog.get(t) or {}).get("errors")]
print("identity_mismatch_entries:", len(idm), idm[:10])
print("error_entries:", len(err), err[:10])
print("TOTALS DONE")
