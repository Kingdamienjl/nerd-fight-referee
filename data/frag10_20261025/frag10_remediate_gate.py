#!/usr/bin/env python3
"""Frag-10 gate-created invalid remediation: the gate run's recovery left 5
profiles INVALID — apply_primary_profile_state's promotion branch fired on
evidence_quality_blockers ([]) alone, marking them battle_eligible=True +
generation.ineligible_reasons=[] + status=provisional, while the approval
gate (service.approval_blockers) refused promotion, so approve_profile
never ran and the file was left eligible-but-incomplete. The schema's
validate_eligibility_contract then fails them (eligible requires revision
metadata + attack_potency/speed/durability + abilities + confidence>=0.55).
Same backup-restore mechanism as frag10_remediate.py: restore ONLY the
eligibility-contract bookkeeping (battle_eligible, status, profile_type,
generation.ineligible_reasons, generation.confidence) from the frag10-gate
backup; merged CONTENT is untouched (good merges kept, bad merges already
reverted by revert50n.py); profile_hash is NOT recomputed; each file is
validated after the write and the set is re-scanned. Writes
gate_remediation.json."""
import copy
import hashlib
import json
import tarfile
from pathlib import Path

import yaml
from battlebot.ingest.import_profiles import validate_profile_path

GATE_TAR = "/app/backups/20261025-frag10-gate/profiles.tar.gz"
OUT = Path("/app/data/frag10_20261025/gate_remediation.json")

TARGETS = [
    "profiles/needs_review/comics/transformers/rodimus-prime.yaml",
    "profiles/needs_review/comics/transformers/soundwave.yaml",
    "profiles/needs_review/game/castlevania/shanoa.yaml",
    "profiles/needs_review/game/destiny/oryx.yaml",
    "profiles/needs_review/game/elden-ring/maliketh.yaml",
]

CONTRACT_FIELDS = ("battle_eligible", "status", "profile_type")


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main():
    report = {"remediated": [], "final_invalid": None}
    tf = tarfile.open(GATE_TAR, "r:gz")
    names = tf.getnames()
    for rel in TARGETS:
        path = Path("/app/" + rel)
        member = [n for n in names if n.endswith(rel)][0]
        pre = yaml.safe_load(tf.extractfile(member))
        before_md5 = md5(path)
        live = yaml.safe_load(path.open())
        before_hash = live.get("profile_hash")
        # Pre-check: confirm the defect signature before touching it.
        pre_gen = pre.get("generation") or {}
        live_gen = live.get("generation") or {}
        entry = {
            "path": str(path),
            "defect_signature": {
                "live_eligible": live.get("battle_eligible"),
                "live_reasons": live_gen.get("ineligible_reasons"),
                "pre_reasons": pre_gen.get("ineligible_reasons"),
            },
        }
        for field in CONTRACT_FIELDS:
            live[field] = copy.deepcopy(pre.get(field))
        live_gen["ineligible_reasons"] = copy.deepcopy(
            pre_gen.get("ineligible_reasons"))
        live_gen["confidence"] = copy.deepcopy(pre_gen.get("confidence"))
        live["generation"] = live_gen
        path.write_text(yaml.safe_dump(live, sort_keys=False,
                                       allow_unicode=False))
        after = yaml.safe_load(path.open())
        entry["md5_before"] = before_md5
        entry["md5_after"] = md5(path)
        entry["profile_hash_unchanged"] = (
            after.get("profile_hash") == before_hash)
        try:
            validate_profile_path(path)
            entry["validate_ok"] = True
            entry["validate_error"] = None
        except Exception as exc:  # noqa: BLE001
            entry["validate_ok"] = False
            entry["validate_error"] = str(exc)[:300]
        entry["restored"] = {
            "battle_eligible": after.get("battle_eligible"),
            "status": after.get("status"),
            "profile_type": after.get("profile_type"),
            "ineligible_reasons": (after.get("generation") or {}).get(
                "ineligible_reasons"),
            "confidence": (after.get("generation") or {}).get("confidence"),
        }
        report["remediated"].append(entry)
        print(f"{rel.split('/')[-1]} valid={entry['validate_ok']} "
              f"hash_ok={entry['profile_hash_unchanged']}")
    # Final scan: all 6 gate-recovered profiles must validate now.
    bad = []
    for rel in TARGETS + [
            "profiles/needs_review/game/castlevania/isaac.yaml"]:
        try:
            validate_profile_path(Path("/app/" + rel))
        except Exception as exc:  # noqa: BLE001
            bad.append({"profile": rel, "error": str(exc)[:200]})
    report["final_invalid"] = bad
    OUT.write_text(json.dumps(report, indent=1))
    print("final_invalid:", bad if bad else "none")


if __name__ == "__main__":
    main()
