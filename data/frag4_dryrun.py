#!/usr/bin/env python3
"""Frag-4 deploy spot checks (dry-run, no mutation):
  - harley-quinn-post-flashpoint: the glued tab-key composite
    ability must now be dropped with reason tab_key_composite.
  - midnighter-post-crisis: the bare-qualifier tier "At least"
    must now be dropped with reason bare_qualifier (shown via the
    report's per-field reasons when the source still yields it,
    and unconditionally via the verbatim screening composition).
Both target files must be byte-identical afterwards.
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

COMPOSITE = "Base Hax Hammer Harleen Hax AoR Harley Hax Death Manipulation"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def find(name: str) -> Path | None:
    hits = sorted(Path("/app/profiles").rglob(name))
    return hits[0] if hits else None


async def run(target: Path) -> dict:
    before = md5(target)
    report = await ar.recover_profile_evidence(target, dry_run=True)
    after = md5(target)
    blob = json.dumps(report, ensure_ascii=False, default=str)
    return {
        "target": str(target),
        "file_mutated": before != after,
        "recovered_fields": report.get("recovered_fields"),
        "tab_key_composite_in_report": "tab_key_composite" in blob,
        "bare_qualifier_in_report": "bare_qualifier" in blob,
        "composite_text_in_report": COMPOSITE in blob,
        "tried": [
            {
                "source_id": t.get("source_id"),
                "boilerplate_fields": t.get("boilerplate_fields"),
                "boilerplate_reasons": t.get("boilerplate_reasons"),
                "dropped_items": t.get("dropped_items"),
                "scoped_fields": t.get("scoped_fields"),
            }
            for t in report.get("sources_tried") or []
        ],
        "guard_rejections": report.get("guard_rejections"),
        "errors": report.get("errors"),
    }


async def main() -> int:
    out = {"verbatim_screening": {
        "composite_fragment_reasons": ar.fragment_item_reasons(
            COMPOSITE, section="powers_and_abilities"),
        "at_least_stat_reasons": ar.stat_field_rejection_reasons("At least"),
        "at_least_fragment_scalar": ar.fragment_scalar_reasons("At least"),
    }}
    for name in ("harley-quinn-post-flashpoint.yaml", "midnighter-post-crisis.yaml"):
        target = find(name)
        if target is None:
            out[name] = {"error": "not found"}
            continue
        out[name] = await run(target)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    Path("/app/data/frag4_20261022/dryrun_report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
