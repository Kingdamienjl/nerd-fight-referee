#!/usr/bin/env python3
"""Provenance for the flagged sample-50e merges: which process merged what,
and when were the profile files last written vs the run window."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

progress = json.loads(Path("/app/data/recovery_progress.json").read_text())
sample = json.loads(Path("/app/data/recovery_sample50e_list.json").read_text())["sample"]

import os, time
for rel in sample:
    entry = progress.get(rel) or {}
    if not entry.get("recovered_fields"):
        continue
    path = Path(rel)
    if not path.exists():
        path = Path(str(path).replace("profiles/needs_review/", "profiles/generated/"))
    mtime = time.strftime("%H:%M:%SZ", time.gmtime(os.path.getmtime(path)))
    merges = [(m.get("source_id"), m.get("fetched_title"), m.get("recovered_fields"))
              for m in entry.get("merges") or []]
    print(f"{rel}\n  mtime={mtime} merges={merges}")

# full text of the flagged items, from the actual snapshots
actual = json.loads(Path("/app/data/recovery_sample50e_actual.json").read_text())
WATCH = {
    "profiles/needs_review/comic/dc/etrigan-dc-comics.yaml": ("weaknesses", "please read"),
    "profiles/needs_review/comic/dc/doomsday-dc-comics.yaml": ("abilities", "portal-creation"),
    "profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml": ("abilities", "mind-manipulation-possesses"),
    "profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml ": ("abilities", "x"),
}
for rel, prof in actual.items():
    for section in ("abilities", "weaknesses"):
        items = prof.get(section)
        if isinstance(items, dict):
            items = list(items.values())
        for item in items or []:
            if not isinstance(item, dict):
                continue
            iid = str(item.get("id") or "")
            if any(k in iid for k in ("portal-creation-has", "mind-manipulation-possesses",
                                      "please-read", "particular-high",
                                      "and-status-effect", "spatial-manipulation-and",
                                      "absorption-by", "resistance-to-sleep")):
                print(f"ITEM {rel} [{section}] id={iid}")
                print(f"  name={item.get('name')!r}")
                print(f"  desc={str(item.get('description') or '')!r}")
                print(f"  source_ids={item.get('source_ids')}")
