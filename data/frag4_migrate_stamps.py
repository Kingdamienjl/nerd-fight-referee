#!/usr/bin/env python3
"""Frag-4 Part 2: migrate demotion stamps to their schema-legal
home (review.<key>) in every profile file that carries a legacy
top-level stamp, then prove each migrated file passes the
importer's own CharacterProfile validation and that the stamps
remain readable via battlebot.profiles.demotion.

Dry-run by default; pass --apply to write. Writes a JSON report to
/app/data/frag4_20261022/stamp_migration_report.json.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.ingest import import_profiles
from battlebot.profiles import yaml_io
from battlebot.profiles.demotion import (
    DEMOTION_STAMP_KEYS,
    demotion_stamps,
    migrate_demotion_stamps,
    record_ineligible_reason,
)

APPLY = "--apply" in sys.argv
ROOT = Path("/app/profiles")
STAMP_LINE = re.compile(r"(?:continuity_demotion|template_cleanup_demotion):")

candidates = []
for path in sorted(ROOT.rglob("*.yaml")):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    if STAMP_LINE.search(text):
        candidates.append(path)

results = []
for path in candidates:
    rel = str(path.relative_to(Path("/app")))
    entry = {"profile": rel}
    profile = yaml_io.load_yaml(path)
    before_stamps = demotion_stamps(profile)
    if not before_stamps:
        continue
    entry["stamps_before"] = sorted(before_stamps)
    moved = migrate_demotion_stamps(profile)
    entry["moved"] = moved
    # Second latent defect the stamp error had masked: the demote
    # runs flipped battle_eligible without recording a reason, and
    # the eligibility contract rejects ineligible profiles with an
    # empty generation.ineligible_reasons. Record the stamp rule.
    added = []
    if profile.get("battle_eligible") is False:
        for key in sorted(before_stamps):
            if record_ineligible_reason(profile, key):
                added.append(key)
    entry["ineligible_reasons_added"] = added
    after_stamps = demotion_stamps(profile)
    entry["stamps_after"] = sorted(after_stamps)
    entry["payload_preserved"] = all(
        after_stamps.get(k) == before_stamps.get(k) for k in before_stamps
    )
    entry["top_level_clean"] = not any(
        key in profile for key in DEMOTION_STAMP_KEYS
    )
    changed = bool(moved or added)
    entry["changed"] = changed
    if APPLY and changed:
        yaml_io.write_yaml(path, profile)
        # Re-read from disk: stamps must survive the round trip and
        # the file must pass the importer's validation gate.
        reread = yaml_io.load_yaml(path)
        entry["reread_stamps"] = sorted(demotion_stamps(reread))
        try:
            validated = import_profiles.validate_profile_path(path)
            entry["validates"] = True
            entry["validated_eligible"] = bool(validated.battle_eligible)
        except Exception as exc:  # noqa: BLE001
            entry["validates"] = False
            entry["validation_error"] = str(exc)[:300].replace("\n", " | ")
    results.append(entry)
    print(json.dumps(entry, ensure_ascii=False))

summary = {
    "apply": APPLY,
    "files_with_stamps": len(results),
    "files_migrated": sum(1 for r in results if r["moved"]),
    "files_reason_fixed": sum(
        1 for r in results if r["ineligible_reasons_added"]
    ),
    "all_payloads_preserved": all(
        r["payload_preserved"] for r in results
    ),
    "all_top_level_clean": all(r["top_level_clean"] for r in results),
}
if APPLY:
    summary["all_validate"] = all(
        r.get("validates") for r in results if r["changed"]
    )
    summary["validation_failures"] = [
        r["profile"] for r in results if r["changed"] and not r.get("validates")
    ]
print(json.dumps({"SUMMARY": summary}, indent=1))
out = Path("/app/data/frag4_20261022/stamp_migration_report.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"summary": summary, "results": results}, indent=1))
