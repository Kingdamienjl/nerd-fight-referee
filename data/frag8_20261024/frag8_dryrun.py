#!/usr/bin/env python3
"""Frag-8 synthetic dry-run proof for ONE profile (argv[1] = file name).

The three gate-50k profiles (carnage-mcu, darwin, kraven-mcu) had
their debris items removed and their weaknesses restored to the
pre-run snapshot; their other recovery targets are filled, so a
dry-run on the real files is a no-op. Restore each to a
recovery-eligible state on a SCRATCH copy (abilities + weaknesses
emptied, attack_potency blanked; recorded sources untouched),
dry-run the recovery against the live source pages, and verify the
frag-8 defenses:
  - carnage: the Death Battle disclaimer must NOT come back as a
    weakness item; "Is weak to fire" may re-merge (real weakness).
  - darwin: shards 2/3/4 must NOT come back ("but will not meet his
    desires...", "during his fight with the Hulk", "rather than
    supplying..."). The lead clause ("His body will adapt...") is
    EXPECTED to re-merge: no screen catches it by design (see the
    _prose_sentence_shard docstring); report it explicitly, do not
    treat it as a dry-run failure.
  - kraven-mcu: "leading to mistakes." must NOT come back; the kept
    lead clause ("His belief in his superior hunting abilities...")
    may re-merge (audited-good, Chris did not overrule).
Neither the live file nor the scratch copy may be mutated.
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
OUTDIR = Path("/app/data/frag8_20261024")
SYNTH = OUTDIR / "synth"
SYNTH.mkdir(parents=True, exist_ok=True)

# name -> must-not-merge fragments (substring match on recovered names)
BAD = {
    "carnage-marvel-cinematic-universe.yaml": [
        "any information displayed on any profile",
    ],
    "darwin.yaml": [
        "but will not meet his desires",
        "during his fight with the Hulk",
        "rather than supplying a combat-related power",
    ],
    "kraven-the-hunter-marvel-cinematic-universe.yaml": [
        "leading to mistakes",
    ],
}
# name -> may-merge (audited-good / real) fragments, reported only
MAYBE = {
    "carnage-marvel-cinematic-universe.yaml": ["Is weak to fire"],
    "darwin.yaml": ["His body will adapt to whatever means"],
    "kraven-the-hunter-marvel-cinematic-universe.yaml": [
        "His belief in his superior hunting abilities"
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
    boilerplate = []
    for tried in report.get("sources_tried") or []:
        per_field = tried.get("dropped_items") or {}
        if isinstance(per_field, dict):
            for field_name, items in per_field.items():
                for item in items or []:
                    dropped.append({**{"field": field_name}, **(item or {})})
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
    if isinstance(recovered, dict):
        applied = recovered.get("weaknesses")
        if isinstance(applied, list):
            for item in applied:
                if isinstance(item, dict):
                    recovered_weakness_names.append(
                        str(item.get("name") or ""))
                else:
                    recovered_weakness_names.append(str(item))

    bad = BAD.get(NAME, [])
    maybe = MAYBE.get(NAME, [])
    return {
        "target": str(src),
        "live_mutated": live_before != md5(src),
        "synth_mutated_by_dryrun": synth_before != md5(dst),
        "recovered_fields": recovered if isinstance(recovered, list)
        else sorted(recovered.keys()),
        "recovered_weakness_names": recovered_weakness_names,
        "bad_names_merged": [
            b for b in bad
            if any(b in n for n in recovered_weakness_names)
        ],
        "maybe_merged": [
            m for m in maybe
            if any(m in n for n in recovered_weakness_names)
        ],
        "bad_names_dropped_reasons": {
            b: [d.get("reasons") or []
                for d in dropped
                if b in json.dumps(d, ensure_ascii=False, default=str)]
            for b in bad
        },
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
