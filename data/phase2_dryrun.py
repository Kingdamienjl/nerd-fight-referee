#!/usr/bin/env python3
"""Phase 2 continuity live-verify: dry-run repair on apollo-post-crisis.

Expectation: the recorded Post-Flashpoint source attempt is flagged
continuity_mismatch=True by annotate_attempt_quality, and the profile
file is NOT mutated (dry_run). Prints a compact JSON verdict.
"""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

TARGET = Path("/app/profiles/generated/comic/dc/apollo-post-crisis.yaml")
DEBUG_DIR = Path("/app/data/phase2_20261022")


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
    verdict = {
        "target": str(TARGET),
        "md5_before": before,
        "md5_after": after,
        "file_mutated": before != after,
        "changed": result.changed,
        "promoted": result.promoted,
        "errors": result.errors,
        "repaired_fields": result.repaired_fields,
        "unresolved_fields": result.unresolved_fields,
        "attempts": [
            {
                "source_id": a.source_id,
                "provider_id": a.provider_id,
                "url": a.url,
                "page_title": a.normalized_page_title,
                "fetch_status": a.fetch_status,
                "continuity_mismatch": a.continuity_mismatch,
                "continuity_detail": a.continuity_detail,
            }
            for a in result.source_attempts
        ],
    }
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
