#!/usr/bin/env python3
"""Frag-7 synthetic dry-run proof for ONE profile (argv[1] = file name).

The two gate-50j profiles (the-immortal, the-immortal-image-comics)
had their debris item removed and their weaknesses restored to the
exact pre-run snapshot (empty); their other recovery targets are
filled, so a dry-run on the real files is a no-op. Restore each to a
recovery-eligible state on a SCRATCH copy (abilities + weaknesses
emptied, attack_potency blanked; recorded sources untouched),
dry-run the recovery against the live source pages, and verify the
frag-7 defenses: 'Out Orbital Punch' / 'Air Strike' must NOT come
back as weakness items -- either the source's weaknesses field is
dropped wholesale as explicit-none (extraction fix / merge backstop)
or the pieces drop with name_only_technique_in_weaknesses /
explicit_none. Neither the live file nor the scratch copy may be
mutated by the dry-run.
"""
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
OUTDIR = Path("/app/data/frag7_20261023")
SYNTH = OUTDIR / "synth"
SYNTH.mkdir(parents=True, exist_ok=True)

BAD_NAMES = ("Out Orbital Punch", "Air Strike")


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
    boilerplate = []
    for tried in report.get("sources_tried") or []:
        per_field = tried.get("dropped_items") or {}
        if isinstance(per_field, dict):
            for field_name, items in per_field.items():
                for item in items or []:
                    dropped.append({"field": field_name, **(item or {})})
        bf = tried.get("boilerplate_fields") or []
        br = tried.get("boilerplate_reasons") or {}
        if bf:
            boilerplate.append(
                {"source": tried.get("title") or tried.get("source_id"),
                 "fields": bf, "reasons": br}
            )

    recovered = report.get("recovered_fields") or []
    (OUTDIR / f"dryrun_{NAME}.report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=str))
    recovered_weakness_names = []
    applied = None
    if isinstance(recovered, dict):
        applied = recovered.get("weaknesses")
    if isinstance(applied, list):
        for item in applied:
            if isinstance(item, dict):
                recovered_weakness_names.append(str(item.get("name") or ""))
            else:
                recovered_weakness_names.append(str(item))

    bad_dropped = {}
    for bad in BAD_NAMES:
        bad_dropped[bad] = [
            d.get("reasons") or []
            for d in dropped
            if bad in json.dumps(d, ensure_ascii=False, default=str)
        ]
    return {
        "target": str(src),
        "live_mutated": live_before != md5(src),
        "synth_mutated_by_dryrun": synth_before != md5(dst),
        "recovered_fields": recovered if isinstance(recovered, list)
        else sorted(recovered.keys()),
        "recovered_weakness_names": recovered_weakness_names,
        "bad_names_merged": [
            b for b in BAD_NAMES
            if any(b == n or b in n for n in recovered_weakness_names)
        ],
        "bad_names_dropped_reasons": bad_dropped,
        "boilerplate": boilerplate,
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
