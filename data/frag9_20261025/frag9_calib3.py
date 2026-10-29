#!/usr/bin/env python3
"""Frag-9 final calibration: run the REAL new screens over every
stored weakness item name in /app/profiles and report:
  - relative_pronoun_opener hits (raw + distinct + per-pronoun)
  - numeric_split_fragment hits (raw + distinct + samples)
  - header_cutoff hits (raw + distinct + per-shape)
  - prose_sentence_shard delta from the or/even/like extensions
    (new conj:or / prep:like / adv:even opener counts)
  - split_listish sanity (thousands guard)
  - verbatim sanity for all frag-9 items + controls + prior-gen
    spot checks
Read-only."""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar
from battlebot.harvest.auto_profile_harvester import split_listish

profiles = 0
items = 0
rel = Counter()
rel_ex = {}
num = Counter()
num_ex = {}
hdr = Counter()
hdr_ex = {}
shard_new = Counter()
shard_new_ex = {}

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        with path.open() as handle:
            prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    weak = prof.get("weaknesses")
    if isinstance(weak, dict):
        weak = list(weak.values())
    for item in weak or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        items += 1
        reasons = ar.fragment_item_reasons(name, section="weaknesses")
        low = name.casefold().strip().lstrip("([\"'* ")
        if "relative_pronoun_opener" in reasons:
            for p in ar._REL_PRONOUNS:
                if low.startswith(p):
                    rel[p.strip()] += 1
                    rel_ex.setdefault(p.strip(), (name, str(path)))
                    break
            else:
                rel["<other>"] += 1
        if "numeric_split_fragment" in reasons:
            key = name.strip()[:40]
            num[key] += 1
            num_ex.setdefault(key, str(path))
        if "header_cutoff" in reasons:
            m = ar._HEADER_CUTOFF_RE.match(name.strip())
            rest = m.group(2).strip() if m else name
            rlow = rest.casefold()
            if any(rlow.startswith(op) for op in ar._HEADER_SUBORD_OPENERS):
                klass = "subordinate_only"
            elif rlow.startswith("the "):
                klass = "the_np_short"
            elif ar._prose_sentence_shard(rest, rlow):
                klass = "shard_rest"
            else:
                klass = "other"
            hdr[klass] += 1
            hdr_ex.setdefault(klass, (name, str(path)))
        if "prose_sentence_shard" in reasons:
            klass = None
            for op in ("or ",):
                if low.startswith(op):
                    klass = "conj:or"
            if klass is None:
                for op in ("like ",):
                    if low.startswith(op):
                        klass = "prep:like"
            if klass is None:
                for op in ("even ",):
                    if low.startswith(op):
                        klass = "adv:even"
            if klass:
                shard_new[klass] += 1
                shard_new_ex.setdefault(klass, (name, str(path)))

print(f"profiles_scanned={profiles} weakness_items={items}")
print(f"\n== RELATIVE PRONOUN OPENER (final rule): "
      f"{sum(rel.values())} raw, {len(rel)} classes")
for k, n in rel.most_common():
    print(f"   {n:4d}  {k!r}  e.g. {rel_ex[k][0][:90]!r}")
print(f"\n== NUMERIC SPLIT FRAGMENT (final rule): "
      f"{sum(num.values())} raw, {len(num)} distinct")
for k, n in num.most_common(20):
    print(f"   {n:4d}  {k!r}  e.g. {num_ex[k]}")
print(f"\n== HEADER CUTOFF (final rule): {sum(hdr.values())} raw")
for k, n in hdr.most_common():
    print(f"   {n:4d}  {k}  e.g. {hdr_ex[k][0][:100]!r}")
print(f"\n== PROSE SHARD via NEW openers (or/like/even): "
      f"{sum(shard_new.values())} raw")
for k, n in shard_new.most_common():
    print(f"   {n:4d}  {k}  e.g. {shard_new_ex[k][0][:90]!r}")

print("\n== SPLIT_LISTISH sanity ==")
print("  ", split_listish("radiation up to 4,000 hertz, fire, ice"))
print("  ", split_listish("deals 1,000,000 damage, fire"))
print("  ", split_listish("1,000, 2,000"))
print("  ", split_listish("Strength 4, Speed 5"))

print("\n== VERBATIM SANITY (real functions) ==")
verbatim = [
    ("venom rel 1", "which has causes drastic shifts in his personality."),
    ("venom rel 2",
     "which can weaken or nullify the suit's healing powers."),
    ("venom header 1", "Sonic and Heat: The Venom symbiote"),
    ("venom header 2",
     "Darkforce: As Anti-Venom is formed from the Lightforce"),
    ("venom header 3",
     "Antibody Overuse: If Anti-Venom overuses his healing powers"),
    ("venom like", "like all others of its kind"),
    ("venom num half", "000 hertz"),
    ("venom or",
     "or by anything that can pass through the symbiote in large "
     "amounts of energy."),
    ("venom even", "even in the eminence of a battle."),
    ("control: rel + comma main", "which he fears, so he avoids it"),
    ("control: rel + boundary main",
     "which broke his arm. He never recovered."),
    ("control: that + comma main",
     "that he cannot control, and it burns him"),
    ("control: or + headed", "or he can fly"),
    ("control: even without + noun", "even without her horn"),
    ("control: like + comma main", "like a human, he needs sleep"),
    ("control: 180 blind spot", "180 degree blind spot"),
    ("control: up to 1000 degrees", "up to 1000 degrees"),
    ("control: 4 minutes", "4 minutes"),
    ("control: header subject-led", "Fire: it burns him"),
    ("control: header when + comma", "Fire: When exposed, he weakens"),
    ("control: header leading verb", "Sonic: Burns on contact"),
    ("control: header long definition",
     "Flight: The ability to fly with his wings."),
    ("control: header long definition 2",
     "Ki Blast: The most basic form of energy wave."),
    ("control: header kryptonite def",
     "Kryptonite: The green mineral from his homeworld"),
    ("control: weak to sunlight", "Weakness to sunlight"),
    ("control: archangel blades", "Archangel Blades"),
    ("control: kryptonite", "Kryptonite"),
    ("control: is weak to fire", "Is weak to fire"),
    ("control: but he cannot fly", "but he cannot fly"),
    ("control: during + comma main",
     "During full moons, he loses control"),
    ("prior: darwin shard 2",
     "but will not meet his desires in many situations. For example"),
    ("prior: darwin shard 3", "during his fight with the Hulk"),
    ("prior: kraven shard", "leading to mistakes."),
    ("prior: darwin lead (accepted, NOT caught)",
     "His body will adapt to whatever means to make Darwin survive"),
    ("prior: out orbital punch", "Out Orbital Punch"),
    ("prior: carnage disclaimer",
     "any information displayed on any profile based on Death Battle "
     "are solely based on whatever is said in their videos and not my "
     "own"),
    ("prior: kraven keep",
     "His belief in his superior hunting abilities may cause him to "
     "underestimate opponents"),
]
for label, text in verbatim:
    reasons = ar.fragment_item_reasons(text, section="weaknesses")
    print(f"  {sorted(reasons)}  :: {label}")
