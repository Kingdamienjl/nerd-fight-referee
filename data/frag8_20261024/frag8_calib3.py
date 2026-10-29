#!/usr/bin/env python3
"""Frag-8 final calibration: run the REAL new screens over every
stored weakness item name in /app/profiles and report:
  - page_disclaimer hits (raw + distinct + samples)
  - prose_sentence_shard hits (raw + distinct + per-opener counts)
  - residual -ing openers the shard rule does NOT catch
  - verbatim sanity for all frag-8 items + controls
Read-only."""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

profiles = 0
items = 0
disc = Counter()
disc_ex = {}
shard = Counter()
shard_ex = {}
residual_ing = Counter()
residual_ing_ex = {}

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
        if "page_disclaimer" in reasons:
            key = name.casefold()[:80]
            disc[key] += 1
            disc_ex.setdefault(key, str(path))
        if "prose_sentence_shard" in reasons:
            low = name.casefold().strip().lstrip("([\"'* ")
            klass = "trailing"
            for op in ar._SHARD_CONJ_OPENERS:
                if low.startswith(op):
                    klass = f"conj:{op.strip()}"
                    break
            else:
                for op in ar._SHARD_PREP_OPENERS:
                    if low.startswith(op):
                        klass = f"prep:{op.strip()}"
                        break
                else:
                    toks = re.findall(
                        r"[a-z]+(?:'[a-z]+)?", low)
                    if toks and toks[0].endswith("ing"):
                        klass = f"gerund:{toks[0]}"
            shard[klass] += 1
            shard_ex.setdefault(klass, (name, str(path)))
        else:
            toks = re.findall(r"[a-z]+(?:'[a-z]+)?", name.casefold())
            if toks and len(toks[0]) >= 4 and toks[0].endswith("ing") \
                    and toks[0] not in ar._SHARD_GERUND_DENY:
                residual_ing[toks[0]] += 1
                residual_ing_ex.setdefault(toks[0], (name, str(path)))

print(f"profiles_scanned={profiles} weakness_items={items}")
print(f"\n== PAGE DISCLAIMER (final rule): {sum(disc.values())} raw, "
      f"{len(disc)} distinct")
for key, n in disc.most_common(20):
    print(f"   {n:4d}  {key!r}  e.g. {disc_ex[key]}")
print(f"\n== PROSE SENTENCE SHARD (final rule): "
      f"{sum(shard.values())} raw, {len(shard)} distinct openers")
for klass, n in shard.most_common(60):
    print(f"   {n:4d}  {klass}  e.g. {shard_ex[klass][0][:80]!r}")
print(f"\n== RESIDUAL -ing openers NOT caught: "
      f"{sum(residual_ing.values())} raw, {len(residual_ing)} distinct")
for g, n in residual_ing.most_common(25):
    print(f"   {n:4d}  {g!r}  e.g. {residual_ing_ex[g][0][:80]!r}")

print("\n== VERBATIM SANITY (real functions) ==")
verbatim = [
    ("carnage disclaimer (full)",
     "any information displayed on any profile based on Death Battle "
     "are solely based on whatever is said in their videos and not my "
     "own opinion. So if a character is weaker or stronger on a profile "
     "than they actually are then it isn't my fault."),
    ("carnage disclaimer (120-cap name)",
     "any information displayed on any profile based on Death Battle "
     "are solely based on whatever is said in their videos and "),
    ("discord note",
     "Fought Bhunivelze and ultimately proved to be superior to him "
     "Note: Message me on Discord in case you want to discuss "
     "anything regarding this page (Vanta #2717)"),
    ("shovel note",
     "I just inputted everything according to the legends."),
    ("darwin shard 1 (lead clause)",
     "His body will adapt to whatever means to make Darwin survive"),
    ("darwin shard 2",
     "but will not meet his desires in many situations. For example"),
    ("darwin shard 3", "during his fight with the Hulk"),
    ("darwin shard 4",
     "rather than supplying a combat-related power."),
    ("kraven shard", "leading to mistakes."),
    ("kraven keep",
     "His belief in his superior hunting abilities may cause him to "
     "underestimate opponents"),
    ("control: however + complete clause",
     "however this can be negated by just using an even bigger shield."),
    ("control: but + subject clause",
     "but he cannot fly without his cape"),
    ("control: using + finite verb",
     "Using his powers drains him quickly"),
    ("control: without + noun", "Without his armor"),
    ("control: leaving vulnerable",
     "leaving him vulnerable to attack"),
    ("control: being powerless",
     "Being powerless without his ring"),
    ("control: weak to fire", "Is weak to fire"),
    ("control: lacking experience",
     "Lacking in battle experience on his own"),
    ("control: suffering from",
     "suffering from paranoia and extreme anger"),
    ("control: though he recovered",
     "though he eventually recovered"),
    ("control: though he wont die",
     "though he won't die because he's half-human"),
    ("control: but theyll break",
     "but they'll even break on contact"),
    ("control: meaning hell slide",
     "meaning he'll occasionally slide along the ground for a second"),
    ("control: during + comma main",
     "During full moons, he loses control"),
    ("control: darkseid cap artifact",
     "The Post-Flashpoint emanation of Darkseid was stated to be a "
     "fragment of Godhead Darkseid that resulted from his death i"),
    ("control: momo My Hero Academia",
     "requiring a certain amount of consumption of food based on how "
     "she'll use it.My Hero Academia Volume 9 Chapter 72"),
    ("control: solely based on ring",
     "His power is solely based on his ring"),
    ("known loss: due-to fragment",
     "due to not having his symbol in her armor"),
    ("known loss: getting shocked",
     "getting shocked when things don't go his way"),
    ("known loss: feet remain",
     "however his feet remain on the ground during this move"),
]
for label, text in verbatim:
    reasons = ar.fragment_item_reasons(text, section="weaknesses")
    print(f"  {sorted(reasons)}  :: {label}")
