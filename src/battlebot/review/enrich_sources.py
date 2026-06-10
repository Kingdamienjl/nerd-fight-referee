"""Inject internal source candidates into needs_review profiles."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from battlebot.profiles.aliases import resolve_alias
from battlebot.profiles.variants import split_variant_name, variant_search_queries
from battlebot.review import auto_repair, service


ALLOWED_FIELDS = [
    "attack_potency",
    "speed",
    "durability",
    "powers_and_abilities",
    "weaknesses",
    "range",
    "stamina",
    "intelligence",
]
PROVIDERS = {
    "vsbattles": {
        "authority": "high",
        "source_type": "mediawiki",
        "domain": "vsbattles.fandom.com",
        "notes": "enrich_sources_candidate",
        "allowed_fields": ALLOWED_FIELDS,
        "parser": "mediawiki_battle_stats",
        "promotion_allowed": True,
    },
    "character_stats_profiles": {
        "authority": "high",
        "source_type": "mediawiki",
        "domain": "character-stats-and-profiles.fandom.com",
        "notes": "enrich_sources_candidate",
        "allowed_fields": ALLOWED_FIELDS,
        "parser": "mediawiki_battle_stats",
        "promotion_allowed": True,
    },
}


@dataclass
class EnrichSummary:
    scanned: int = 0
    changed: int = 0
    source_candidates_added: int = 0
    skipped_existing_sources: int = 0
    top_franchises: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "changed": self.changed,
            "source_candidates_added": self.source_candidates_added,
            "skipped_existing_sources": self.skipped_existing_sources,
            "top_franchises": dict(self.top_franchises.most_common(10)),
        }


def aliases_for_profile(profile: dict[str, Any]) -> list[str]:
    aliases = profile.get("aliases") or []
    values = [str(alias) for alias in aliases if str(alias).strip()]
    match = resolve_alias(str(profile.get("name") or ""))
    if match:
        values.append(match.canonical)
    return values


def candidate_titles(profile: dict[str, Any]) -> list[str]:
    name = str(profile.get("name") or "")
    franchise = str(profile.get("franchise") or "")
    category = str(profile.get("category") or "").casefold()
    aliases = aliases_for_profile(profile)
    titles = variant_search_queries(name, franchise, aliases)
    if franchise:
        titles.append(f"{name} ({franchise})")
    titles.extend(aliases)
    normalized_franchise = franchise.casefold()
    if category == "comic" and normalized_franchise == "marvel":
        titles.extend([f"{name} (Marvel Comics)", f"{name} (Earth-616)"])
    elif category == "comic" and normalized_franchise == "dc":
        titles.extend(
            [
                f"{name} (DC Comics)",
                f"{name} (Prime Earth)",
                f"{name} (Post-Crisis)",
                f"{name} (Post-Flashpoint)",
            ]
        )
    elif category == "anime":
        titles.extend([name, f"{name} ({franchise})"])
    elif category == "game":
        titles.extend([name, f"{name} ({franchise})", f"{name} (Game)"])
    parent, variant = split_variant_name(name)
    if variant:
        titles.extend([name, f"{parent} {variant}", f"{parent} {franchise} {variant}".strip()])
    seen = set()
    unique = []
    for title in titles:
        cleaned = str(title).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique


def source_key(source: dict[str, Any]) -> tuple[str, str]:
    return (str(source.get("provider_id") or ""), str(source.get("title") or "").casefold())


def source_candidate(provider_id: str, title: str) -> dict[str, Any]:
    provider = PROVIDERS[provider_id]
    url_title = quote(title.replace(" ", "_"))
    return {
        "id": service.slugify(f"{provider_id}-{title}"),
        "provider_id": provider_id,
        "source_type": provider["source_type"],
        "title": title,
        "url": f"https://{provider['domain']}/wiki/{url_title}",
        "authority": provider["authority"],
        "notes": provider["notes"],
        "allowed_fields": list(provider["allowed_fields"]),
        "parser": provider["parser"],
        "promotion_allowed": provider["promotion_allowed"],
    }


def enrich_profile_sources(profile: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    sources = profile.setdefault("sources", [])
    existing = {source_key(source) for source in sources if isinstance(source, dict)}
    added = 0
    skipped = 0
    for title in candidate_titles(profile):
        if auto_repair.title_wrong_for_profile(profile, title):
            continue
        for provider_id in PROVIDERS:
            key = (provider_id, title.casefold())
            if key in existing:
                skipped += 1
                continue
            sources.append(source_candidate(provider_id, title))
            existing.add(key)
            added += 1
    return profile, added, skipped


def profile_paths(target: Path, max_profiles: int = 0) -> list[Path]:
    if target.is_file():
        return [target]
    paths = sorted(target.rglob("*.yaml")) if target.exists() else []
    return paths[:max_profiles] if max_profiles else paths


def enrich_path(path: Path, *, dry_run: bool = False) -> tuple[int, int]:
    profile = service.load_yaml(path)
    _, added, skipped = enrich_profile_sources(profile)
    if added and not dry_run:
        service.write_yaml(path, profile)
    return added, skipped


def enrich_target(target: Path, *, max_profiles: int = 0, dry_run: bool = False) -> EnrichSummary:
    summary = EnrichSummary()
    for path in profile_paths(target, max_profiles):
        profile = service.load_yaml(path)
        summary.scanned += 1
        summary.top_franchises.update([str(profile.get("franchise") or "unknown")])
        _, added, skipped = enrich_profile_sources(profile)
        summary.source_candidates_added += added
        summary.skipped_existing_sources += skipped
        if added:
            summary.changed += 1
            if not dry_run:
                service.write_yaml(path, profile)
    return summary


def format_summary(summary: EnrichSummary) -> str:
    data = summary.as_dict()
    return "\n".join(
        [
            f"scanned: {data['scanned']}",
            f"changed: {data['changed']}",
            f"source_candidates_added: {data['source_candidates_added']}",
            f"skipped_existing_sources: {data['skipped_existing_sources']}",
            f"top_franchises: {data['top_franchises']}",
        ]
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inject internal source candidates into needs_review profiles")
    parser.add_argument("target", type=Path)
    parser.add_argument("--max-profiles", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--csv", action="store_true", help="Print summary as one CSV row.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    summary = enrich_target(args.target, max_profiles=args.max_profiles, dry_run=args.dry_run)
    if args.csv:
        writer = csv.DictWriter(__import__("sys").stdout, fieldnames=list(summary.as_dict()))
        writer.writeheader()
        writer.writerow(summary.as_dict())
    else:
        print(format_summary(summary))


if __name__ == "__main__":
    main()
