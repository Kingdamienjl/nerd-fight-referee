#!/usr/bin/env python3
"""Frag-11 calibration round 3 (read-only): run the NEW frag-11 screens
over the full stored corpus and report hit counts + samples for hand
review. Runs with the frag-11 auto_repair.py deployed, so the counts
below are the NEW code's counts.

Sections:
  (A) item screens: per-reason hits for the six new/changed reasons.
  (B) stats: label_bleed_stat hits + samples.
  (C) promotion contract: how many stored needs_review profiles would
      satisfy the new promotion gate as they stand (revision metadata
      present + no approval_blockers) -- a sense of the gate's bite.
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar
from battlebot.review import service

NEW_REASONS = (
    "label_bleed_stat",
    "bare_proper_name",
    "truncated_item",
    "orphan_tail_clause",
    "glued_composite",
)
CHANGED_REASONS = ("section_header", "conjunction_orphan")


def item_texts(prof):
    out = []
    for sec in ("abilities", "weaknesses", "equipment", "resistances", "summons"):
        items = prof.get(sec)
        if isinstance(items, dict):
            items = list(items.values())
        for it in items or []:
            if isinstance(it, dict):
                out.append((sec, str(it.get("name") or ""), str(it.get("description") or "")))
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
item_total = 0
reason_hits = Counter()
reason_samples = defaultdict(list)
stat_total = 0
label_hits = 0
label_samples = []
contract_ok = 0
contract_blocked_rev = 0
contract_blocked_appr = 0
needs_review_total = 0

for path in Path("/app/profiles").rglob("*.yaml"):
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    if not isinstance(prof, dict):
        continue
    profiles += 1
    for sec, name, desc in item_texts(prof):
        if not name and not desc:
            continue
        item_total += 1
        for text in {name, desc}:
            if not text:
                continue
            reasons = ar.fragment_item_reasons(text, section=sec)
            for r in reasons:
                if r in NEW_REASONS or r in CHANGED_REASONS:
                    reason_hits[r] += 1
                    if len(reason_samples[r]) < 15:
                        reason_samples[r].append(f"[{sec}] {text[:140]}")
    for field, text in stat_texts(prof).items():
        if not text:
            continue
        stat_total += 1
        if "label_bleed_stat" in ar.boilerplate_reasons(text, scalar=True):
            label_hits += 1
            if len(label_samples) < 15:
                label_samples.append(f"[{field}] {text[:140]}")
    rel = str(path.relative_to("/app"))
    if rel.startswith("profiles/needs_review/"):
        needs_review_total += 1
        if not ar._has_revision_metadata(prof):
            contract_blocked_rev += 1
        elif service.approval_blockers(prof):
            contract_blocked_appr += 1
        else:
            contract_ok += 1

print(f"profiles={profiles} items={item_total} stats={stat_total}")
print("== (A) item screen hits (new + changed reasons) ==")
for r in list(NEW_REASONS) + list(CHANGED_REASONS):
    print(f"  {r}: {reason_hits[r]}")
    for s in reason_samples[r]:
        print(f"      - {s!r}")
print(f"== (B) label_bleed_stat: {label_hits} / {stat_total} ==")
for s in label_samples:
    print(f"      - {s!r}")
print(f"== (C) needs_review promotion-contract now: ok={contract_ok} "
      f"blocked_no_revision={contract_blocked_rev} "
      f"blocked_approval={contract_blocked_appr} "
      f"total={needs_review_total} ==")
print("CALIB3 DONE")
