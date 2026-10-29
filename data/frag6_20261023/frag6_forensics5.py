#!/usr/bin/env python3
"""Frag-6 gate forensics #5: synthetic dry-run on the-immortal with
the FULL recovery report dumped, to see exactly what the pipeline
fetches and keeps for weaknesses."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

SRC = Path("/app/profiles/needs_review/comic/image-comics/the-immortal.yaml")
SYNTH = Path("/app/data/frag6_20261023/synth/the-immortal.yaml")
SYNTH.parent.mkdir(parents=True, exist_ok=True)


async def main() -> int:
    prof = yaml.load(SRC.open(), Loader=yaml.CSafeLoader) or {}
    prof["abilities"] = []
    prof["weaknesses"] = []
    with SYNTH.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    report = await ar.recover_profile_evidence(SYNTH, dry_run=True)
    print(json.dumps(report, indent=1, ensure_ascii=False, default=str)[:9000])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
