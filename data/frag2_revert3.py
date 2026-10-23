#!/usr/bin/env python3
"""Part-3 gate FAIL revert (sample 50f):
- harley-quinn-post-flashpoint: revert the single bad merge
  (source character-stats-profiles-harley-quinn-post-flashpoint-dc)
  field/item-level to the pre-run snapshot; drop its added source;
  remove its recovery progress key (re-eligible).
- harley-quinn-dc-comics: remove ONLY the glued tab-key composite
  item 'Base Hax Hammer ...' from needs_review AND generated copies
  (rest of its merges audited good; progress key kept).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

DATA = Path("/app/data")
expected = json.loads((DATA / "recovery_sample50f_expected.json").read_text())
progress = json.loads((DATA / "recovery_progress.json").read_text())

REL = "profiles/needs_review/comic/dc/harley-quinn-post-flashpoint.yaml"
exp = expected[REL]
profile = yaml_io.load_yaml(REL)
profile["power_scale"] = exp.get("power_scale")
for section in ("abilities", "weaknesses", "equipment"):
    if exp.get(section) is None:
        profile.pop(section, None)
    else:
        profile[section] = exp[section]
exp_source_ids = {str(s.get("id")) for s in exp.get("sources") or []
                  if isinstance(s, dict)}
profile["sources"] = [
    s for s in profile.get("sources") or []
    if str(s.get("id")) in exp_source_ids
]
yaml_io.write_yaml(REL, profile)
removed_key = progress.pop(REL, None) is not None
tmp = DATA / "recovery_progress.json.tmp"
tmp.write_text(json.dumps(progress, indent=1, ensure_ascii=False))
tmp.replace(DATA / "recovery_progress.json")
print(f"post-flashpoint reverted; progress_key_removed={removed_key}")

HAX_PREFIX = "Base Hax Hammer"
for rel in (
    "profiles/needs_review/comic/dc/harley-quinn-dc-comics.yaml",
    "profiles/generated/comic/dc/harley-quinn-dc-comics.yaml",
):
    prof = yaml_io.load_yaml(rel)
    items = prof.get("abilities")
    is_dict = isinstance(items, dict)
    seq = list(items.values()) if is_dict else list(items or [])
    hit = [i for i in seq if isinstance(i, dict)
           and str(i.get("name") or "").startswith(HAX_PREFIX)]
    if not hit:
        print(f"HAX MISS in {rel}")
        continue
    hit_ids = {str(i.get("id")) for i in hit}
    if is_dict:
        for key in [k for k, v in items.items()
                    if isinstance(v, dict) and str(v.get("id")) in hit_ids]:
            del items[key]
    else:
        prof["abilities"] = [
            i for i in seq
            if not (isinstance(i, dict) and str(i.get("id")) in hit_ids)
        ]
    yaml_io.write_yaml(rel, prof)
    print(f"HAX removed x{len(hit)} from {rel}")
