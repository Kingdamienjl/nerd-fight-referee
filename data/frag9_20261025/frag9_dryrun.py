#!/usr/bin/env python3
"""Frag-9 synthetic dry-run proof for ONE profile (argv[1] = file name).

The two gate-50l profiles (venom-earth-616, venom-mcu) had their
debris items removed and their weaknesses restored to the pre-run
snapshot; their other recovery targets are filled, so a dry-run on
the real files is a no-op. Restore each to a recovery-eligible state
on a SCRATCH copy (abilities + weaknesses emptied, attack_potency
blanked; recorded sources untouched), dry-run the recovery against
the live source pages, and verify the frag-9 defenses:
  - venom-earth-616: the two relative-pronoun openers, the three
    header + cut-off clauses, and the "like"-led fragment must NOT
    come back as weakness items.
  - venom-mcu: the numeric-split halves ("radiation up to 4" /
    "000 hertz" -- the thousands guard must keep "radiation up to
    4,000 hertz" whole; the whole number MAY re-merge as one real
    limit item), the "or" opener, and the "even" opener must NOT
    come back as split/fragment items.
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
OUTDIR = Path("/app/data/frag9_20261025")
SYNTH = OUTDIR / "synth"
SYNTH.mkdir(parents=True, exist_ok=True)

# name -> must-not-merge fragments (substring match on recovered names)
BAD = {
    "venom-earth-616.yaml": [
        "which has causes drastic shifts in his personality",
        "which can weaken or nullify the suit's healing powers",
        "Sonic and Heat: The Venom symbiote",
        "Darkforce: As Anti-Venom is formed from the Lightforce",
        "Antibody Overuse: If Anti-Venom overuses his healing powers",
        "like all others of its kind",
    ],
    "venom-marvel-cinematic-universe.yaml": [
        # split halves: either half merging alone is a failure
        "radiation up to 4",
        "000 hertz",
        "or by anything that can pass through the symbiote",
        "even in the eminence of a battle",
    ],
}
# name -> may-merge (audited-good / real) fragments, reported only.
# "radiation up to 4,000 hertz" as ONE whole item is the correct
# outcome of the thousands guard -- it must not be counted in BAD
# (the "radiation up to 4" substring check above would also match
# the whole number, so the dry-run report must distinguish the two;
# see the whole_number check in run()).
MAYBE = {
    "venom-earth-616.yaml": [],
    "venom-marvel-cinematic-universe.yaml": [
        "radiation up to 4,000 hertz",
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
            if any(
                b in n
                and not (
                    b == "radiation up to 4"
                    and "radiation up to 4,000 hertz" in n
                )
                for n in recovered_weakness_names
            )
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
