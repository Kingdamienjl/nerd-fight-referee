#!/usr/bin/env python3
"""Settle provenance: grodd flagged-item descriptions (full), and the
review-notes timeline for etrigan / doomsday-rebirth."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import service

actual = json.loads(Path("/app/data/recovery_sample50e_actual.json").read_text())
for rel in ("profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml",
            "profiles/needs_review/comic/dc/gorilla-grodd.yaml"):
    prof = actual[rel]
    items = prof.get("abilities")
    if isinstance(items, dict):
        items = list(items.values())
    for item in items or []:
        iid = str(item.get("id") or "")
        if any(k in iid for k in ("mind-manipulation-possesses", "absorption-by",
                                  "resistance-to-sleep")):
            desc = str(item.get("description") or "")
            print(f"ITEM {rel}\n  name={item.get('name')!r}\n  desc={desc!r}\n"
                  f"  parens desc open={desc.count('(')} close={desc.count(')')}")

# review notes timeline for the two post-run-mtime profiles
notes_path = service.DEFAULT_REVIEW_NOTES_PATH
print("notes_path:", notes_path)
base = Path(notes_path)
candidates = [base] if base.is_file() else []
if base.is_dir():
    candidates = sorted(base.rglob("*"))
else:
    # Fix C: fragment files live alongside / under a notes dir
    for cand in (base.parent / "review_notes.d",
                 base.with_suffix(""),
                 Path("/app/data")):
        if cand.is_dir():
            candidates += sorted(cand.rglob("*etrigan*")) + sorted(cand.rglob("*doomsday-rebirth*"))
import re
hits = []
for cand in candidates:
    if cand.is_file() and cand.suffix in (".yaml", ".yml", ".json", ".txt", ".md"):
        try:
            text = cand.read_text(errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r"etrigan", text):
            hits.append((str(cand), text[max(0, m.start()-200):m.start()+300].replace("\n", " ")))
print(f"note_files_scanned={len(candidates)} etrigan_hits={len(hits)}")
for path, snippet in hits[:6]:
    print("NOTE", path, "::", snippet[:420])
