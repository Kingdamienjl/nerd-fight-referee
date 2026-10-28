#!/usr/bin/env python3
"""Strip known wiki-template fragments from each distinct H1 scalar value.
Anything left over is real content -> that value must be SKIPPED, not cleaned.
Usage: stripcheck.py <analysis.json>"""
import json
import re
import sys
import collections

m = json.load(open(sys.argv[1]))
vals = collections.Counter()
for f, v in m["files"].items():
    for it in v["items"]:
        for s in it["scalars"]:
            vals[(s["key"], re.sub(r"\s+", " ", s["value"]).strip())] += 1

FRAGS = [
    "Self-explanatory",
    "Feats: List all of the character's amazing feats.",
    "Feats: List the character's amazing feats.",
    "Strength feats, speed feats, durability feats, etc.",
    "You can judge a person's power by their feats.",
    "It is possible to add Respect Thread links to the list, as long as they follow the policies regarding the subject provided in the Editing Rules page.",
    "Notable Attacks/Techniques: A list of some abilities the character generally uses.",
    "Notable Attacks/Techniques:",
    "Note: Self-explanatory",
    "==Explanations (Optional)==",
    "== Explanations (Optional) ==",
    "This section can be used to explain the reasons for the assigned power level of a certain character more in-depth, as well as how the powers and nature of the character fundamentally work. This is particularly useful for more high-tiered characters. However, it is very important that you make sure that the text has good grammar/sentence structure, and is easy to understand.",
    "== Gallery ==",
    "==Gallery==",
    "Themes:",
    "Put other pictures of the character here.",
    "== Others ==",
    "==Others==",
    "Put some minor information about the character here.",
    "Notable Victories: Put some notable/good matches that result in the character's victory.",
    "Notable Losses: Put some notable/good matches that result in the character's loss.",
    "Inconclusive Matches: Put some notable/good matches with the results still unclear.",
    "Notable Victories:",
    "Notable Losses:",
    "Inconclusive Matches:",
    "== Categories ==",
    "==Categories==",
    'You should always add the tier for the character. These go from "Tier 11" to "Tier 1", and also include "Unknown Tier" and "Variable Tier".',
    "__FORCETOC__",
    "This profile is still under construction!",
    "==References==",
    "== References ==",
    "==Categories",
    "[[Feats]]",
    "==Explanations & Debunks==",
    "etc.",
    "etc",
]


def strip_templates(val):
    v = val
    for frag in FRAGS:
        v = v.replace(frag, " ")
    v = re.sub(r"Category:[A-Za-z0-9\- ]+", " ", v)
    v = re.sub(r"https?://\S+", " ", v)
    v = re.sub(r"\{\|.*?\|\}", " ", v, flags=re.S)
    v = re.sub(r"File:[^ |]+\|[^ |]+", " ", v)
    v = re.sub(r"[^A-Za-z0-9 ]+", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    # leftover single stray words from markup/headers are not content
    stop = {"Design", "Design Sheets", "Concept Art", "Volume", "Rimuru",
            "Character Gallery", "Page References", "Tensura Favicon",
            "Text stroke Cookie Run", "References"}
    for w in ["Design", "Character Gallery", "Page References"]:
        v = v.replace(w, " ")
    v = re.sub(r"\s+", " ", v).strip()
    return v


for (k, val), c in vals.most_common():
    rem = strip_templates(val)
    flag = "REMAINDER" if rem else "pure"
    print(f"[{k}] x{c} {flag}: {rem[:220]}")
