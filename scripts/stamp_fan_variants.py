#!/usr/bin/env python3
"""
Retroactively stamp existing profiles with fan_interpretation variant.

The build_profile() fix only applies to newly harvested profiles. This script
combs all existing YAML profiles and applies the fan_interpretation variant
where the primary source is a fan wiki (VS Battles, Character Stats & Profiles).

Usage:
    python3 stamp_fan_variants.py [--dry-run] [--profiles-dir PATH]
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required", file=sys.stderr)
    sys.exit(1)

FAN_WIKI_DOMAINS = {
    "vsbattles.fandom.com": "VS Battles Wiki",
    "character-stats-and-profiles.fandom.com": "Character Stats & Profiles Wiki",
}


def get_primary_source_url(profile: dict) -> str:
    """Get the URL of the primary (first) source."""
    sources = profile.get("sources") or []
    for src in sources:
        if isinstance(src, dict) and src.get("url"):
            return str(src["url"])
    return ""


def needs_fan_stamp(profile: dict) -> str | None:
    """
    Check if profile needs fan_interpretation stamp.
    Returns the fan wiki label if needed, None otherwise.
    """
    # Skip if already has a variant_name
    variant = profile.get("variant") or {}
    if isinstance(variant, dict) and variant.get("variant_name"):
        return None

    url = get_primary_source_url(profile)
    for domain, label in FAN_WIKI_DOMAINS.items():
        if domain in url:
            return label
    return None


def stamp_profile(path: Path, dry_run: bool = False) -> bool:
    """Apply fan_interpretation variant. Returns True if changed."""
    with open(path) as f:
        profile = yaml.safe_load(f)
    if not isinstance(profile, dict):
        return False

    label = needs_fan_stamp(profile)
    if not label:
        return False

    profile["variant"] = {
        "variant_name": f"{label} interpretation",
        "variant_type": "fan_interpretation",
        "label": f"Fan-made powerscaling ({label}); not direct canon",
        "default_variant": False,
        "battle_notes": (
            f"Abilities sourced from {label}, a fan-run powerscaling wiki. "
            "Treat as fan interpretation, not canonical base form."
        ),
    }

    if not dry_run:
        with open(path, "w") as f:
            yaml.safe_dump(profile, f, allow_unicode=True, sort_keys=False)
    return True


def main():
    parser = argparse.ArgumentParser(description="Stamp fan-wiki profiles")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--profiles-dir", default="profiles/generated")
    args = parser.parse_args()

    profiles_dir = Path(args.profiles_dir)
    files = list(profiles_dir.rglob("*.yaml"))
    print(f"Scanning {len(files)} profiles...")

    stamped = 0
    for path in files:
        try:
            if stamp_profile(path, dry_run=args.dry_run):
                stamped += 1
                if args.dry_run and stamped <= 10:
                    print(f"  Would stamp: {path}")
        except Exception as e:
            print(f"ERROR {path}: {e}", file=sys.stderr)

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"\n[{mode}] Stamped {stamped} profiles with fan_interpretation variant")


if __name__ == "__main__":
    main()
