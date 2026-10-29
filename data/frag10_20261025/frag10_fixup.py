#!/usr/bin/env python3
"""Frag-10 remediation fixup: revert the 6 non-profile files that the
remediation scan wrongly included (overrides, review_notes, example_character).
Restores exact pre-remediation bytes from the frag10-deploy backup, except
review_notes.yaml where any post-backup appends are preserved (generation key
surgically removed instead). Also proves raven-post-flashpoint's schema error
is pre-existing by validating its backup copy. Writes fixup.json."""
import hashlib
import json
import tarfile
from pathlib import Path

import yaml

PROFILES = Path("/app/profiles")
DEPLOY_TAR = "/app/backups/20261025-frag10-deploy/profiles.tar.gz"
GATE_TAR = "/app/backups/20261025-frag9-gate/profiles.tar.gz"
OUT = Path("/app/data/frag10_20261025/fixup.json")

NON_PROFILES = [
    "example_character.yaml",
    "review_notes.yaml",
    "overrides/character_aliases.yaml",
    "overrides/preferred_profiles.yaml",
    "overrides/source_candidates.yaml",
    "overrides/source_registry.yaml",
]


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def tar_member_bytes(tar, rel):
    with tarfile.open(tar) as t:
        names = t.getnames()
        hits = [n for n in names if n.endswith(rel)]
        if not hits:
            return None
        return t.extractfile(hits[0]).read()


def main():
    report = {"reverted": [], "raven_preexisting": None, "final_invalid": None}
    for rel in NON_PROFILES:
        path = PROFILES / rel
        backup = tar_member_bytes(DEPLOY_TAR, rel)
        cur = path.read_bytes()
        cur_data = yaml.load(cur, Loader=yaml.CSafeLoader) or {}
        entry = {"path": str(path), "had_generation_key": "generation" in cur_data,
                 "backup_found": backup is not None}
        if rel == "review_notes.yaml":
            backup_data = yaml.load(backup, Loader=yaml.CSafeLoader) or {}
            cur_nogen = {k: v for k, v in cur_data.items() if k != "generation"}
            if cur_nogen == backup_data:
                path.write_bytes(backup)
                entry["action"] = "restored_backup_bytes"
            else:
                # Post-backup appends exist: keep them, drop only my key.
                cur_data.pop("generation", None)
                path.write_text(yaml.safe_dump(cur_data, sort_keys=True,
                                               allow_unicode=True,
                                               default_flow_style=False))
                entry["action"] = "removed_generation_key_preserving_appends"
                entry["note"] = "non-generation content differs from backup"
        else:
            path.write_bytes(backup)
            entry["action"] = "restored_backup_bytes"
        entry["after_md5"] = md5(path)
        entry["backup_md5"] = hashlib.md5(backup).hexdigest()
        entry["byte_identical_to_backup"] = entry["after_md5"] == entry["backup_md5"]
        report["reverted"].append(entry)

    # Raven: validate the PRE-remediation (deploy backup) copy.
    from battlebot.ingest.import_profiles import validate_profile_path
    raven_backup = tar_member_bytes(DEPLOY_TAR,
                                    "needs_review/comic/dc/raven-post-flashpoint.yaml")
    tmp = Path("/tmp/raven_backup_copy.yaml")
    tmp.write_bytes(raven_backup)
    try:
        validate_profile_path(str(tmp))
        report["raven_preexisting"] = {"error": None}
    except Exception as exc:  # noqa: BLE001
        report["raven_preexisting"] = {"error": str(exc)[:300]}

    # Final invalid scan (profiles only: skip the 6 non-profile paths).
    invalid = []
    for p in sorted(PROFILES.rglob("*.yaml")):
        if p.relative_to(PROFILES).as_posix() in NON_PROFILES:
            continue
        try:
            data = yaml.load(p.open(), Loader=yaml.CSafeLoader) or {}
        except Exception:  # noqa: BLE001
            continue
        gen = data.get("generation") or {}
        reasons = gen.get("ineligible_reasons")
        if data.get("battle_eligible") is not True and reasons in ([], None):
            invalid.append(str(p))
    report["final_invalid"] = invalid
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
