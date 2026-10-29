"""Inspect recovery_progress.json: key count, value shapes, quarantined
entries, and whether the frag-11 cohort-11 run entries are present.
Also prints the 3 todo profiles' blockers.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import service
import yaml

p = json.load(open("/app/data/recovery_progress.json"))
print(f"progress_keys={len(p)}")
print("value_types:", dict(Counter(type(v).__name__ for v in p.values())))
quar = [k for k, v in p.items()
        if isinstance(v, dict) and v.get("quarantined_frag11")]
print(f"quarantined_flagged={len(quar)}")
for k in sorted(quar):
    print(f"  Q: {k}")
cohort11 = [k for k, v in p.items()
            if isinstance(v, dict) and v.get("cohort") == "cohort11"]
print(f"cohort11_marked={len(cohort11)}")
# sample keys to see the entry shape
for k in sorted(p)[:3]:
    v = p[k]
    print(f"  sample {k}: {str(v)[:200]}")
for rel in ("profiles/needs_review/recentchanges/unknown/leafling.yaml",
            "profiles/needs_review/recentchanges/unknown/netskie.yaml",
            "profiles/needs_review/recentchanges/unknown/sheary.yaml"):
    prof = yaml.load(open("/app/" + rel), Loader=yaml.CSafeLoader) or {}
    print(f"{rel}: blockers={service.approval_blockers(prof)}")
print("PROGRESS-INSPECT DONE")
