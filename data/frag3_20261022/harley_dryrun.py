#!/usr/bin/env python3
"""Frag-3 Part 2 targeted verification: recovery dry-run on
harley-quinn-post-flashpoint. The CSPW source page merged four
template artifacts in sample 50f; with the template screens live,
the dry-run must show all four refused/dropped by the screens and
the profile file byte-identical afterwards."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

CANDIDATES = sorted(Path("/app/profiles").rglob("harley-quinn-post-flashpoint.yaml"))
TARGET = CANDIDATES[0] if CANDIDATES else None

ARTIFACTS = (
    "will finish upon return",
    "attacks/abilities can cover",
    "self-explanatory feats",
    "speed feats",
    "durability feats",
)


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


async def main() -> int:
    if TARGET is None:
        print(json.dumps({"error": "harley-quinn-post-flashpoint.yaml not found"}))
        return 1
    before = md5(TARGET)
    report = await ar.recover_profile_evidence(TARGET, dry_run=True)
    after = md5(TARGET)
    blob = json.dumps(report, ensure_ascii=False, default=str).casefold()
    tried_summary = []
    for t in report.get("sources_tried") or []:
        tried_summary.append(
            {
                "source_id": t.get("source_id"),
                "boilerplate_fields": t.get("boilerplate_fields"),
                "boilerplate_reasons": t.get("boilerplate_reasons"),
                "dropped_items": t.get("dropped_items"),
                "scoped_fields": t.get("scoped_fields"),
            }
        )
    verdict = {
        "target": str(TARGET),
        "file_mutated": before != after,
        "recovered_fields": report.get("recovered_fields"),
        "merges": report.get("merges"),
        "artifacts_in_report_blob": [a for a in ARTIFACTS if a in blob],
        "wip_reason_present": "wip_placeholder_stat" in blob,
        "definition_reason_present": "field_definition_stat" in blob,
        "template_instruction_present": "template_instruction" in blob,
        "feats_label_present": "feats_label" in blob,
        "sources_tried": tried_summary,
        "guard_rejections": report.get("guard_rejections"),
        "errors": report.get("errors"),
    }
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    Path("/app/data/frag3_20261022/harley_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
