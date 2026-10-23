#!/usr/bin/env python3
"""Frag-3 Part-1 live cleanup: remove the exact CSPW template
artifacts from profiles/generated/** (classification applied FRESH
at clean time):
  - weakness/any-section items whose NAME carries the template
    instruction ("Self-explanatory Feats: List all of the
    character's amazing feats..."),
  - bare "<stat> feats" label items in weaknesses,
  - stats whose text IS the WIP placeholder or the field-definition
    string (whole power_scale entry cleared),
  - disclosed extra: an attack_potency entry whose text starts
    with the template's own AP instruction line verbatim.
Prints one line per action. DB refresh is the caller's job
(import_generated_profiles).
"""
import glob
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io
from battlebot.review import auto_repair as ar

DEFN = "the distance the character's attacks/abilities can cover"
WIP = "will finish upon return"
AP_INSTRUCTION_PREFIX = (
    "the character's attack power or destructive capacity (in bold"
)

actions = []
for path in sorted(glob.glob("/app/profiles/generated/**/*.yaml", recursive=True)):
    rel = path.split("/app/")[-1]
    profile = yaml_io.load_yaml(path)
    if not isinstance(profile, dict):
        continue
    changed = False
    # --- stats ---
    ps = profile.get("power_scale") or {}
    if isinstance(ps, dict):
        for field in list(ps):
            entry = ps.get(field)
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "")
            low = text.strip().casefold()
            detail = None
            if low == WIP:
                detail = "wip_placeholder_stat"
            elif DEFN in low:
                detail = "field_definition_stat"
            elif field == "attack_potency" and low.startswith(AP_INSTRUCTION_PREFIX):
                detail = "template_instruction_stat_disclosed_extra"
            if detail:
                del ps[field]
                changed = True
                actions.append(
                    f"CLEAR-STAT {rel} [power_scale:{field}] ({detail}) "
                    f"text={text[:90]!r}"
                )
    # --- items ---
    for section in ("abilities", "weaknesses", "equipment"):
        items = profile.get(section)
        is_dict = isinstance(items, dict)
        seq = list(items.values()) if is_dict else list(items or [])
        for item in seq:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            low = name.casefold()
            reasons = ar.placeholder_item_reasons(name)
            detail = None
            if "self-explanatory feats" in low or (
                "template_instruction" in reasons and "list all of" in low
            ):
                detail = f"template_instruction_item:{reasons}"
            elif section == "weaknesses" and "feats_label" in reasons:
                detail = "feats_label"
            if not detail:
                continue
            if is_dict:
                for key in [
                    k
                    for k, v in items.items()
                    if isinstance(v, dict) and v.get("id") == item.get("id")
                ]:
                    del items[key]
            else:
                profile[section] = [
                    i
                    for i in profile[section]
                    if not (isinstance(i, dict) and i.get("id") == item.get("id"))
                ]
            changed = True
            actions.append(
                f"REMOVE {rel} [{section}] id={item.get('id')} "
                f"({detail}) name={name[:90]!r}"
            )
    if changed:
        yaml_io.write_yaml(path, profile)

for line in actions:
    print(line)
print(f"total actions: {len(actions)}")
