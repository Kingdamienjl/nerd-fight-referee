#!/usr/bin/env python3
"""
Retroactive readiness validation for Nerd Referee profiles.

The fragmented_ability_evidence guardrail was added in policy 2026-09-22,
but profiles generated before that were never re-validated. This script
runs assess_readiness on all profiles and reports which ones have blockers.

Usage:
    python3 revalidate_profiles.py [--profiles-dir PATH] [--quarantine]

--quarantine moves profiles with blockers to profiles/quarantined/
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr)
    sys.exit(1)


def check_fragmented_abilities(profile: dict) -> list[str]:
    """Check for unbalanced parens in abilities (the fragmented_ability_evidence blocker)."""
    blockers = []
    for item in profile.get("abilities") or []:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description") or item.get("name") or "")
        depth = 0
        malformed = False
        for char in description:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                malformed = malformed or depth < 0
        if malformed or depth:
            blockers.append("fragmented_ability_evidence")
            break
    return blockers


def check_sources(profile: dict) -> list[str]:
    """Check for contaminated sources."""
    blockers = []
    char_name = str(
        (profile.get("identity") or {}).get("canonical_name")
        or profile.get("name")
        or ""
    ).lower()
    char_words = set(re.findall(r"\w+", char_name)) - {"the", "a", "an", "of"}

    for src in profile.get("sources") or []:
        if not isinstance(src, dict):
            continue
        title = str(src.get("title") or "").lower()
        title_words = set(re.findall(r"\w+", title)) - {"the", "a", "an", "of", "canon"}
            # No word overlap - likely wrong character
        if (title and char_words and not (char_words & title_words)) and (char_name not in title and title not in char_name):
            blockers.append(f"contaminated_source:{src.get('title', '')[:40]}")
    return blockers


def validate_profile(path: Path) -> list[str]:
    """Run validation checks, return list of blockers."""
    with open(path) as f:
        profile = yaml.safe_load(f)
    if not isinstance(profile, dict):
        return ["invalid_yaml"]
    blockers = []
    blockers.extend(check_fragmented_abilities(profile))
    blockers.extend(check_sources(profile))
    return blockers


def main():
    parser = argparse.ArgumentParser(description="Re-validate all profiles")
    parser.add_argument("--profiles-dir", default="profiles/generated")
    parser.add_argument("--quarantine", action="store_true",
                        help="Move blocked profiles to quarantined/")
    args = parser.parse_args()

    profiles_dir = Path(args.profiles_dir)
    files = list(profiles_dir.rglob("*.yaml"))
    print(f"Validating {len(files)} profiles...")

    blocked = {}
    for path in files:
        try:
            blockers = validate_profile(path)
        except Exception as e:
            blockers = [f"error:{e}"]
        if blockers:
            blocked[str(path)] = blockers

    print(f"\n{len(blocked)} profiles have blockers:")
    by_blocker = {}
    for path, blockers in blocked.items():
        for b in blockers:
            by_blocker.setdefault(b, []).append(path)

    for blocker, paths in sorted(by_blocker.items()):
        print(f"  {blocker}: {len(paths)} profiles")

    if args.quarantine and blocked:
        quarantine_dir = Path("profiles/quarantined")
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        for path_str in blocked:
            src = Path(path_str)
            dst = quarantine_dir / src.name
            shutil.move(str(src), str(dst))
        print(f"\nMoved {len(blocked)} profiles to {quarantine_dir}")


if __name__ == "__main__":
    main()
