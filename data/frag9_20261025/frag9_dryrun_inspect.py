#!/usr/bin/env python3
"""Inspect frag-9 dry-run reports: list every recovered weakness
item name per profile (the dry-run script itself cannot read them
because recovered_fields is a list, not a dict, in this report
shape)."""
import json
import sys

for name in ("venom-earth-616.yaml",
             "venom-marvel-cinematic-universe.yaml"):
    rep = json.load(
        open(f"/app/data/frag9_20261025/dryrun_{name}.report.json"))
    print("==", name, "top keys:", list(rep.keys()))
    print("  recovered_fields:", rep.get("recovered_fields"))
    for tried in rep.get("sources_tried") or []:
        print("  source:", tried.get("title") or tried.get("source_id"))
        print("    dropped_items keys:",
              list((tried.get("dropped_items") or {}).keys()))
        for field, items in (tried.get("dropped_items") or {}).items():
            for it in items or []:
                print(f"    dropped [{field}]: "
                      f"{str(it.get('item'))[:90]!r} "
                      f"reasons={it.get('reasons')}")
        rec = tried.get("recovered") or tried.get("applied") or {}
        if isinstance(rec, dict):
            for field, items in rec.items():
                if isinstance(items, list):
                    for it in items:
                        if isinstance(it, dict):
                            print(f"    recovered [{field}]: "
                                  f"{str(it.get('name'))[:90]!r}")
                        else:
                            print(f"    recovered [{field}]: "
                                  f"{str(it)[:90]!r}")
        elif rec:
            print("    recovered (non-dict):", str(rec)[:400])
    sys.stdout.flush()
