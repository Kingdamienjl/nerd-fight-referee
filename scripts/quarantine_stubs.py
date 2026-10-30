#!/usr/bin/env python3
"""
Quarantine bootstrap stubs and malformed profiles.

1,030 profiles are bootstrap stubs (generation.bootstrap_promoted=True) with
"Unknown" stats — placeholders never actually harvested. 35 are malformed
(not dicts). Neither should be in the DB. Move them to quarantined/.

Usage:
    python3 quarantine_stubs.py [--dry-run] [--profiles-dir PATH]
"""

import argparse
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr)
    sys.exit(1)


def is_stub(profile: dict) -> bool:
    """Check if profile is a bootstrap stub."""
    gen = profile.get("generation") or {}
    if isinstance(gen, dict) and gen.get("bootstrap_promoted"):
        return True
    ap = str(profile.get("attack_potency") or "")
    return bool("provisional" in ap.lower() and "unknown" in ap.lower())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--profiles-dir", default="profiles/generated")
    args = parser.parse_args()

    profiles_dir = Path(args.profiles_dir)
    quarantine_dir = profiles_dir.parent / "quarantined" / "bootstrap_stubs"

    files = list(profiles_dir.rglob("*.yaml"))
    print(f"Scanning {len(files)} profiles...", flush=True)

    stubs = []
    malformed = []
    for path in files:
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except Exception:
            malformed.append(path)
            continue
        if not isinstance(data, dict):
            malformed.append(path)
            continue
        if is_stub(data):
            stubs.append(path)

    print(f"Found {len(stubs)} bootstrap stubs, {len(malformed)} malformed", flush=True)

    if not args.dry_run:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        for path in stubs + malformed:
            rel = path.relative_to(profiles_dir)
            dst = quarantine_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dst))
        print(f"Moved to {quarantine_dir}", flush=True)
    else:
        print("[DRY RUN] Would move to", quarantine_dir, flush=True)


if __name__ == "__main__":
    main()
