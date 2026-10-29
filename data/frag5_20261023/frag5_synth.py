#!/usr/bin/env python3
"""Frag-5 synthetic dry-run proof: the live Raven profiles currently
have no recovery targets (their stats/abilities are filled; the 50h
debris rode along on a weaknesses merge), so a dry-run on the real
files is a correct no-op. Restore each profile to a recovery-eligible
state on a SCRATCH copy (abilities emptied, attack_potency blanked,
weaknesses emptied -- the recorded sources untouched), dry-run the
recovery against the live source pages, and verify the verbatim
Soul Self shards are dropped with prose_shard_continuation and
nothing is written."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

SHARDS = [
    "have it carry her",
    "use it to absorb energy from something or trap someone in a pocket dimension",
    "Can be sometimes exhausted by using her",
]
SYNTH = Path("/app/data/frag5_20261023/synth")
SYNTH.mkdir(parents=True, exist_ok=True)


def find(name: str) -> Path | None:
    hits = sorted(Path("/app/profiles").rglob(name))
    return hits[0] if hits else None


async def run(name: str) -> dict:
    src = find(name)
    if src is None:
        return {"error": f"{name} not found"}
    with src.open() as handle:
        prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    prof["abilities"] = []
    prof["weaknesses"] = []
    power = prof.get("power_scale") or {}
    if isinstance(power.get("attack_potency"), dict):
        power["attack_potency"] = {"text": "", "source_ids": []}
    dst = SYNTH / name
    with dst.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    before = hashlib.md5(dst.read_bytes()).hexdigest()
    report = await ar.recover_profile_evidence(dst, dry_run=True)
    after = hashlib.md5(dst.read_bytes()).hexdigest()
    dropped = []
    for tried in report.get("sources_tried") or []:
        for item in tried.get("dropped_items") or []:
            dropped.append(item)
    blob = json.dumps(report, ensure_ascii=False, default=str)
    return {
        "target": str(src),
        "synth_mutated_by_dryrun": before != after,
        "recovered_fields": report.get("recovered_fields"),
        "continuation_reason_in_report": "prose_shard_continuation" in blob,
        "shards_dropped": {
            s: any(s in json.dumps(d, ensure_ascii=False, default=str)
                   and "prose_shard_continuation" in
                   json.dumps(d, ensure_ascii=False, default=str)
                   for d in dropped)
            for s in SHARDS
        },
        "dropped_count": len(dropped),
        "errors": report.get("error"),
        "identity_mismatch": report.get("identity_mismatch"),
    }


async def main() -> int:
    out = {}
    for name in ("raven-rebirth.yaml", "raven-prime-earth.yaml"):
        out[name] = await run(name)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    Path("/app/data/frag5_20261023/synth_report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
