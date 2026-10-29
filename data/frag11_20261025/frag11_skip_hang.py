#!/usr/bin/env python3
"""Mark SpongeBob SquarePants as skipped-due-to-hang so the cohort can
proceed. Evidence: its recovery stalls indefinitely (observed in 3
separate runs, 22+ min total, process alive with ~0 CPU and 2
ESTABLISHED fetch connections returning no data). The hang is
profile-specific (run 2 hung on it as its very first profile; run 3
processed 319 other profiles without hanging). No real recovery attempt
completed, so no merge exists to quarantine -- the entry records the
hang honestly for frag-12 (which needs a fetch timeout + a diagnosis
of the SpongeBob sources)."""
import json
from pathlib import Path

progress_path = Path("/app/data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
rel = "profiles/needs_review/mixed/adult-cartoons/spongebob-squarepants.yaml"
progress[rel] = {
    "recovered_fields": [],
    "promoted": False,
    "error": "recovery_hang: fetch stalls indefinitely on SpongeBob SquarePants sources (3 runs, 22+ min, process idle with 2 ESTABLISHED conns, no data); skipped for frag-12 investigation (fetch timeout + source diagnosis needed)",
    "identity_mismatch": False,
    "skipped_hang_frag11": True,
}
progress_path.write_text(json.dumps(progress, indent=1, sort_keys=True))
print("skipped:", rel)
print("progress_keys_after:", len(progress))
print("SKIP DONE")
