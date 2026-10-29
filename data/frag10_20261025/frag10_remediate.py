#!/usr/bin/env python3
"""Frag-10 drain-defect remediation (runs in a one-off container).

Scans all stored profiles for the drain defect (not battle_eligible
with generation.ineligible_reasons == [] or missing), restores the
reason for each:
  - from the frag-9-gate backup tar when the backup copy carries a
    non-empty reasons list (the pre-gate state, proven VALID);
  - else the generic ["needs_review"] (the code's own default reason).
Changes NOTHING else in the file and does NOT recompute profile_hash
(frag-9 lesson: the drain owns the hash). Every file is verified with
validate_profile_path after the write, and the whole set is re-scanned
up to 3 passes in case a concurrent drain write clobbers a fix.
Writes /app/data/frag10_20261025/remediation.json.
"""
import copy
import hashlib
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.ingest.import_profiles import validate_profile_path

GATE_TAR = "/app/backups/20261025-frag9-gate/profiles.tar.gz"
OUT = Path("/app/data/frag10_20261025/remediation.json")


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def scan_invalid():
    bad = []
    for path in sorted(Path("/app/profiles").rglob("*.yaml")):
        try:
            prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
        except Exception:
            continue
        if not isinstance(prof, dict):
            continue
        if prof.get("battle_eligible"):
            continue
        reasons = (prof.get("generation") or {}).get("ineligible_reasons")
        if reasons == [] or reasons is None:
            bad.append(str(path))
    return bad


def backup_reasons(tar, tar_names, targets):
    out = {}
    for path in targets:
        rel = path[len("/app/"):] if path.startswith("/app/") else path
        member = [n for n in tar_names if n.endswith(rel)]
        if not member:
            out[path] = None
            continue
        try:
            data = tar.extractfile(member[0]).read()
            pre = yaml.safe_load(data) or {}
            reasons = (pre.get("generation") or {}).get("ineligible_reasons")
            out[path] = reasons if isinstance(reasons, list) and reasons else None
        except Exception:
            out[path] = None
    return out


def parsed_diff(before, after):
    """Keys whose values differ, as dotted paths (top level only plus
    generation.*). Returns [] when only generation.ineligible_reasons
    differs."""
    diffs = []
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            if key == "generation":
                gb, ga = before.get(key) or {}, after.get(key) or {}
                for gk in set(gb) | set(ga):
                    if gb.get(gk) != ga.get(gk):
                        diffs.append("generation." + gk)
            else:
                diffs.append(key)
    return diffs


def main():
    tar = tarfile.open(GATE_TAR, "r:gz")
    tar_names = tar.getnames()
    report = {"passes": [], "final_invalid": []}
    for pass_no in (1, 2, 3):
        targets = scan_invalid()
        entry = {"pass": pass_no, "found_invalid": len(targets), "fixed": []}
        report["passes"].append(entry)
        if not targets:
            break
        reasons_map = backup_reasons(tar, tar_names, targets)
        for path_str in targets:
            path = Path(path_str)
            before_md5 = md5(path)
            before = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
            before_snapshot = copy.deepcopy(before)
            before_hash = before.get("profile_hash")
            backup = reasons_map.get(path_str)
            source = "backup" if backup else "generic"
            new_reasons = list(backup) if backup else ["needs_review"]
            gen = before.get("generation")
            if not isinstance(gen, dict):
                gen = {}
                before["generation"] = gen
            gen["ineligible_reasons"] = new_reasons
            with path.open("w") as handle:
                yaml.safe_dump(before, handle, allow_unicode=True, sort_keys=False)
            after = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
            try:
                validate_profile_path(path)
                valid = True
                valid_error = ""
            except Exception as exc:  # noqa: BLE001 - report, don't crash
                valid = False
                valid_error = str(exc)[:200]
            entry["fixed"].append({
                "path": path_str,
                "source": source,
                "reasons": new_reasons,
                "md5_before": before_md5,
                "md5_after": md5(path),
                "profile_hash_unchanged": after.get("profile_hash") == before_hash,
                "other_diffs": parsed_diff(before_snapshot, after),
                "validate_ok": valid,
                "validate_error": valid_error,
            })
    report["final_invalid"] = scan_invalid()
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({
        "passes": [(p["pass"], p["found_invalid"], len(p["fixed"]))
                   for p in report["passes"]],
        "final_invalid": len(report["final_invalid"]),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
