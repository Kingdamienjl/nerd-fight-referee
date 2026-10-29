#!/usr/bin/env python3
"""Frag-6 calibration: run the three NEW screens over the stored
corpus (generated + needs_review profiles).

- editorial reasons: checked on abilities + weaknesses + equipment
  item texts (the screen applies to all item fields).
- concessive_shard / technique_in_weaknesses: weaknesses texts only
  (the screens are weaknesses-scoped by design).
Also runs the verbatim regressions + controls and reports them.
Output: /app/data/frag6_20261023/calib.json + printed summary.
"""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

spec = importlib.util.spec_from_file_location(
    "ar_frag6", "/app/data/frag6_20261023/auto_repair_new.py")
ar = importlib.util.module_from_spec(spec)
sys.modules["ar_frag6"] = ar
spec.loader.exec_module(ar)

NEW_ITEM_REASONS = {"editor_instruction", "editorial_essay"}
NEW_FRAG_REASONS = {"concessive_shard", "technique_in_weaknesses"}

VERBATIM = [
    # (text, section, expected_reason)
    ("as well as how the powers and nature of the character fundamentally work. "
     "This is particularly useful for more high-tiered characters, as their "
     "powers are often more complex", "weaknesses", "editorial_essay"),
    ("it is very important that you make sure that the text has good "
     "grammar/sentence structure", "weaknesses", "editor_instruction"),
    ("Starbolt: Starfire can fire bolts of stellar energy out of her hands",
     "weaknesses", "technique_in_weaknesses"),
    ("Nova: Starfire releases an omnidirectional energy pulse",
     "weaknesses", "technique_in_weaknesses"),
    ("though this is draining to use", "weaknesses", "concessive_shard"),
]

CONTROLS = [
    # (text, section) -- none of the NEW reasons may fire
    ("Weak to Dragon", "weaknesses"),
    ("he can simply use the opponent's abilities", "weaknesses"),
    ("Though weak to fire, he is resistant to ice", "weaknesses"),
    ("Although she is powerful, her stamina is limited", "weaknesses"),
    ("He is strong, though he tires quickly", "weaknesses"),
    ("Though draining, she can use it repeatedly", "weaknesses"),
    ("Starbolts: Drawing on stellar energy drains her reserves over time",
     "weaknesses"),
    ("Kryptonite: A radioactive mineral that weakens him and drains his strength",
     "weaknesses"),
    ("His suit makes sure the wearer survives vacuum", "weaknesses"),
    ("Makes sure his allies are safe before engaging", "weaknesses"),
    ("Vulnerable to magic and enchanted weapons", "weaknesses"),
    ("Flight", "powers_and_abilities"),
    ("Regeneration (Low-Mid)", "powers_and_abilities"),
    ("Straw Doll Technique: Resonance", "powers_and_abilities"),
    ("Resistance to Mind and Soul Hax", "powers_and_abilities"),
    ("Weakness to sunlight", "weaknesses"),
    ("as the Attack Forme lowers durability", "weaknesses"),
]

verbatim_results = []
for text, section, expected in VERBATIM:
    reasons = list(ar.placeholder_item_reasons(text))
    reasons += list(ar.fragment_item_reasons(text, section=section))
    verbatim_results.append({
        "text": text[:80], "section": section, "expected": expected,
        "ok": expected in reasons, "reasons": sorted(set(reasons)),
    })

control_results = []
for text, section in CONTROLS:
    reasons = set(ar.placeholder_item_reasons(text))
    reasons |= set(ar.fragment_item_reasons(text, section=section))
    bad = sorted(reasons & (NEW_ITEM_REASONS | NEW_FRAG_REASONS))
    control_results.append({"text": text[:80], "section": section,
                            "ok": not bad, "new_reasons": bad,
                            "all_reasons": sorted(reasons)})

SECTION_OF_PROFILE_KEY = {
    "abilities": "powers_and_abilities",
    "weaknesses": "weaknesses",
    "equipment": "standard_equipment",
}

totals = {}
hits = {"editorial": [], "concessive_shard": [], "technique_in_weaknesses": []}
profiles = 0
for base in ("/app/profiles/generated", "/app/profiles/needs_review"):
    for path in sorted(Path(base).rglob("*.yaml")):
        try:
            with path.open() as handle:
                prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        profiles += 1
        for key, section in SECTION_OF_PROFILE_KEY.items():
            items = prof.get(key)
            if isinstance(items, dict):
                items = list(items.values())
            for item in items or []:
                texts = []
                if isinstance(item, dict):
                    for fkey in ("name", "text", "description"):
                        if item.get(fkey):
                            texts.append(str(item[fkey]))
                elif isinstance(item, str):
                    texts.append(item)
                for text in texts:
                    totals[section] = totals.get(section, 0) + 1
                    ed = ar.editorial_item_reasons(text)
                    if ed:
                        hits["editorial"].append({
                            "profile": str(path), "section": section,
                            "text": text[:220], "reasons": ed})
                    if section == "weaknesses":
                        frag = ar.fragment_item_reasons(text, section="weaknesses")
                        for reason in ("concessive_shard", "technique_in_weaknesses"):
                            if reason in frag:
                                hits[reason].append({
                                    "profile": str(path), "text": text[:220],
                                    "reasons": frag})

out = {
    "profiles": profiles, "totals": totals,
    "verbatim": verbatim_results, "controls": control_results,
    "hit_counts": {k: len(v) for k, v in hits.items()},
    "hits": hits,
}
Path("/app/data/frag6_20261023/calib.json").write_text(
    json.dumps(out, indent=1, ensure_ascii=False))
print(f"profiles={profiles} totals={totals}")
print("hit_counts:", out["hit_counts"])
print("verbatim_ok:", all(v["ok"] for v in verbatim_results),
      [v for v in verbatim_results if not v["ok"]])
print("controls_ok:", all(c["ok"] for c in control_results),
      [c for c in control_results if not c["ok"]])
for kind in hits:
    for hit in hits[kind][:60]:
        print(f"HIT[{kind}]", hit["text"], "|", hit["profile"].split("/")[-1],
              "|", hit.get("section", "weaknesses"))
