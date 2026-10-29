#!/usr/bin/env python3
"""Inspect dry-run report dropped/boilerplate details for 3 profiles."""
import json

for name in ("blackarachnia", "shredder", "starscream"):
    d = json.load(open(
        "/opt/referee/data/frag10_20261025/dryrun_" + name + ".yaml.report.json"))
    print("=====" + name)
    for t in d.get("sources_tried") or []:
        print("  source:", t.get("title") or t.get("source_id"),
              "fetch:", t.get("fetch_status"))
        print("    scoped_fields:", t.get("scoped_fields"))
        print("    boilerplate_fields:", t.get("boilerplate_fields"))
        print("    boilerplate_reasons:", t.get("boilerplate_reasons"))
        di = (t.get("dropped_items") or {}).get("weaknesses") or []
        for item in di:
            print("    dropped weak:", str(item.get("item"))[:130],
                  "reasons:", item.get("reasons"))
