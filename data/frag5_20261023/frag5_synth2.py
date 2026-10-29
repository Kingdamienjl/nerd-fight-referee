#!/usr/bin/env python3
"""Frag-5 synth diagnostic #2: print exactly what the recovery
dropped and merged for the two Raven synth copies."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

SYNTH = Path("/app/data/frag5_20261023/synth")


def find(name: str) -> Path | None:
    hits = sorted(Path("/app/profiles").rglob(name))
    return hits[0] if hits else None


async def go() -> None:
    for name in ("raven-rebirth.yaml", "raven-prime-earth.yaml"):
        src = find(name)
        with src.open() as handle:
            prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
        prof["abilities"] = []
        prof["weaknesses"] = []
        power = prof.get("power_scale") or {}
        if isinstance(power.get("attack_potency"), dict):
            power["attack_potency"] = {"text": "", "source_ids": []}
        dst = SYNTH / ("diag-" + name)
        with dst.open("w") as handle:
            yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
        report = await ar.recover_profile_evidence(dst, dry_run=True)
        print("=====", name)
        for tried in report.get("sources_tried") or []:
            print(" source:", tried.get("source_id"))
            for dropped in tried.get("dropped_items") or []:
                print("  DROPPED:", json.dumps(dropped, ensure_ascii=False,
                                               default=str)[:320])
        for merge in report.get("merges") or []:
            print(" MERGE:", json.dumps(merge, ensure_ascii=False,
                                         default=str)[:420])
        prof_after = report.get("profile") or {}
        print(" weaknesses_after:", json.dumps(
            prof_after.get("weaknesses") or [], ensure_ascii=False,
            default=str)[:700])
        print(" parser_used:", report.get("parser_used"))


if __name__ == "__main__":
    asyncio.run(go())
