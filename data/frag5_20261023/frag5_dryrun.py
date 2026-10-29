#!/usr/bin/env python3
"""Frag-5 deploy spot check (dry-run, no mutation): both Raven
profiles' recovery dry-runs must now drop the verbatim sample-50h
prose shards with reason prose_shard_continuation, and both target
files must be byte-identical afterwards."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar

SHARDS = [
    "have it carry her",
    "use it to absorb energy from something or trap someone in a pocket dimension",
    "Can be sometimes exhausted by using her",
]


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
        "continuation_reason_in_report": "prose_shard_continuation" in blob,
        "shards_in_report": {s: (s in blob) for s in SHARDS},
        "tried": [
            {
                "source_id": t.get("source_id"),
                "dropped_items": t.get("dropped_items"),
                "boilerplate_fields": t.get("boilerplate_fields"),
            }
            for t in report.get("sources_tried") or []
        ],
        "guard_rejections": report.get("guard_rejections"),
        "errors": report.get("errors"),
    }


async def main() -> int:
    out = {"verbatim_screening": {
        s: ar.fragment_item_reasons(s, section="weaknesses") for s in SHARDS
    }}
    for name in ("raven-rebirth.yaml", "raven-prime-earth.yaml"):
        target = find(name)
        if target is None:
            out[name] = {"error": "not found"}
            continue
        out[name] = await run(target)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    Path("/app/data/frag5_20261023/dryrun_report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
