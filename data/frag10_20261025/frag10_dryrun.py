#!/usr/bin/env python3
"""Frag-10 synthetic dry-run proof for ONE profile (argv[1] = file name).

The 13 gate-50m profiles had their debris items/fields removed and
their weaknesses restored to the pre-run snapshot; their other recovery
targets are filled, so a dry-run on the real files is a no-op. Restore
each to a recovery-eligible state on a SCRATCH copy (abilities +
weaknesses emptied; attack_potency, tier, range blanked; recorded
sources untouched), dry-run the recovery against the live source pages,
and verify the frag-10 defenses: every verbatim failing weakness item
must NOT come back, every rating-stripped tier must NOT come back
(Arcee's must come back WITH its ratings, proving the parser fix),
and devastator's range must NOT come back carrying image filenames.
Neither the live file nor the scratch copy may be mutated.
"""
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar

NAME = sys.argv[1]
OUTDIR = Path("/app/data/frag10_20261025")
SYNTH = OUTDIR / "synth"
SYNTH.mkdir(parents=True, exist_ok=True)

# name -> must-not-merge weakness substrings
BAD_WEAK = {
    "casey-jones.yaml": [
        "yet believes himself to be and thus can be overwhelmed by the stronger mutants they may face",
    ],
    "leatherhead.yaml": [
        "especially when anything related to the Kraang is brought up",
    ],
    "shredder.yaml": ["where he is ticklish"],
    "blackarachnia.yaml": ["insane and is very self loathing"],
    "devastator.yaml": [
        "Devastator is hardly slow. He is",
        "rather easy to outmaneuver",
        "As the Constructicons'",
    ],
    "ironhide.yaml": ["As Ironhide ages"],
    "rodimus-prime.yaml": ["feeling he don't ever live up to Optimus Prime"],
    "soundwave.yaml": [
        "as he passes up a chance to kill Wheeljack in order to save Laserbeak",
    ],
    "starscream.yaml": [
        "very short tempered",
        "If the allspark shard in his head is removed",
    ],
    "ultra-magnus.yaml": [
        "to the point where it could potentially impede his judgement",
    ],
}
# name -> must-not-merge stripped tier forms (substring match)
BAD_TIER = {
    "arcee.yaml": ["likely higher. with swords"],
    "blackarachnia.yaml": ["At most, possibly far higher"],
    "galvatron.yaml": ["At least, higher with the Heart of Darkness"],
    "ironhide.yaml": [
        "At most. higher with Stealth Force, even higher with Heavy Iron 2.0"
    ],
    "predaking.yaml": ["At least, likely higher, even higher with Beast Mode"],
}
# name -> tier text that MUST appear when a tier merges (parser fix)
TIER_MUST_HAVE = {
    "arcee.yaml": ["5-B", "5-A"],
}
BAD_RANGE_FILES = {
    "devastator.yaml": [
        "SolarBeamRifleDevastation.png",
        "DrillMisslesDevastation.jpg",
        "DrillsDevastation.jpg",
    ],
}
RATING_RE = re.compile(r"\b\d+-[A-C]\b")


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
    for field in ("attack_potency", "tier", "range"):
        if isinstance(power.get(field), dict):
            power[field] = {"text": "", "source_ids": []}
    dst = SYNTH / NAME
    with dst.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    synth_before = md5(dst)
    report = await ar.recover_profile_evidence(dst, dry_run=True)
    (OUTDIR / f"dryrun_{NAME}.report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=str))

    # Recovered VALUES live in report["profile"] (mutated in memory;
    # dry_run only skips the disk write). report["recovered_fields"]
    # is a LIST of field names, not a dict -- reading values from it
    # yields nothing (frag-10 dry-run round 1 bug, caught on review).
    prof_after = report.get("profile") or {}
    rec_weak_names = []
    for item in prof_after.get("weaknesses") or []:
        if isinstance(item, dict):
            rec_weak_names.append(str(item.get("name") or ""))
        else:
            rec_weak_names.append(str(item))
    power_after = prof_after.get("power_scale") or {}

    def _stat_text(field):
        entry = power_after.get(field)
        if isinstance(entry, dict):
            return str(entry.get("text") or "")
        return str(entry or "")

    rec_tier = _stat_text("tier")
    rec_range = _stat_text("range")
    recovered = report.get("recovered_fields") or []

    bad_weak = [
        b for b in BAD_WEAK.get(NAME, [])
        if any(b in n for n in rec_weak_names)
    ]
    bad_tier = [
        b for b in BAD_TIER.get(NAME, [])
        if b in rec_tier
        and "qualifier_only_stat" in ar.boilerplate_reasons(rec_tier, scalar=True)
    ]
    tier_flagged = (
        bool(rec_tier)
        and "qualifier_only_stat" in ar.boilerplate_reasons(rec_tier, scalar=True)
    )
    tier_missing_ratings = [
        m for m in TIER_MUST_HAVE.get(NAME, []) if m not in rec_tier
    ] if rec_tier else []
    bad_range = [
        b for b in BAD_RANGE_FILES.get(NAME, [])
        if b in rec_range
    ]

    dropped = []
    for tried in report.get("sources_tried") or []:
        per_field = tried.get("dropped_items") or {}
        if isinstance(per_field, dict):
            for field_name, items in per_field.items():
                for item in items or []:
                    dropped.append({**{"field": field_name}, **(item or {})})
    dropped_dump = json.dumps(dropped, ensure_ascii=False, default=str)
    bad_weak_dropped_reasons = {
        b: [d.get("reasons") or []
            for d in dropped
            if d.get("field") == "weaknesses" and b in dropped_dump
            and b in json.dumps(d, ensure_ascii=False, default=str)]
        for b in BAD_WEAK.get(NAME, [])
    }
    tier_drop_reasons = []
    range_drop_reasons = []
    for tried in report.get("sources_tried") or []:
        br = tried.get("boilerplate_reasons") or {}
        if "tier" in (tried.get("boilerplate_fields") or []):
            tier_drop_reasons.extend(br.get("tier") or [])
        if "range" in (tried.get("boilerplate_fields") or []):
            range_drop_reasons.extend(br.get("range") or [])

    return {
        "target": str(src),
        "live_mutated": live_before != md5(src),
        "synth_mutated_by_dryrun": synth_before != md5(dst),
        "recovered_fields": sorted(recovered) if isinstance(recovered, list) else recovered,
        "recovered_weakness_names": rec_weak_names,
        "recovered_tier": rec_tier,
        "recovered_range": rec_range,
        "bad_weak_merged": bad_weak,
        "bad_weak_dropped_reasons": bad_weak_dropped_reasons,
        "bad_tier_merged": bad_tier,
        "tier_flagged_qualifier_only": tier_flagged,
        "tier_missing_ratings": tier_missing_ratings,
        "tier_drop_reasons": sorted(set(tier_drop_reasons)),
        "range_drop_reasons": sorted(set(range_drop_reasons)),
        "bad_range_files_merged": bad_range,
        "dropped_weaknesses": [d for d in dropped if d.get("field") == "weaknesses"],
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
