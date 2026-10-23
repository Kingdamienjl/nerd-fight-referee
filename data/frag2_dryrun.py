#!/usr/bin/env python3
"""Part 2 live-verify: dry-run repair on etrigan-dc-comics.

Expectation: with the item screens wired into attempt_from_result,
the source attempt whose weakness text carries the editor-note
footer now shows it in metadata dropped_items/stripped_items (the
footer must NOT survive into the attempt field map), and the
profile file is NOT mutated (dry_run).
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

TARGET = Path("/app/profiles/generated/comic/dc/etrigan-dc-comics.yaml")
DEBUG_DIR = Path("/app/data/frag2_20261022")


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


async def main() -> int:
    before = md5(TARGET)
    result = await ar.repair_profile(
        TARGET,
        dry_run=True,
        debug_dir=DEBUG_DIR,
        verbose=False,
    )
    after = md5(TARGET)
    attempts = []
    for a in result.source_attempts:
        field_map = ar.attempt_field_map(a)
        weaknesses = field_map.get("weaknesses") or ""
        attempts.append(
            {
                "source_id": a.source_id,
                "fetch_status": a.fetch_status,
                "footer_in_weaknesses": "Before making any changes" in weaknesses,
                "weaknesses_preview": weaknesses[:160],
                "dropped_items": a.metadata.get("dropped_items"),
                "stripped_items": a.metadata.get("stripped_items"),
            }
        )
    verdict = {
        "target": str(TARGET),
        "file_mutated": before != after,
        "changed": result.changed,
        "errors": result.errors,
        "attempts": attempts,
    }
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
