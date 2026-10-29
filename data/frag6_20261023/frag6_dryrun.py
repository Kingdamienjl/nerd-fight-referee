#!/usr/bin/env python3
"""Frag-6 synthetic dry-run proof for ONE profile (argv[1] = file name).

The live profiles' weaknesses were restored to their exact pre-50i
state (empty) and their other recovery targets are filled, so a
dry-run on the real files is a no-op. Restore each profile to a
recovery-eligible state on a SCRATCH copy (abilities + weaknesses
emptied, attack_potency blanked; recorded sources untouched), dry-run
the recovery against the live source pages, and verify the verbatim
50i debris items are dropped with the new frag-6 reasons
(editorial_essay / editor_instruction for superman-prime-earth;
technique_in_weaknesses + concessive_shard for the starfires).
Neither the live file nor the scratch copy may be mutated."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

NAME = sys.argv[1]
OUTDIR = Path("/app/data/frag6_20261023")
SYNTH = OUTDIR / "synth"
SYNTH.mkdir(parents=True, exist_ok=True)

EXPECT = {
    "superman-prime-earth.yaml": [
        ("how the powers and nature of the character fundamentally",
         "editorial_essay"),
        ("you make sure that the text has good grammar", "editor_instruction"),
    ],
    "starfire-dc-comics.yaml": [
        ("Starbolt", "technique_in_weaknesses"),
        ("Nova", "technique_in_weaknesses"),
        ("though this is draining to use", "concessive_shard"),
    ],
    "starfire-rebirth.yaml": [
        ("Starbolt", "technique_in_weaknesses"),
        ("Nova", "technique_in_weaknesses"),
        ("though this is draining to use", "concessive_shard"),
    ],
}


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def find(name: str) -> Path | None:
    hits = sorted(Path("/app/profiles").rglob(name))
    return hits[0] if hits else None


async def run() -> dict:
    src = find(NAME)
    if src is None:
        return {"error": f"{NAME} not found"}
    live_before = md5(src)
    with src.open() as handle:
        prof = yaml.load(handle, Loader=yaml.CSafeLoader) or {}
    prof["abilities"] = []
    prof["weaknesses"] = []
    power = prof.get("power_scale") or {}
    if isinstance(power.get("attack_potency"), dict):
        power["attack_potency"] = {"text": "", "source_ids": []}
    dst = SYNTH / NAME
    with dst.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    synth_before = md5(dst)
    report = await ar.recover_profile_evidence(dst, dry_run=True)
    dropped = []
    for tried in report.get("sources_tried") or []:
        per_field = tried.get("dropped_items") or {}
        if isinstance(per_field, dict):
            for field_name, items in per_field.items():
                for item in items or []:
                    dropped.append({"field": field_name, **(item or {})})
        elif isinstance(per_field, list):
            dropped.extend(per_field)
    checks = {}
    for needle, reason in EXPECT.get(NAME, []):
        checks[f"{needle!r} -> {reason}"] = any(
            needle in json.dumps(d, ensure_ascii=False, default=str)
            and reason in (d.get("reasons") or [])
            for d in dropped
        )
    return {
        "target": str(src),
        "live_mutated": live_before != md5(src),
        "synth_mutated_by_dryrun": synth_before != md5(dst),
        "recovered_fields": report.get("recovered_fields"),
        "checks": checks,
        "dropped_weaknesses": [
            d for d in dropped if d.get("field") == "weaknesses"
        ],
        "dropped_count": len(dropped),
        "errors": report.get("error"),
        "identity_mismatch": report.get("identity_mismatch"),
    }


async def main() -> int:
    out = await run()
    print(json.dumps(out, indent=2, ensure_ascii=False))
    (OUTDIR / f"dryrun_{NAME}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
