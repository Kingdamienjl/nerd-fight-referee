"""Audit likely duplicate character profiles without changing profile data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from battlebot.profiles.canonical import is_likely_variant_name, normalize_text, row_canonical_group_key, row_display_name


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


def audit_duplicate_rows(rows: list[dict[str, Any]], *, names: list[str] | None = None) -> dict[str, Any]:
    name_filters = [set(normalize_text(name).split()) for name in names or []]
    groups: dict[str, list[dict[str, Any]]] = {}
    likely_variants = []
    for row in rows:
        display_name = row_display_name(row)
        display_tokens = set(normalize_text(display_name).split())
        if name_filters and not any(name_filter <= display_tokens for name_filter in name_filters):
            continue
        if is_likely_variant_name(display_name):
            likely_variants.append(summarize_row(row))
            continue
        groups.setdefault(row_canonical_group_key(row), []).append(row)

    duplicate_groups = []
    for key, group_rows in sorted(groups.items()):
        if len(group_rows) < 2:
            continue
        ranked = sorted(group_rows, key=default_sort_key, reverse=True)
        duplicate_groups.append(
            {
                "group": key,
                "count": len(group_rows),
                "suggested_canonical_default": summarize_row(ranked[0]),
                "same_form_duplicates": [summarize_row(row) for row in ranked],
                "suggested_archive_or_merge_candidates": [summarize_row(row) for row in ranked[1:]],
            }
        )

    return {
        "duplicate_groups": duplicate_groups,
        "likely_variants": likely_variants,
        "summary": {
            "groups": len(duplicate_groups),
            "same_form_duplicates": sum(group["count"] for group in duplicate_groups),
            "likely_variants": len(likely_variants),
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
            f"- {group['group']} ({group['count']}): default={default['name']} "
            f"[{default['franchise']}/{default['category']}]"
        )
        for candidate in group["suggested_archive_or_merge_candidates"]:
            lines.append(f"  merge/archive: {candidate['name']} [{candidate['franchise']}/{candidate['category']}]")
    variants = report.get("likely_variants") or []
    lines.append("Likely variants:")
    if not variants:
        lines.append("- none")
    for variant in variants[:25]:
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
