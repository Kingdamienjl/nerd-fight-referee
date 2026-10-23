#!/usr/bin/env python3
"""Frag-4 spot check #2 (synthetic): midnighter-post-crisis as it
stood in sample 50g -- core stats empty, so recovery targets the
CSPW page that yielded tier "At least". The dry-run on this copy
must drop tier with bare_qualifier while recovering real fields.
The real profile is never touched (dry_run + a scratch copy).
"""
import asyncio
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io
from battlebot.review import auto_repair as ar

SRC = Path("/app/profiles/needs_review/comic/dc/midnighter-post-crisis.yaml")
COPY = Path("/app/data/frag4_20261022/midnighter_synth.yaml")


async def main() -> int:
    profile = yaml_io.load_yaml(SRC)
    for axis in ("tier", "attack_potency", "speed", "durability"):
        entry = (profile.get("power_scale") or {}).get(axis)
        if isinstance(entry, dict):
            entry["text"] = ""
            entry["source_ids"] = []
            entry["confidence"] = 0.0
    yaml_io.write_yaml(COPY, profile)
    report = await ar.recover_profile_evidence(COPY, dry_run=True)
    tried = []
    for t in report.get("sources_tried") or []:
        tried.append({
            "source_id": t.get("source_id"),
            "boilerplate_fields": t.get("boilerplate_fields"),
            "boilerplate_reasons": t.get("boilerplate_reasons"),
            "scoped_fields": t.get("scoped_fields"),
        })
    out = {
        "recovered_fields": report.get("recovered_fields"),
        "tier_reasons": [
            (t["boilerplate_reasons"] or {}).get("tier")
            for t in tried
            if (t.get("boilerplate_reasons") or {}).get("tier")
        ],
        "bare_qualifier_seen": any(
            "bare_qualifier" in (reasons or [])
            for t in tried
            for reasons in (t.get("boilerplate_reasons") or {}).values()
        ),
        "profile_tier_after": (
            (report.get("profile") or {}).get("power_scale") or {}
        ).get("tier"),
        "tried": tried,
        "errors": report.get("errors"),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    Path("/app/data/frag4_20261022/midnighter_synth_report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
