"""Phase 4 evaluation: tally approval_blockers across the needs_review cohort.

Read-only. Loads every profiles/needs_review/**/*.yaml, runs the live
service.approval_blockers(), and tallies blocker codes. Reports:
- total profiles scanned
- per-blocker counts (top 40)
- for each Oct-21 option-2 cluster (version-scope axes,
  multiple_source_keys, defensive-evidence): how many profiles carry it,
  and how many carry it as their SOLE blocker (i.e. clearable by that
  rule alone).
"""
import json
from collections import Counter
from pathlib import Path

from battlebot.review import service

ROOT = Path("/app/profiles/needs_review")
OUT = Path("/app/data/phase4_20261025/blocker_tally.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

CLUSTERS = {
    "version_scope_axis": lambda b: b.startswith("unresolved_version_scope:")
    and b != "unresolved_version_scope:multiple_source_keys",
    "multiple_source_keys": lambda b: b == "unresolved_version_scope:multiple_source_keys",
    "defensive_evidence": lambda b: b == "unclassified_defensive_evidence",
}

counts: Counter = Counter()
cluster_profiles: dict[str, int] = {k: 0 for k in CLUSTERS}
cluster_sole: dict[str, int] = {k: 0 for k in CLUSTERS}
cluster_sole_examples: dict[str, list[str]] = {k: [] for k in CLUSTERS}
scanned = 0
errors = 0

for path in sorted(ROOT.rglob("*.yaml")):
    scanned += 1
    try:
        profile = service.load_yaml(path)
        blockers = service.approval_blockers(profile)
    except Exception:
        errors += 1
        continue
    counts.update(blockers)
    present = {k for k, pred in CLUSTERS.items() if any(pred(b) for b in blockers)}
    for k in present:
        cluster_profiles[k] += 1
    if len(present) == 1 and len(blockers) == len(
        [b for b in blockers if CLUSTERS[next(iter(present))](b)]
    ):
        k = next(iter(present))
        cluster_sole[k] += 1
        if len(cluster_sole_examples[k]) < 10:
            cluster_sole_examples[k].append(str(path))

result = {
    "scanned": scanned,
    "errors": errors,
    "blocker_counts": dict(counts.most_common(40)),
    "cluster_profiles": cluster_profiles,
    "cluster_sole_blocker": cluster_sole,
    "cluster_sole_examples": cluster_sole_examples,
}
OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps(result, indent=2, sort_keys=True))
print("WROTE", OUT)
