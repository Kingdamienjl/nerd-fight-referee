"""Expand manual-review dump: for each of the 9 mass-run recovered
profiles, print EVERY new item (abilities/weaknesses/equipment) and every
new/changed stat with FULL text (no truncation), plus source titles.
Diffs expected (expand_expected.json) vs actual (expand_actual_mass.json),
keyed the same way as the audit (item id or normalized name).
Read-only.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

expected = json.loads(Path("/app/data/expand_20261025/expand_expected.json").read_text())
actual = json.loads(Path("/app/data/expand_20261025/expand_actual_mass.json").read_text())
progress = json.loads(Path("/app/data/recovery_progress.json").read_text())
mass = json.loads(Path("/app/data/expand_20261025/expand_manifest_mass.json").read_text())


def item_key(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "") or ar.normalized_identity_text(
        item.get("name") or item.get("label") or "")


def source_titles(after, item):
    sb = {str(s.get("id")): s for s in after.get("sources") or [] if isinstance(s, dict)}
    return [str(sb[str(sid)].get("title")) for sid in item.get("source_ids") or []
            if str(sid) in sb]


for rel in mass["sample"]:
    entry = progress.get(rel) or {}
    if not entry.get("recovered_fields"):
        continue
    before, after = expected.get(rel) or {}, actual.get(rel) or {}
    print("=" * 100)
    print(f"PROFILE: {rel}")
    print(f"  recovered_fields={entry.get('recovered_fields')} promoted={entry.get('promoted')} identity_mismatch={entry.get('identity_mismatch')}")
    print(f"  blockers_before={entry.get('blockers_before')}")
    print(f"  blockers_after={entry.get('blockers_after')}")
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
            print(f"  [NEW STAT {field}] len={len(a_text)} src={source_titles(after, a_item)}")
            print(f"    {a_text!r}")
    if before.get("tier") != after.get("tier"):
        print(f"  [TIER] before={before.get('tier')!r} after={after.get('tier')!r}")
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
            name = str(item.get("name") or "")
            desc = str(item.get("description") or "")
            text = str(item.get("text") or "")
            print(f"  [NEW {section}] name_len={len(name)} desc_len={len(desc)} src={source_titles(after, item)}")
            print(f"    NAME: {name!r}")
            if desc:
                print(f"    DESC: {desc!r}")
            if text:
                print(f"    TEXT: {text!r}")
print("=" * 100)
print("MANUAL-REVIEW-DUMP DONE")
