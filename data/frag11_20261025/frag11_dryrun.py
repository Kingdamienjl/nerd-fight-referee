#!/usr/bin/env python3
"""Frag-11 synthetic dry-run proof for ONE profile (argv[1] = file name).

Same pattern as frag-10: the gate-50n profiles had their debris
items/fields removed and their other recovery targets filled, so a
dry-run on the real files is a no-op. Restore each to a
recovery-eligible state on a SCRATCH copy (abilities + weaknesses
emptied; recovered power_scale fields blanked; recorded sources
untouched), dry-run the recovery against the live source pages, and
verify the frag-11 defenses: every verbatim failing item/stat must
NOT come back, and the promotion-branch fix must not leave an
eligible-but-invalid profile (schema_validation_blockers empty in
whatever state results). Neither the live file nor the scratch copy
may be mutated.
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
from battlebot.review import service

NAME = sys.argv[1]
OUTDIR = Path("/app/data/frag11_20261025")
SYNTH = OUTDIR / "synth"
SYNTH.mkdir(parents=True, exist_ok=True)

# name -> must-not-merge item substrings (abilities + weaknesses)
BAD_ITEMS = {
    "isaac.yaml": [
        "Battle ID Types",
        "Bird ID Types",
        "Mage ID Types",
        "Deadly Absorp",
        "Dark Lord abilities (4-D - Baseline)",
        "Creatures of Chaos (4-D - Baseline)",
        "Forcefield Creation (Via Protective FieldCastlevania",
    ],
    "maliketh.yaml": [
        "Radagon",
        "but after the Night of the black knives",
        "he was limited.",
        "Durability Negation Destined Death lowers and burns HP. Death Manipulation",
        "Frost Damage and the Blasphemous Claw",
    ],
}
# name -> must-not-merge stat values (exact)
BAD_STATS = {
    "oryx.yaml": {
        "speed": "Lifting Strength: Striking Strength:",
        "range": "Standard Equipment: Intelligence: Above Average",
    },
}
# fields blanked on the synthetic copy (gate-50n recovered fields)
BLANK_FIELDS = {
    "isaac.yaml": ("attack_potency", "speed", "durability", "stamina", "range", "intelligence", "tier"),
    "oryx.yaml": ("attack_potency", "speed", "durability", "range", "intelligence", "tier"),
    "maliketh.yaml": ("attack_potency", "speed", "durability", "stamina", "range", "intelligence", "tier"),
    "rodimus-prime.yaml": ("attack_potency", "speed", "durability", "range", "tier"),
    "soundwave.yaml": ("attack_potency", "speed", "durability", "range", "tier"),
    "shanoa.yaml": ("attack_potency", "speed", "durability", "range", "tier"),
}


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def find(name: str) -> Path | None:
    for cand in (Path("/app/profiles/needs_review").rglob(name),
                 Path("/app/profiles").rglob(name)):
        hits = sorted(cand)
        if hits:
            return hits[0]
    return None


def has_revision_metadata(prof) -> bool:
    return any(
        isinstance(s, dict)
        and s.get("source_type") == "mediawiki"
        and bool(s.get("revision_id"))
        and bool(s.get("revision_timestamp"))
        for s in prof.get("sources") or []
    )


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
    for field in BLANK_FIELDS.get(NAME, ("attack_potency", "tier", "range")):
        if isinstance(power.get(field), dict):
            power[field] = {"text": "", "source_ids": []}
    dst = SYNTH / NAME
    with dst.open("w") as handle:
        yaml.safe_dump(prof, handle, allow_unicode=True, sort_keys=False)
    synth_before = md5(dst)
    blockers_before = service.schema_validation_blockers(prof)
    report = await ar.recover_profile_evidence(dst, dry_run=True)
    (OUTDIR / f"dryrun_{NAME}.report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, default=str))

    prof_after = report.get("profile") or {}
    rec_items = []
    for section in ("abilities", "weaknesses", "equipment"):
        for item in prof_after.get(section) or []:
            if isinstance(item, dict):
                rec_items.append((section, str(item.get("name") or ""),
                                  str(item.get("description") or "")))
    power_after = prof_after.get("power_scale") or {}

    def _stat_text(field):
        entry = power_after.get(field)
        if isinstance(entry, dict):
            return str(entry.get("text") or "")
        return str(entry or "")

    bad_items = [
        b for b in BAD_ITEMS.get(NAME, [])
        if any(b in n or b in d for _, n, d in rec_items)
    ]
    bad_stats = {
        f: _stat_text(f)
        for f, v in BAD_STATS.get(NAME, {}).items()
        if _stat_text(f) and v in _stat_text(f)
    }
    dropped = []
    for tried in report.get("sources_tried") or []:
        per_field = tried.get("dropped_items") or {}
        if isinstance(per_field, dict):
            for field_name, items in per_field.items():
                for item in items or []:
                    dropped.append({**{"field": field_name}, **(item or {})})
    dropped_dump = json.dumps(dropped, ensure_ascii=False, default=str)
    bad_drop_reasons = {
        b: sorted({r for d in dropped for r in (d.get("reasons") or [])
                   if b in json.dumps(d, ensure_ascii=False, default=str)})
        for b in BAD_ITEMS.get(NAME, [])
    }
    stat_drop_reasons = {}
    for tried in report.get("sources_tried") or []:
        br = tried.get("boilerplate_reasons") or {}
        for field in BAD_STATS.get(NAME, {}):
            if field in (tried.get("boilerplate_fields") or []):
                stat_drop_reasons.setdefault(field, set()).update(br.get(field) or [])
    stat_drop_reasons = {k: sorted(v) for k, v in stat_drop_reasons.items()}

    gen = prof_after.get("generation") or {}
    return {
        "target": str(src),
        "live_mutated": live_before != md5(src),
        "synth_mutated_by_dryrun": synth_before != md5(dst),
        "recovered_fields": sorted(report.get("recovered_fields") or []),
        "recovered_item_count": len(rec_items),
        "recovered_items": [f"[{s}] {n}" for s, n, _ in rec_items],
        "recovered_stats": {f: _stat_text(f) for f in
                            ("attack_potency", "speed", "durability", "range",
                             "intelligence", "tier")
                            if _stat_text(f)},
        "bad_items_merged": bad_items,
        "bad_items_dropped_reasons": bad_drop_reasons,
        "bad_stats_merged": bad_stats,
        "bad_stat_drop_reasons": stat_drop_reasons,
        "dropped_count": len(dropped),
        "promotion": {
            "battle_eligible": bool(prof_after.get("battle_eligible")),
            "status": prof_after.get("status"),
            "profile_type": prof_after.get("profile_type"),
            "confidence": gen.get("confidence"),
            "reasons": gen.get("ineligible_reasons"),
            "revision_metadata_stamped": has_revision_metadata(prof_after),
            "approval_blockers_after": report.get("blockers_after"),
            "schema_blockers_before_recovery": blockers_before,
            "schema_blockers_after": service.schema_validation_blockers(prof_after),
        },
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
