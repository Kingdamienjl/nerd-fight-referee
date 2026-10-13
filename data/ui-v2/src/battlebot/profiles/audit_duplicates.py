"""Audit likely duplicate character profiles without changing profile data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from battlebot.profiles.canonical import (
    is_fake_variant,
    is_likely_variant_name,
    normalize_text,
    row_canonical_group_key,
    row_display_name,
    row_duplicate_group_key,
    row_universe_key,
)


def profile_row_from_yaml(path: Path, root: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "name": data.get("name") or path.stem,
        "canonical_name": data.get("name") or path.stem,
        "franchise": data.get("franchise") or "unknown",
        "category": data.get("category") or "unknown",
        "status": data.get("status") or root.name,
        "battle_eligible": bool(data.get("battle_eligible")),
        "profile_path": str(path),
        "profile_json": data,
    }


def load_profile_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for root in paths:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.yaml")):
            rows.append(profile_row_from_yaml(path, root))
    return rows


def source_count(row: dict[str, Any]) -> int:
    profile_json = row.get("profile_json") if isinstance(row.get("profile_json"), dict) else {}
    sources = profile_json.get("sources") or []
    return len(sources) if isinstance(sources, list) else 0


def default_sort_key(row: dict[str, Any]) -> tuple[int, int, int, str]:
    status = str(row.get("status") or "").casefold()
    verified = 2 if status in {"verified", "approved"} else 1 if row.get("battle_eligible") else 0
    text = " ".join([row_display_name(row), str(row.get("franchise") or "")]).casefold()
    crossover_penalty = -1 if "crossover icons" in text else 0
    return (verified, source_count(row), crossover_penalty, row_display_name(row))


def is_crossover_row(row: dict[str, Any]) -> bool:
    return "crossover icons" in " ".join([row_display_name(row), str(row.get("franchise") or "")]).casefold()


def summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row_display_name(row),
        "franchise": row.get("franchise"),
        "category": row.get("category"),
        "status": row.get("status"),
        "battle_ready": bool(row.get("battle_eligible")),
        "source_count": source_count(row),
        "path": row.get("profile_path"),
    }


def display_matches_name_filter(display_name: str, name_filter: tuple[str, ...]) -> bool:
    display_tokens = tuple(normalize_text(display_name).split())
    if len(name_filter) == 1:
        return display_tokens[:1] == name_filter
    return set(name_filter) <= set(display_tokens)


def audit_duplicate_rows(rows: list[dict[str, Any]], *, names: list[str] | None = None) -> dict[str, Any]:
    name_filters = [tuple(normalize_text(name).split()) for name in names or []]
    duplicate_buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    name_buckets: dict[str, list[dict[str, Any]]] = {}
    likely_variants = []
    invalid_variants = []
    for row in rows:
        display_name = row_display_name(row)
        if name_filters and not any(display_matches_name_filter(display_name, name_filter) for name_filter in name_filters):
            continue
        if is_likely_variant_name(display_name):
            likely_variants.append(summarize_row(row))
            continue
        if is_fake_variant(row):
            invalid_variants.append(summarize_row(row))
        name_key = row_canonical_group_key(row)
        name_buckets.setdefault(name_key, []).append(row)
        duplicate_buckets.setdefault(row_duplicate_group_key(row), []).append(row)

    for name_key, name_rows in name_buckets.items():
        canonical_buckets = [
            (key, bucket)
            for key, bucket in duplicate_buckets.items()
            if key[0] == name_key and key[1] != "crossover icons"
        ]
        if not canonical_buckets:
            continue
        target_key, target_rows = sorted(canonical_buckets, key=lambda item: max(default_sort_key(row) for row in item[1]), reverse=True)[0]
        crossover_rows = [row for row in name_rows if is_crossover_row(row)]
        if crossover_rows:
            duplicate_buckets[target_key] = target_rows + [row for row in crossover_rows if row not in target_rows]
            for key in [key for key in duplicate_buckets if key[0] == name_key and key[1] == "crossover icons"]:
                duplicate_buckets.pop(key, None)

    duplicate_groups = []
    for key, group_rows in sorted(duplicate_buckets.items()):
        if len(group_rows) < 2:
            continue
        ranked = sorted(group_rows, key=default_sort_key, reverse=True)
        duplicate_groups.append(
            {
                "group": key[0],
                "universe": key[1],
                "category": key[2],
                "count": len(group_rows),
                "suggested_canonical_default": summarize_row(ranked[0]),
                "same_form_duplicates": [summarize_row(row) for row in ranked],
                "suggested_archive_or_merge_candidates": [summarize_row(row) for row in ranked[1:]],
            }
        )

    homonym_groups = []
    for name_key, name_rows in sorted(name_buckets.items()):
        universes = {(row_universe_key(row), normalize_text(str(row.get("category") or "unknown"))) for row in name_rows}
        non_crossover = {universe for universe in universes if universe[0] != "crossover icons"}
        if len(non_crossover) < 2:
            continue
        homonym_groups.append(
            {
                "group": name_key,
                "count": len(name_rows),
                "characters": [summarize_row(row) for row in sorted(name_rows, key=lambda row: (row_universe_key(row), row_display_name(row)))],
            }
        )

    return {
        "duplicate_groups": duplicate_groups,
        "homonym_groups": homonym_groups,
        "likely_variants": likely_variants,
        "invalid_variants": invalid_variants,
        "summary": {
            "groups": len(duplicate_groups),
            "homonyms": len(homonym_groups),
            "same_form_duplicates": sum(group["count"] for group in duplicate_groups),
            "likely_variants": len(likely_variants),
            "invalid_variants": len(invalid_variants),
        },
    }


def format_table(report: dict[str, Any]) -> str:
    lines = ["Duplicate groups:"]
    groups = report.get("duplicate_groups") or []
    if not groups:
        lines.append("- none")
    for group in groups:
        default = group["suggested_canonical_default"]
        lines.append(
            f"- {group['group']} [{group['universe']}/{group['category']}] ({group['count']}): default={default['name']} "
            f"[{default['franchise']}/{default['category']}]"
        )
        for candidate in group["suggested_archive_or_merge_candidates"]:
            lines.append(f"  merge/archive: {candidate['name']} [{candidate['franchise']}/{candidate['category']}]")
    homonyms = report.get("homonym_groups") or []
    lines.append("Homonym groups:")
    if not homonyms:
        lines.append("- none")
    for group in homonyms:
        lines.append(f"- {group['group']} ({group['count']}): not merge candidates")
        for character in group["characters"]:
            lines.append(f"  homonym: {character['name']} [{character['franchise']}/{character['category']}]")
    variants = report.get("likely_variants") or []
    lines.append("Likely variants:")
    if not variants:
        lines.append("- none")
    for variant in variants[:25]:
        lines.append(f"- {variant['name']} [{variant['franchise']}/{variant['category']}]")
    invalid_variants = report.get("invalid_variants") or []
    lines.append("Invalid/fake variants:")
    if not invalid_variants:
        lines.append("- none")
    for variant in invalid_variants[:25]:
        lines.append(f"- {variant['name']} [{variant['franchise']}/{variant['category']}]")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit likely duplicate character profiles")
    parser.add_argument("--generated-dir", type=Path, default=Path("profiles/generated"))
    parser.add_argument("--needs-review-dir", type=Path, default=Path("profiles/needs_review"))
    parser.add_argument("--name", action="append", default=[], help="Filter to a character name fragment")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    rows = load_profile_rows([args.generated_dir, args.needs_review_dir])
    report = audit_duplicate_rows(rows, names=args.name)
    print(json.dumps(report, indent=2) if args.json else format_table(report))


if __name__ == "__main__":
    main()
