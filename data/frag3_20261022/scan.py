#!/usr/bin/env python3
"""Frag-3 Part-1 live cleanup scan (READ-ONLY).

Scans profiles/generated/** for the EXACT CSPW template patterns:
  STAT-CLEAN: power_scale stat text == "Will Finish Upon Return",
              or containing the field-definition range string.
  ITEM-CLEAN: item NAME containing "Self-explanatory Feats" or the
              list-all instruction; bare "<stat> feats" labels in
              weaknesses (the new screen's _feats_label_item).
Everything else the new screens would catch is reported as REVIEW
(report-only, never auto-cleaned); description-only occurrences of
the instruction text are AMBIGUOUS (reported, not touched).
"""
import glob
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

DEFN = "the distance the character's attacks/abilities can cover"
WIP = "will finish upon return"


def load(path):
    with open(path) as handle:
        return yaml.load(handle, Loader=yaml.CSafeLoader) or {}


def iter_items(prof):
    for section in ("abilities", "weaknesses", "equipment"):
        items = prof.get(section)
        if isinstance(items, dict):
            items = list(items.values())
        for i in items or []:
            if isinstance(i, dict):
                yield section, i


out = {"stat_clean": [], "item_clean": [], "review": [], "ambiguous": []}
files = sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True))
for path in files:
    rel = path.split("/app/")[-1]
    try:
        prof = load(path)
    except Exception:  # noqa: BLE001
        continue
    ps = prof.get("power_scale") or {}
    if isinstance(ps, dict):
        for field, entry in ps.items():
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "")
            low = text.strip().casefold()
            if low == WIP or DEFN in low:
                out["stat_clean"].append(
                    {"profile": rel, "field": field, "text": text[:110]}
                )
            else:
                extra = [
                    r
                    for r in ar.template_stat_reasons(text)
                    if r in ("wip_placeholder_stat", "field_definition_stat")
                ]
                if extra:
                    out["review"].append(
                        {
                            "profile": rel,
                            "kind": f"stat:{field}",
                            "reasons": extra,
                            "text": text[:110],
                        }
                    )
    for section, item in iter_items(prof):
        name = str(item.get("name") or "")
        desc = str(item.get("description") or "")
        low = name.casefold()
        reasons = ar.placeholder_item_reasons(name)
        if "self-explanatory feats" in low or (
            "template_instruction" in reasons and "list all of" in low
        ):
            out["item_clean"].append(
                {
                    "profile": rel,
                    "section": section,
                    "id": item.get("id"),
                    "name": name[:110],
                }
            )
        elif section == "weaknesses" and "feats_label" in reasons:
            out["item_clean"].append(
                {
                    "profile": rel,
                    "section": section,
                    "id": item.get("id"),
                    "name": name[:110],
                }
            )
        elif "feats_label" in reasons or "template_instruction" in reasons:
            out["review"].append(
                {
                    "profile": rel,
                    "kind": f"item:{section}",
                    "reasons": reasons,
                    "text": name[:110],
                }
            )
        elif "self-explanatory feats" in desc.casefold():
            out["ambiguous"].append(
                {"profile": rel, "section": section, "id": item.get("id")}
            )

print(json.dumps(out, indent=1))
print(
    "counts:",
    {k: len(v) for k, v in out.items()},
    "files_scanned:",
    len(files),
)
