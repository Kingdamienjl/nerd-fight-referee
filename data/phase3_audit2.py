#!/usr/bin/env python3
"""Phase 3 strict audit v2 — keyed on the real profile item shapes.

For every recovered profile in the sample-50d set:
  - power_scale: per-field recovery = before text empty, after text set.
    Check text with placeholder_item_reasons + ALL
    stat_field_rejection_reasons; cited sources via continuity_check.
  - abilities/weaknesses/equipment: items keyed by id (fallback:
    normalized name); new ids = recovered. Check name+description with
    the same screens; cited sources via continuity_check + nonfiction
    title hints.
Prints a full merge manifest and a problems list. Exit 1 if problems.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

NONFICTION_TITLE_HINTS = ("animal", "species", "genus")

expected = json.loads(Path("/app/data/recovery_sample50d_expected.json").read_text())
actual = json.loads(Path("/app/data/recovery_sample50d_actual.json").read_text())
sample = json.loads(Path("/app/data/recovery_sample50d_list.json").read_text())["sample"]
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())


def text_of(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("text") or item.get("description") or item.get("name") or "")


def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")


def source_reasons(after, item):
    reasons = []
    sources_by_id = {str(s.get("id")): s for s in after.get("sources") or []
                     if isinstance(s, dict)}
    for sid in item.get("source_ids") or []:
        src = sources_by_id.get(str(sid))
        if not src:
            continue
        title = str(src.get("title") or "")
        if not title:
            continue
        verdict = ar.continuity_check(after, page_title=title,
                                      page_url=src.get("url") or None)
        if verdict["mismatch"]:
            reasons.append(f"continuity:{title}")
        lowered = title.lower()
        if any(h in lowered for h in NONFICTION_TITLE_HINTS) and "wikia" not in lowered \
                and "fandom" not in lowered:
            reasons.append(f"nonfiction_title:{title}")
    return reasons


problems = []
audited = 0
manifest = []
for rel in sample:
    entry = progress.get(rel) or {}
    if not entry.get("recovered_fields"):
        continue
    audited += 1
    before, after = expected[rel], actual[rel]
    issues = []
    # power_scale per-field
    b_ps = before.get("power_scale") or {}
    a_ps = after.get("power_scale") or {}
    if isinstance(a_ps, dict):
        for field, a_item in a_ps.items():
            if not isinstance(a_item, dict):
                continue
            a_text = str(a_item.get("text") or "")
            b_item = b_ps.get(field) if isinstance(b_ps, dict) else None
            b_text = str((b_item or {}).get("text") or "") if isinstance(b_item, dict) else ""
            if not a_text or a_text == b_text:
                continue
            reasons = list(ar.placeholder_item_reasons(a_text))
            reasons += list(ar.stat_field_rejection_reasons(a_text))
            reasons += source_reasons(after, a_item)
            titles = []
            sb = {str(s.get("id")): s for s in after.get("sources") or [] if isinstance(s, dict)}
            for sid in a_item.get("source_ids") or []:
                if str(sid) in sb:
                    titles.append(str(sb[str(sid)].get("title")))
            manifest.append(f"{rel} [stat:{field}] {a_text[:90]} <- {titles}")
            if reasons:
                issues.append(f"stat:{field} -> {sorted(set(reasons))}")
    # list sections by item id
    for section in ("abilities", "weaknesses", "equipment"):
        b_items = before.get(section)
        a_items = after.get(section)
        if isinstance(b_items, dict):
            b_items = list(b_items.values())
        if isinstance(a_items, dict):
            a_items = list(a_items.values())
        b_keys = {item_key(i) for i in b_items or [] if isinstance(i, dict)}
        for item in a_items or []:
            if not isinstance(item, dict) or item_key(item) in b_keys:
                continue
            text = text_of(item)
            reasons = []
            if text:
                reasons += list(ar.placeholder_item_reasons(text))
                reasons += [r for r in ar.stat_field_rejection_reasons(text)
                            if r in ("page_scaffolding", "insubstantive")]
            reasons += source_reasons(after, item)
            titles = []
            sb = {str(s.get("id")): s for s in after.get("sources") or [] if isinstance(s, dict)}
            for sid in item.get("source_ids") or []:
                if str(sid) in sb:
                    titles.append(str(sb[str(sid)].get("title")))
            manifest.append(f"{rel} [{section}] {str(item.get('name'))[:70]} <- {titles}")
            if reasons:
                issues.append(f"{section}:{item_key(item)} -> {sorted(set(reasons))}")
    if issues:
        problems.append({"profile": rel, "issues": issues})

print(f"audited={audited} flagged={len(problems)}")
for line in manifest:
    print("MERGE:", line)
for p in problems:
    print("PROBLEM:", json.dumps(p, ensure_ascii=False))
sys.exit(1 if problems else 0)
