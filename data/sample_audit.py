#!/usr/bin/env python3
"""Independent audit of a recovery-run merge set against the gate bar.

Reads the progress file + the expected (pre-run) and actual (post-run)
profile snapshots, reports every recovered profile whose new evidence-shape
is suspicious: foreign-franchise text, continuity-mismatched cited pages,
boilerplate/scaffolding in list items OR scalars, infobox-header tier stats.
Usage: python sample_audit.py <progress.json> <expected.json> <actual.json>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")
from battlebot.review import auto_repair as ar


def _text(value):
    return str(value or "").strip()

NONFICTION_TITLE_HINTS = ("animal", "species", "genus")

progress = json.loads(Path(sys.argv[1]).read_text())
expected = json.loads(Path(sys.argv[2]).read_text())
actual = json.loads(Path(sys.argv[3]).read_text())

problems = []
audited = 0
for profile_id, entry in sorted(progress.get("recovered", {}).items()):
    before = expected.get(profile_id)
    after = actual.get(profile_id)
    if before is None or after is None:
        continue
    audited += 1
    issues = []
    before_keys = set()
    for section in ("power_scale", "abilities", "weaknesses", "equipment"):
        items = before.get(section)
        if isinstance(items, dict):
            items = list(items.values())
        for item in items or []:
            if isinstance(item, dict):
                before_keys.add((section, ar.normalized_identity_text(item.get("label") or item.get("key") or "")))
    sources_by_id = {_text(s.get("id")): s for s in after.get("sources") or []
                     if isinstance(s, dict)}
    for section in ("power_scale", "abilities", "weaknesses", "equipment"):
        items = after.get(section)
        if isinstance(items, dict):
            items = list(items.values())
        for item in items or []:
            if not isinstance(item, dict):
                continue
            key = (section, ar.normalized_identity_text(item.get("label") or item.get("key") or ""))
            if key in before_keys:
                continue
            text = _text(item.get("text"))
            reasons = ar.placeholder_item_reasons(text) if text else []
            if not reasons and text:
                scalar_reasons = [r for r in ar.stat_field_rejection_reasons(text)
                                  if r in ("page_scaffolding", "insubstantive")]
                reasons = scalar_reasons
            for sid in item.get("source_ids") or []:
                src = sources_by_id.get(_text(sid))
                if not src:
                    continue
                title = _text(src.get("title"))
                if not title:
                    continue
                verdict = ar.continuity_check(after, page_title=title,
                                               page_url=src.get("url") or None)
                if verdict["mismatch"]:
                    reasons.append(f"continuity:{title}")
                lowered = title.lower()
                if any(hint in lowered for hint in NONFICTION_TITLE_HINTS) and \
                        "wikia" not in lowered and "fandom" not in lowered:
                    reasons.append(f"nonfiction_title:{title}")
            if reasons:
                issues.append(f"{section}:{key[1]} -> {sorted(set(reasons))}")
    if issues:
        problems.append({"profile_id": profile_id,
                         "name": after.get("name"),
                         "issues": issues[:8]})

print(f"audited={audited} flagged={len(problems)}")
for problem in problems:
    print(json.dumps(problem, ensure_ascii=False))
