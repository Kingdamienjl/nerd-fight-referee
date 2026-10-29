#!/usr/bin/env python3
"""Frag-10 calibration round 3 (read-only): run the NEW frag-10 screens
over the full stored corpus and report hit counts + samples for hand
review. Runs inside the one-off test container with the frag-10
auto_repair.py mounted over /app/src/battlebot/review/auto_repair.py,
so the counts below are the NEW code's counts.

Sections:
  (A) weakness items: per-reason hits for the three new reasons and
      for the two changed reasons (prose_sentence_shard,
      relative_pronoun_opener), with samples.
  (B) tiers: qualifier_only_stat hits + samples.
  (C) stats: media_fragment (URL-stripped rule) hits + samples.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

NEW_REASONS = ("subordinate_opener", "lowercase_predicate", "trailing_fragment")
CHANGED_REASONS = ("prose_sentence_shard", "relative_pronoun_opener")


def weak_names(prof):
    weak = prof.get("weaknesses")
    if isinstance(weak, dict):
        weak = list(weak.values())
    out = []
    for item in weak or []:
        if isinstance(item, dict):
            out.append(str(item.get("name") or ""))
    return out


def stat_texts(prof):
    ps = prof.get("power_scale") or {}
    out = {}
    if isinstance(ps, dict):
        for field, val in ps.items():
            if isinstance(val, dict):
                out[field] = str(val.get("text") or "")
            elif isinstance(val, str):
                out[field] = val
    return out


profiles = 0
weak_items = 0
reason_hits = Counter()
reason_samples = defaultdict(list)
tier_total = 0
tier_hits = 0
tier_samples = []
stat_total = 0
media_hits = 0
media_samples = []

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    for name in weak_names(prof):
        if not name:
            continue
        weak_items += 1
        reasons = ar.fragment_item_reasons(name, section="weaknesses")
        for r in reasons:
            if r in NEW_REASONS or r in CHANGED_REASONS:
                reason_hits[r] += 1
                if len(reason_samples[r]) < 15:
                    reason_samples[r].append(name[:150])
    ps = prof.get("power_scale") or {}
    tier = ps.get("tier")
    tier_text = ""
    if isinstance(tier, dict):
        tier_text = str(tier.get("text") or "")
    elif isinstance(tier, str):
        tier_text = tier
    if tier_text:
        tier_total += 1
        if "qualifier_only_stat" in ar.boilerplate_reasons(tier_text, scalar=True):
            tier_hits += 1
            if len(tier_samples) < 20:
                tier_samples.append(tier_text[:150])
    for field, text in stat_texts(prof).items():
        if not text:
            continue
        stat_total += 1
        if "media_fragment" in ar.boilerplate_reasons(text, scalar=True):
            media_hits += 1
            if len(media_samples) < 20:
                media_samples.append(f"[{field}] {text[:150]}")

print(f"profiles={profiles} weakness_items={weak_items}")
print("== (A) weakness-item screen hits (new + changed reasons) ==")
for r in list(NEW_REASONS) + list(CHANGED_REASONS):
    print(f"  {r}: {reason_hits[r]}")
    for s in reason_samples[r]:
        print(f"      - {s!r}")
print(f"== (B) tier qualifier_only_stat: {tier_hits} / {tier_total} ==")
for s in tier_samples:
    print(f"      - {s!r}")
print(f"== (C) stat media_fragment: {media_hits} / {stat_total} ==")
for s in media_samples:
    print(f"      - {s!r}")
print("CALIB3 DONE")
