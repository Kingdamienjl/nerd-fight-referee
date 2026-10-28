"""Frag-13 targeted pass setup (run on the box): save the standard cohort,
write a 4-profile targeted cohort (the H-profiles that are in the cohort
and in todo), verify none of them has a progress entry (prep reset them).
"""
import json
from pathlib import Path

DATA = Path("/opt/referee/data")
cohort = json.loads((DATA / "recovery_cohort.json").read_text())
progress = json.loads((DATA / "recovery_progress.json").read_text())
targets = [
    "profiles/needs_review/comic/dc/harley-quinn-post-flashpoint.yaml",
    "profiles/needs_review/comic/dc/superman-prime-earth.yaml",
    "profiles/needs_review/recentchanges/unknown/asmoday.yaml",
    "profiles/needs_review/recentchanges/unknown/ronova.yaml",
]
t = {p: cohort[p] for p in targets if p in cohort}
print("targeted in cohort:", len(t))
in_progress = [p for p in t if p in progress]
print("in progress (should be none):", in_progress)
assert len(t) == 4, "not all 4 targeted profiles are in the cohort"
assert not in_progress, "a targeted profile still has a progress entry"
(DATA / "recovery_cohort.json").write_text(json.dumps(t, indent=1, sort_keys=True))
print("TARGETED COHORT WRITTEN")
