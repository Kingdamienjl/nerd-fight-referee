#!/usr/bin/env python3
"""Summarize frag-10 dry-run round-2 JSONs (runs on the box)."""
import glob
import json

for f in sorted(glob.glob("/opt/referee/data/frag10_20261025/dryrun_*.json")):
    if ".report." in f:
        continue
    d = json.load(open(f))
    name = f.split("dryrun_")[1][:-5]
    print(name + ": live_mut=" + str(d["live_mutated"])
          + " synth_mut=" + str(d["synth_mutated_by_dryrun"])
          + " bad_weak=" + str(d["bad_weak_merged"])
          + " bad_tier=" + str(d["bad_tier_merged"])
          + " tier_flag=" + str(d["tier_flagged_qualifier_only"])
          + " tier_missing=" + str(d["tier_missing_ratings"])
          + " bad_range=" + str(d["bad_range_files_merged"])
          + " err=" + str(d["errors"])
          + " ident=" + str(d["identity_mismatch"]))
    print("   recovered=" + str(d["recovered_fields"]))
    print("   tier=" + repr(d["recovered_tier"]))
    print("   range=" + repr(d["recovered_range"][:120]))
    print("   weak=" + str(d["recovered_weakness_names"]))
    print("   weak_dropped_reasons=" + str(d.get("bad_weak_dropped_reasons")))
    print("   tier_drop=" + str(d.get("tier_drop_reasons"))
          + " range_drop=" + str(d.get("range_drop_reasons")))
