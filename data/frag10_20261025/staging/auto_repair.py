"""Automatic source-backed repair for needs_review profiles."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import yaml

from battlebot.harvest.auto_profile_harvester import (
    FIELD_ALIASES,
    explicit_none_value,
    extract_vsbattles_fields,
    field_alias,
    list_items_from_text,
    rendered_text_from_parse as _rendered_text_from_parse,
    title_from_wiki_url,
)
from battlebot.profiles.aliases import resolve_alias
from battlebot.profiles.variants import variant_search_queries
from battlebot.review.providers import comicvine, kaggle_superherodb, mediawiki, powerlisting
from battlebot.review import service, source_registry


POWER_FIELDS = (
    "tier",
    "attack_potency",
    "speed",
    "durability",
    "range",
    "stamina",
    "intelligence",
)
COMIC_VARIANT_SUFFIXES = (
    "(Post-Crisis)",
    "(Post-Flashpoint)",
    "(Rebirth)",
    "(Prime Earth)",
    "(New Earth)",
    "(DC Comics)",
    "(Marvel Comics)",
)
DEFAULT_DEBUG_DIR = Path("data/repair_debug")
DEFAULT_SOURCE_CANDIDATES_PATH = Path("profiles/overrides/source_candidates.yaml")
IDENTITY_MATCH_THRESHOLD = 60
CONTINUITY_SUFFIX_TOKEN_SETS = (
    ("marvel", "comics"),
    ("dc", "comics"),
    ("earth", "616"),
    ("earth", "0"),
    ("prime", "earth"),
    ("new", "earth"),
    ("post", "crisis"),
    ("pre", "crisis"),
    ("post", "flashpoint"),
    ("main", "continuity"),
    ("post", "timeskip"),
    ("pre", "timeskip"),
    ("dc", "animated", "universe"),
    ("dc", "extended", "universe"),
    ("marvel", "cinematic", "universe"),
    ("new", "52"),
    ("earth", "1610"),
    ("ultimate", "universe"),
    ("golden", "age"),
    ("silver", "age"),
    ("animated", "series"),
    ("arrowverse",),
    ("rebirth",),
    ("dcau",),
    ("dceu",),
    ("mcu",),
)


@dataclass
class SourceAttempt:
    source_id: str
    url: str
    ok: bool
    note: str
    extracted_fields: list[str] = field(default_factory=list)
    normalized_page_title: str = ""
    source_type: str = ""
    revision_id: str = ""
    fetch_status: str = "not_attempted"
    http_status: int | None = None
    content_length: int = 0
    content_kind: str = "unknown"
    headings_detected: list[str] = field(default_factory=list)
    stat_labels_detected: list[str] = field(default_factory=list)
    extraction_failure_reason: str = ""
    rank: int = 0
    provider_id: str = ""
    authority: str = ""
    promotion_allowed: bool = False
    allowed_fields: list[str] = field(default_factory=list)
    field_candidates: list[dict[str, Any]] = field(default_factory=list)
    identity_match: bool = False
    identity_score: int = 0
    variant_score: int = 0
    provider_priority: int = 0
    core_field_count: int = 0
    ability_count: int = 0
    exact_name_match: bool = False
    alias_match: bool = False
    franchise_match: bool = False
    variant_match: bool = False
    continuity_mismatch: bool = False
    continuity_detail: str = ""
    duplicate_key: str = ""
    retryable: bool = False
    exception_class: str = ""
    source_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairResult:
    path: Path
    changed: bool
    promoted: bool
    repaired_fields: list[str]
    unresolved_fields: list[str]
    source_attempts: list[SourceAttempt]
    errors: list[str] = field(default_factory=list)
    needs_human_source_choice: bool = False
    candidate_sources: list[dict[str, Any]] = field(default_factory=list)
    chosen_source_id: str | None = None


def profile_paths(target: Path, max_profiles: int = 0) -> list[Path]:
    if target.is_file():
        return [target]
    paths = sorted(target.rglob("*.yaml")) if target.exists() else []
    return paths[:max_profiles] if max_profiles else paths


def missing_targets(profile: dict[str, Any]) -> list[str]:
    from battlebot.profiles.evidence_quality import has_usable_ability, usable_text

    missing = []
    for field_name in ("attack_potency", "speed", "durability"):
        if not usable_text(service.power_text(profile, field_name)):
            missing.append(field_name)
    if not has_usable_ability(profile):
        missing.append("abilities")
    if not profile.get("sources"):
        missing.append("sources")
    return missing


def parse_source_content(content: str) -> dict[str, str]:
    fields = extract_vsbattles_fields(content)
    fields.update({key: value for key, value in extract_table_like_fields(content).items() if key not in fields})
    return fields


def extract_table_like_fields(content: str) -> dict[str, str]:
    text = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", ":", content, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    fields = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        canonical = field_alias(normalize_label(label))
        value = normalize_value(value)
        if canonical and value:
            fields.setdefault(canonical, value)
    return fields


def normalize_label(value: str) -> str:
    value = re.sub(r"['*|=\[\]{}]", " ", value)
    value = value.replace("&amp;", "&")
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\s*&\s*", " & ", value)
    return re.sub(r"\s+", " ", value.strip().casefold())


def normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def detected_headings(content: str) -> list[str]:
    headings = re.findall(r"(?m)^\s*=+\s*([^=\n]+?)\s*=+\s*$", content)
    headings += re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", content, flags=re.IGNORECASE | re.DOTALL)
    return [normalize_value(re.sub(r"<[^>]+>", "", heading)) for heading in headings[:40]]


def detected_stat_labels(content: str) -> list[str]:
    labels = []
    lowered = content.casefold()
    for label, canonical in FIELD_ALIASES.items():
        if label in lowered and canonical not in labels:
            labels.append(canonical)
    return sorted(labels)


def rendered_text_from_parse(body: dict[str, Any]) -> str:
    return _rendered_text_from_parse(body)


def source_id_for(source: dict[str, Any], fallback: str) -> str:
    source_id = source.get("id")
    if source_id:
        return str(source_id)
    return service.slugify(source.get("title") or source.get("url") or fallback)


def candidate_row_from_source(source: dict[str, Any], fallback: str) -> dict[str, Any]:
    return {
        "source_id": source_id_for(source, fallback),
        "title": source.get("title") or "",
        "url": source.get("url") or "",
        "rank": source.get("rank") or 0,
        "extracted_fields": source.get("extracted_fields") or [],
        "provider_id": source.get("provider_id") or "",
        "authority": source.get("authority") or "",
        "promotion_allowed": bool(source.get("promotion_allowed", False)),
        "allowed_fields": source.get("allowed_fields") or [],
        "rejection_reason": source.get("rejection_reason") or "",
        "search_query": source.get("search_query") or "",
    }


def candidate_row_from_attempt(attempt: SourceAttempt) -> dict[str, Any]:
    return {
        "source_id": attempt.source_id,
        "url": attempt.url,
        "title": attempt.normalized_page_title,
        "rank": attempt.rank,
        "extracted_fields": attempt.extracted_fields,
        "provider_id": attempt.provider_id,
        "authority": attempt.authority,
        "promotion_allowed": attempt.promotion_allowed,
        "allowed_fields": attempt.allowed_fields,
        "rejection_reason": attempt.extraction_failure_reason,
        "identity_match": attempt.identity_match,
        "identity_score": attempt.identity_score,
        "variant_score": attempt.variant_score,
        "provider_priority": attempt.provider_priority,
        "core_field_count": attempt.core_field_count,
        "ability_count": attempt.ability_count,
        "exact_name_match": attempt.exact_name_match,
        "alias_match": attempt.alias_match,
        "franchise_match": attempt.franchise_match,
        "variant_match": attempt.variant_match,
        "continuity_mismatch": attempt.continuity_mismatch,
        "continuity_detail": attempt.continuity_detail,
        "duplicate_key": attempt.duplicate_key,
    }


def roster_titles_for_profile(profile: dict[str, Any], roster_dir: Path) -> list[str]:
    return [
        str(row.get("wiki_title") or "")
        for row in roster_source_rows(profile, roster_dir)
        if str(row.get("wiki_title") or "").strip()
    ]


def source_search_queries(profile: dict[str, Any], roster_dir: Path) -> list[str]:
    name = str(profile.get("name") or "")
    franchise = str(profile.get("franchise") or "")
    aliases = []
    alias_match = resolve_alias(name)
    if alias_match:
        aliases.append(alias_match.canonical)
    queries = variant_search_queries(name, franchise, aliases)
    queries.extend(roster_titles_for_profile(profile, roster_dir))
    seen = set()
    unique = []
    for query in queries:
        cleaned = query.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique


def title_wrong_for_profile(profile: dict[str, Any], title: str) -> str:
    lowered = title.casefold()
    franchise = str(profile.get("franchise") or "").casefold()
    category = str(profile.get("category") or "").casefold()
    if franchise == "marvel" and any(marker in lowered for marker in ("dc comics", "post-crisis", "post-flashpoint", "prime earth", "rebirth", "anime")):
        return "wrong_franchise"
    if franchise == "dc" and any(marker in lowered for marker in ("marvel comics", "earth-616", "marvel cinematic universe", "anime")):
        return "wrong_franchise"
    if category == "anime" and any(marker in lowered for marker in ("marvel comics", "dc comics", "post-crisis", "post-flashpoint", "prime earth", "rebirth")):
        return "wrong_category"
    if category == "game" and franchise not in {"marvel", "dc"} and any(marker in lowered for marker in ("marvel comics", "dc comics", "post-crisis", "post-flashpoint", "prime earth", "rebirth")):
        return "wrong_franchise"
    return ""


def rank_source_candidate(profile: dict[str, Any], source: dict[str, Any]) -> int:
    title = str(source.get("title") or "").casefold()
    name = str(profile.get("name") or "").casefold()
    franchise = str(profile.get("franchise") or "").casefold()
    score = 0
    if title == name:
        score += 40
    elif name and name in title:
        score += 25
    if franchise and franchise in title:
        score += 25
    if franchise == "marvel" and any(marker in title for marker in ("marvel comics", "earth-616")):
        score += 25
    if franchise == "dc" and any(marker in title for marker in ("dc comics", "post-crisis", "post-flashpoint", "prime earth", "rebirth")):
        score += 25
    if source.get("revision_id"):
        score += 55
    if source.get("authority") == "high":
        score += 20
    if source.get("notes") == "override_preferred_title":
        score += 40
    extracted = set(source.get("extracted_fields") or [])
    for field_name in ("attack_potency", "speed", "durability"):
        if field_name in extracted:
            score += 15
    if "powers_and_abilities" in extracted or "abilities" in extracted:
        score += 15
    if title_wrong_for_profile(profile, str(source.get("title") or "")):
        score -= 100
    if any(word in title for word in ("disambiguation", "category:", "list of")):
        score -= 60
    return score


def valid_source_candidate(profile: dict[str, Any], source: dict[str, Any]) -> bool:
    reason = title_wrong_for_profile(profile, str(source.get("title") or ""))
    if reason:
        source["rejection_reason"] = reason
        return False
    extracted = set(source.get("extracted_fields") or [])
    if "extracted_fields" in source and not {"attack_potency", "speed", "durability", "powers_and_abilities", "abilities"}.intersection(extracted):
        source["rejection_reason"] = "fetched_no_core_fields"
        return False
    return True


def mediawiki_search_candidates(
    profile: dict[str, Any],
    provider: source_registry.SourceProvider,
    titles: list[str],
    *,
    query: str,
) -> list[dict[str, Any]]:
    candidates = []
    for title in titles:
        candidate = source_registry.mediawiki_candidate_for_provider(
            provider,
            title,
            notes="provider_search_candidate",
        )
        candidate["search_query"] = query
        candidate["rank"] = rank_source_candidate(profile, candidate)
        if valid_source_candidate(profile, candidate):
            candidates.append(candidate)
    return sorted(candidates, key=lambda item: item.get("rank") or 0, reverse=True)


def profile_source_candidates(
    profile: dict[str, Any],
    roster_dir: Path,
    provider_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    providers = source_registry.enabled_providers(provider_ids)

    sources: list[dict[str, Any]] = []
    seen_source_urls: set[str] = set()

    for raw_source in profile.get("sources") or []:
        if not isinstance(raw_source, dict):
            continue

        source = annotate_source_with_provider(
            dict(raw_source),
            providers,
        )
        provider_id = str(source.get("provider_id") or "")

        # When an explicit provider list is supplied, stored sources must
        # obey it as well; previously only newly discovered candidates did.
        if provider_ids and provider_id not in providers:
            continue

        normalized_url = str(source.get("url") or "").strip().casefold()
        if normalized_url and normalized_url in seen_source_urls:
            continue

        sources.append(source)

        if normalized_url:
            seen_source_urls.add(normalized_url)

    existing_urls = {
        source.get("url")
        for source in sources
        if source.get("url")
    }
    vsbattles_enabled = "vsbattles" in providers
    for provider in providers.values():
        if provider.provider_id in {"vsbattles", "character_stats_profiles"} and provider.primary_domain:
            for query in source_search_queries(profile, roster_dir):
                for candidate in mediawiki_search_candidates(profile, provider, [query], query=query):
                    if candidate["url"] not in existing_urls:
                        sources.append(candidate)
                        existing_urls.add(candidate["url"])
    for title in preferred_titles_for_profile(profile):
        if not vsbattles_enabled:
            break
        candidate = mediawiki_candidate(profile, title, "override_preferred_title", providers=providers)
        candidate["rank"] = rank_source_candidate(profile, candidate)
        if valid_source_candidate(profile, candidate) and candidate["url"] not in existing_urls:
            sources.append(candidate)
            existing_urls.add(candidate["url"])
    for row in roster_source_rows(profile, roster_dir):
        if row.get("wiki_url") and row["wiki_url"] not in existing_urls:
            sources.append(
                {
                    "id": service.slugify(row.get("wiki_title") or row["name"]),
                    "title": row.get("wiki_title") or row["name"],
                    "url": row["wiki_url"],
                    "source_type": "mediawiki",
                    "notes": "fallback_from_roster",
                }
            )
            sources[-1] = annotate_source_with_provider(sources[-1], providers)
            existing_urls.add(row["wiki_url"])

    name = str(profile.get("name") or "")
    franchise = str(profile.get("franchise") or "")
    if name:
        titles = [name]
        alias_match = resolve_alias(name)
        if alias_match:
            titles.append(alias_match.canonical)
        if franchise:
            titles.append(f"{name} ({franchise})")
        if profile.get("category"):
            titles.append(f"{name} ({profile['category']})")
        category = str(profile.get("category") or "").casefold()
        normalized_franchise = franchise.casefold()
        if category == "comic" and normalized_franchise == "marvel":
            titles.extend([f"{name} (Marvel Comics)", f"{name} (Earth-616)"])
        if category == "comic" and normalized_franchise == "dc":
            titles.extend([f"{name} (DC Comics)", f"{name} (Prime Earth)"])
        if franchise.casefold() == "kingdom hearts":
            titles.append(f"{name} (Kingdom Hearts)")
        if name.casefold() in {"doom slayer", "doomguy"}:
            titles.extend(["Doom Slayer", "Doomguy"])
        if category == "comic" and normalized_franchise == "dc":
            titles.extend(f"{name} {suffix}" for suffix in COMIC_VARIANT_SUFFIXES)
        if vsbattles_enabled:
            for title in titles:
                candidate = mediawiki_candidate(profile, title, "fallback_title_variant", providers=providers)
                candidate["rank"] = rank_source_candidate(profile, candidate)
                if valid_source_candidate(profile, candidate) and candidate["url"] not in existing_urls:
                    sources.append(candidate)
                    existing_urls.add(candidate["url"])
        if franchise:
            fandom_host = f"{service.slugify(franchise)}.fandom.com"
            fandom_url = f"https://{fandom_host}/wiki/{quote(name.replace(' ', '_'))}"
            if fandom_url not in existing_urls:
                sources.append(
                    {
                        "id": service.slugify(f"fandom-{franchise}-{name}"),
                        "title": name,
                        "url": fandom_url,
                        "source_type": "mediawiki",
                        "notes": "fallback_fandom_slug_candidate",
                    }
                )
    for candidate in source_registry.provider_candidates(profile, providers):
        candidate["rank"] = rank_source_candidate(profile, candidate)
        if valid_source_candidate(profile, candidate) and candidate["url"] not in existing_urls:
            sources.append(candidate)
            existing_urls.add(candidate["url"])
    return sorted(sources, key=lambda item: rank_source_candidate(profile, item), reverse=True)


def annotate_source_with_provider(
    source: dict[str, Any],
    providers: dict[str, source_registry.SourceProvider],
) -> dict[str, Any]:
    provider = providers.get(str(source.get("provider_id") or ""))
    if provider is None and source.get("url"):
        provider = source_registry.provider_for_url(str(source["url"]), providers)
    if provider is not None:
        source.setdefault("provider_id", provider.provider_id)
        source.setdefault("authority", provider.authority)
        source.setdefault("promotion_allowed", provider.promotion_allowed)
        source.setdefault("allowed_fields", list(provider.allowed_fields))
        source.setdefault("parser", provider.parser)
    return source


def mediawiki_candidate(
    profile: dict[str, Any],
    title: str,
    notes: str,
    *,
    providers: dict[str, source_registry.SourceProvider] | None = None,
) -> dict[str, Any]:
    provider = (providers or source_registry.enabled_providers()).get("vsbattles")
    candidate = {
        "id": service.slugify(f"vsbattles-{title}"),
        "title": title,
        "url": f"https://vsbattles.fandom.com/wiki/{quote(title.replace(' ', '_'))}",
        "source_type": "mediawiki",
        "notes": notes,
    }
    return annotate_source_with_provider(candidate, {"vsbattles": provider} if provider else {})


def load_source_candidate_overrides(path: Path = DEFAULT_SOURCE_CANDIDATES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    candidates = data.get("source_candidates") or {}
    return candidates if isinstance(candidates, dict) else {}


def preferred_titles_for_profile(profile: dict[str, Any]) -> list[str]:
    key = service.slugify(str(profile.get("name") or ""))
    override = load_source_candidate_overrides().get(key) or {}
    titles = override.get("preferred_titles") or []
    return [str(title) for title in titles if str(title).strip()]


def roster_source_rows(profile: dict[str, Any], roster_dir: Path) -> list[dict[str, str]]:
    if not roster_dir.exists():
        return []
    name = str(profile.get("name") or "").casefold()
    franchise = str(profile.get("franchise") or "").casefold()
    rows = []
    for csv_path in sorted(roster_dir.rglob("*.csv")):
        try:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if (
                        str(row.get("name") or "").casefold() == name
                        and str(row.get("franchise") or "").casefold() == franchise
                    ):
                        rows.append({key: str(value or "") for key, value in row.items()})
        except OSError:
            continue
    return rows


async def fetch_source_fields(source: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    parser = str(source.get("parser") or "")
    if parser == "comicvine_api":
        return comicvine.missing_api_key_metadata(str(source.get("requires_api_key_env") or "COMICVINE_API_KEY"))
    if parser == "local_csv_dataset":
        root = Path(str(source.get("local_path") or "data/external/superherodb"))
        return kaggle_superherodb.load_local_fields(str(source.get("title") or ""), root)
    if parser == "superherodb_html":
        return {}, {"note": "superherodb_live_fetch_not_implemented", "fetch_status": "skipped"}
    if parser == "databasecomics_html":
        return {}, {"note": "databasecomics_live_fetch_not_implemented", "fetch_status": "skipped"}
    if parser and parser not in {"mediawiki_battle_stats", "mediawiki_ability_taxonomy", "mediawiki_power_levels"}:
        return {}, {
            "note": f"provider_parser_not_implemented: {parser}",
            "provider_id": source.get("provider_id") or "",
            "authority": source.get("authority") or "",
            "promotion_allowed": bool(source.get("promotion_allowed", False)),
            "allowed_fields": source.get("allowed_fields") or [],
        }
    url = str(source.get("url") or "")
    if not url:
        return {}, {"note": "missing_url"}
    parsed = urlparse(url)
    if "fandom.com" not in parsed.netloc and "wiki" not in parsed.path.casefold():
        return {}, {"note": "unsupported_source_url"}

    title = title_from_wiki_url(url) or source.get("title")
    if not title:
        return {}, {"note": "missing_mediawiki_title"}
    if parser == "mediawiki_ability_taxonomy":
        fields, metadata = await mediawiki.fetch_mediawiki_fields(source, powerlisting.parse_ability_taxonomy)
    else:
        fields, metadata = await mediawiki.fetch_mediawiki_fields(source, parse_source_content)
    raw_content = str(metadata.pop("raw_content", ""))
    metadata.setdefault("headings_detected", detected_headings(raw_content))
    metadata.setdefault("stat_labels_detected", detected_stat_labels(raw_content))
    metadata.setdefault("provider_id", source.get("provider_id") or "")
    metadata.setdefault("authority", source.get("authority") or "")
    metadata.setdefault("promotion_allowed", bool(source.get("promotion_allowed", False)))
    metadata.setdefault("allowed_fields", source.get("allowed_fields") or [])
    return fields, metadata


def mediawiki_search_titles_from_body(body: dict[str, Any]) -> list[str]:
    if isinstance(body.get(1), list):
        return [str(title) for title in body.get(1, [])]
    query = body.get("query") or {}
    return [str(row.get("title")) for row in query.get("search") or [] if row.get("title")]


def apply_source_metadata(profile: dict[str, Any], source: dict[str, Any], metadata: dict[str, Any]) -> str:
    sources = profile.setdefault("sources", [])
    existing_ids = {str(item.get("id")) for item in sources if item.get("id")}
    current_id = source_id_for(source, source.get("title") or "source")
    source_id = current_id if current_id in existing_ids else service.safe_unique_id(current_id, existing_ids, fallback="source")
    for item in sources:
        if item.get("id") == source_id or (item.get("url") and item.get("url") == source.get("url")):
            item.setdefault("id", source_id)
            item.update({key: value for key, value in metadata.items() if value and key != "note"})
            item.setdefault("source_type", source.get("source_type") or "mediawiki")
            if metadata.get("url"):
                # This source id has been resolved to a canonical page. Drop
                # same-id candidate stubs that were never resolved to a
                # different revision: they are alternate title spellings of
                # this same logical source, and keeping them makes one page
                # look like several conflicting sources. Entries resolved to
                # a different revision are genuine and are kept.
                resolved_revision = str(metadata.get("revision_id") or "")
                sources[:] = [
                    entry
                    for entry in sources
                    if entry is item
                    or entry.get("id") != source_id
                    or (
                        entry.get("revision_id")
                        and str(entry["revision_id"]) != resolved_revision
                    )
                ]
            return str(item["id"])
    new_source = {"id": source_id, **source}
    new_source.update({key: value for key, value in metadata.items() if value and key != "note"})
    sources.append(new_source)
    return source_id


def set_power_field(
    profile: dict[str, Any],
    field_name: str,
    value: str,
    *,
    source_id: str,
    confidence: float,
    overwrite: bool,
) -> bool:
    power_scale = profile.setdefault("power_scale", {})
    current = power_scale.get(field_name)
    if isinstance(current, dict) and current.get("text") and not overwrite:
        return False
    if current and not isinstance(current, dict) and not overwrite:
        return False
    power_scale[field_name] = {
        "text": value,
        "source_ids": [source_id],
        "confidence": confidence,
        "notes": "auto_repair source extraction",
    }
    return True


def append_auto_note(
    profile_path: Path,
    *,
    field_path: str,
    suggested_value: str,
    source_id: str,
    dry_run: bool,
    notes_path: Path,
) -> None:
    if dry_run:
        return
    service.add_review_note(
        profile_path,
        field_path=field_path,
        issue_type="auto_repair",
        note="Auto repair extracted source-backed value",
        suggested_value=suggested_value,
        source_id=source_id,
        notes_path=notes_path,
    )


def apply_extracted_fields(
    profile_path: Path,
    profile: dict[str, Any],
    fields: dict[str, str],
    *,
    source_id: str,
    confidence: float,
    overwrite: bool,
    dry_run: bool,
    notes_path: Path,
    allow_power_fields: bool = True,
) -> list[str]:
    repaired = []
    if allow_power_fields:
        for field_name in POWER_FIELDS:
            value = fields.get(field_name)
            if value and set_power_field(
                profile,
                field_name,
                value,
                source_id=source_id,
                confidence=confidence,
                overwrite=overwrite,
            ):
                repaired.append(field_name)
                append_auto_note(
                    profile_path,
                    field_path=f"power_scale.{field_name}.text",
                    suggested_value=value,
                    source_id=source_id,
                    dry_run=dry_run,
                    notes_path=notes_path,
                )

    if fields.get("powers_and_abilities") and (overwrite or not profile.get("abilities")):
        abilities = list_items_from_text(
            "powers_and_abilities",
            fields["powers_and_abilities"],
            source_ids=[source_id],
            inherited_tags=[],
            inherited_dependencies=[],
            inherited_scope_limitations=[],
        )
        if abilities:
            profile["abilities"] = abilities
            repaired.append("abilities")
            append_auto_note(
                profile_path,
                field_path="abilities",
                suggested_value=fields["powers_and_abilities"],
                source_id=source_id,
                dry_run=dry_run,
                notes_path=notes_path,
            )

    if fields.get("weaknesses") and (overwrite or not profile.get("weaknesses")):
        profile["weaknesses"] = list_items_from_text(
            "weaknesses",
            fields["weaknesses"],
            source_ids=[source_id],
            inherited_tags=[],
            inherited_dependencies=[],
            inherited_scope_limitations=[],
        )
        if profile["weaknesses"]:
            repaired.append("weaknesses")
    return repaired


def retained_repair_candidate(attempt: SourceAttempt) -> bool:
    return (
        attempt.fetch_status == "fetched"
        and attempt.identity_score >= IDENTITY_MATCH_THRESHOLD
        and attempt.identity_match
        and attempt.variant_score >= 0
        and not attempt.continuity_mismatch
    )


def attempts_with_core_fields(attempts: list[SourceAttempt]) -> list[SourceAttempt]:
    """Return identity-compatible fetched attempts that have all three core fields."""
    return [
        attempt
        for attempt in attempts
        if retained_repair_candidate(attempt)
        and attempt.core_field_count >= 3
    ]


def apply_repairs_from_available_sources(
    profile_path: Path,
    profile: dict[str, Any],
    attempts: list[SourceAttempt],
    *,
    dry_run: bool,
    notes_path: Path,
) -> tuple[list[str], list[SourceAttempt]]:
    """
    Apply repairs from all sources that have core fields extracted.
    Returns (repaired_fields, sources_used).
    """
    repaired_fields: list[str] = []
    sources_used: list[SourceAttempt] = []
    seen_source_ids: set[str] = set()

    # Try to apply repairs from sources with core fields, prioritized by quality
    candidates = sorted(
        attempts_with_core_fields(attempts),
        key=lambda a: (a.provider_priority, a.identity_score, a.core_field_count),
        reverse=True,
    )

    for attempt in candidates:
        if attempt.source_id in seen_source_ids:
            continue

        fields = attempt_field_map(attempt)
        if not fields:
            continue

        applied_source_id = apply_source_metadata(profile, attempt.source_payload, attempt.metadata)
        # Use high confidence if identity matches, moderate otherwise
        confidence = 0.75 if attempt.identity_match else 0.60
        repaired = apply_extracted_fields(
            profile_path,
            profile,
            fields,
            source_id=applied_source_id,
            confidence=confidence,
            overwrite=False,  # Don't overwrite existing valid values
            dry_run=dry_run,
            notes_path=notes_path,
            allow_power_fields=True,
        )

        if repaired:
            repaired_fields.extend(repaired)
            sources_used.append(attempt)
            seen_source_ids.add(attempt.source_id)

    return sorted(set(repaired_fields)), sources_used


def high_authority_core_attempts(attempts: list[SourceAttempt]) -> list[SourceAttempt]:
    required = {"attack_potency", "speed", "durability"}
    return [
        attempt
        for attempt in attempts
        if attempt.authority == "high"
        and attempt.promotion_allowed
        and required.issubset(set(attempt.extracted_fields))
    ]


def high_authority_core_disagreements(attempts: list[SourceAttempt]) -> list[str]:
    disagreements = []
    compatible_attempts = [
        attempt
        for attempt in attempts
        if attempt.authority == "high"
        and attempt.promotion_allowed
        and attempt.identity_match
        and attempt.variant_score >= 0
        and not attempt.continuity_mismatch
    ]
    for field_name in ("attack_potency", "speed", "durability"):
        values = {
            str(candidate.get("value") or "").strip().casefold()
            for attempt in compatible_attempts
            for candidate in attempt.field_candidates
            if candidate.get("field") == field_name and candidate.get("value")
        }
        if len(values) > 1:
            disagreements.append(field_name)
    return disagreements


def provider_priority(authority: str, provider_id: str) -> int:
    score = {"high": 100, "medium": 60, "low": 30}.get(authority, 0)
    if provider_id in {"vsbattles", "character_stats_profiles"}:
        score += 20
    return score


def normalized_identity_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", folded.casefold()).strip()


def identity_text_without_trailing_tokens(value: str, trailing: str) -> str:
    normalized = normalized_identity_text(value)
    suffix = normalized_identity_text(trailing)
    if not normalized or not suffix:
        return normalized
    suffix_tokens = suffix.split()
    tokens = normalized.split()
    if len(tokens) > len(suffix_tokens) + 1 and tokens[-len(suffix_tokens) :] == suffix_tokens:
        return " ".join(tokens[: -len(suffix_tokens)])
    return normalized


def local_identity_text(profile: dict[str, Any], value: str) -> str:
    return strip_known_continuity_suffix(
        identity_text_without_trailing_tokens(value, str(profile.get("franchise") or ""))
    )


def base_title_identity_text(value: str) -> str:
    match = re.search(r"\s*\(([^)]*)\)\s*$", value)
    if not match:
        return normalized_identity_text(value)
    suffix = tuple(normalized_identity_text(match.group(1)).split())
    if suffix in CONTINUITY_SUFFIX_TOKEN_SETS:
        return normalized_identity_text(value[: match.start()].strip())
    return normalized_identity_text(value)


def strip_known_continuity_suffix(value: str) -> str:
    tokens = normalized_identity_text(value).split()
    for suffix_tokens in sorted(CONTINUITY_SUFFIX_TOKEN_SETS, key=len, reverse=True):
        if len(tokens) > len(suffix_tokens) and tuple(tokens[-len(suffix_tokens) :]) == suffix_tokens:
            return " ".join(tokens[: -len(suffix_tokens)])
    return " ".join(tokens)


def source_suffix_identity_text(value: str, profile: dict[str, Any]) -> str:
    parts = re.split(r"\s+[-\u2013\u2014]\s+|:", re.sub(r"\s+", " ", value).strip(), maxsplit=1)
    if len(parts) != 2:
        return ""
    base, suffix = parts
    normalized_suffix = normalized_identity_text(suffix)
    franchise = normalized_identity_text(str(profile.get("franchise") or ""))
    compatible_suffixes = {f"{franchise} comics"} if franchise in {"marvel", "dc"} else set()
    compatible_suffixes.update(" ".join(tokens) for tokens in CONTINUITY_SUFFIX_TOKEN_SETS)
    if normalized_suffix in compatible_suffixes:
        return normalized_identity_text(base)
    return ""


def title_identity_bases(value: str, profile: dict[str, Any]) -> set[str]:
    bases = {
        normalized_identity_text(value),
        base_title_identity_text(value),
        strip_known_continuity_suffix(value),
    }
    source_suffix_base = source_suffix_identity_text(value, profile)
    if source_suffix_base:
        bases.add(source_suffix_base)
    return {base for base in bases if base}


def profile_identity_names(profile: dict[str, Any]) -> list[str]:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    names = [
        str(profile.get("name") or ""),
        *(str(alias) for alias in profile.get("aliases") or []),
        *(str(alias) for alias in identity.get("aliases") or []),
    ]
    alias_match = resolve_alias(str(profile.get("name") or ""))
    if alias_match:
        names.append(alias_match.canonical)
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        normalized = local_identity_text(profile, name)
        if normalized and normalized not in seen:
            unique.append(name)
            seen.add(normalized)
    return unique


def text_for_identity_matching(attempt: SourceAttempt) -> str:
    return " ".join(
        str(value or "")
        for value in (
            attempt.normalized_page_title,
            attempt.source_payload.get("title"),
            attempt.url,
        )
    )


def tokens_for_identity(value: str) -> list[str]:
    return [token for token in normalized_identity_text(value).split() if len(token) > 2]


def identity_score_for_attempt(profile: dict[str, Any], attempt: SourceAttempt) -> int:
    title = normalized_identity_text(attempt.normalized_page_title)
    title_bases = title_identity_bases(attempt.normalized_page_title, profile)
    name = local_identity_text(profile, str(profile.get("name") or ""))
    franchise = normalized_identity_text(str(profile.get("franchise") or ""))
    match_text = normalized_identity_text(text_for_identity_matching(attempt))
    if not title or not name:
        return 0
    if title_wrong_for_profile(profile, attempt.normalized_page_title):
        return 0
    normalized_names = [local_identity_text(profile, value) for value in profile_identity_names(profile)]
    alias_names = [value for value in normalized_names if value != name]
    exact_base_name_match = name in title_bases
    attempt.exact_name_match = title == name
    attempt.alias_match = any(alias in title_bases or alias in match_text for alias in alias_names)
    attempt.franchise_match = bool(franchise and franchise in match_text)
    score = 0
    if attempt.exact_name_match or exact_base_name_match:
        score += 100
    elif attempt.alias_match:
        score += 90
    else:
        tokens = tokens_for_identity(name)
        title_tokens = set(title.split())
        if tokens and set(tokens) == title_tokens:
            score += 60
    if attempt.franchise_match:
        score += 20
    return score


def variant_score_for_attempt(profile: dict[str, Any], attempt: SourceAttempt) -> int:
    title = attempt.normalized_page_title.casefold()
    franchise = str(profile.get("franchise") or "").casefold()
    category = str(profile.get("category") or "").casefold()
    score = 0
    if franchise and franchise in title:
        score += 25
    if category == "comic" and franchise == "marvel" and any(
        marker in title for marker in ("marvel comics", "earth-616")
    ):
        score += 30
    if category == "comic" and franchise == "dc" and any(
        marker in title for marker in ("dc comics", "prime earth", "rebirth", "post-crisis", "post-flashpoint")
    ):
        score += 30
    if title_wrong_for_profile(profile, attempt.normalized_page_title):
        score -= 100
    attempt.variant_match = score > 0 or category not in {"comic", "mixed"}
    return score


# ---------------------------------------------------------------------------
# Continuity validation (shared by repair and evidence recovery)
#
# A version-scoped profile must only take evidence from a page of the
# SAME continuity. Recorded source URLs routinely resolve (redirect or
# search substitution) to a flagship or screen-adaptation page of a
# different continuity -- the iteration-3 recovery sample found four
# Amanda Waller comics profiles all stamped from the DCAU page, and the
# unguarded repair path re-promoted Apollo (Post-Crisis) from the
# Post-Flashpoint page minutes after the sample reverted him. The
# check rejects only on POSITIVE evidence: the fetched page must carry
# a continuity signal (title disambiguator, origin field, categories)
# that names a different continuity than the profile's scope. A page
# with no continuity signal is never rejected on suspicion.
# ---------------------------------------------------------------------------

# (normalized marker, canonical label, kind); scanned in order, so
# specific markers precede the generic ones they contain.
_CONTINUITY_MARKERS: tuple[tuple[str, str, str], ...] = (
    ("dc animated universe", "dcau", "adaptation"),
    ("dc extended universe", "dceu", "adaptation"),
    ("marvel cinematic universe", "mcu", "adaptation"),
    ("dcau", "dcau", "adaptation"),
    ("dceu", "dceu", "adaptation"),
    ("mcu", "mcu", "adaptation"),
    ("arrowverse", "arrowverse", "adaptation"),
    ("animated series", "animated-series", "adaptation"),
    ("live action", "live-action", "adaptation"),
    ("post flashpoint", "post-flashpoint", "print"),
    ("post crisis", "post-crisis", "print"),
    ("pre crisis", "pre-crisis", "print"),
    ("prime earth", "prime-earth", "print"),
    ("new earth", "new-earth", "print"),
    ("new 52", "new-52", "print"),
    ("earth 616", "earth-616", "print"),
    ("earth 1610", "earth-1610", "print"),
    ("ultimate universe", "earth-1610", "print"),
    ("earth 0", "earth-0", "print"),
    ("rebirth", "rebirth", "print"),
    ("golden age", "golden-age", "print"),
    ("silver age", "silver-age", "print"),
    ("main continuity", "main-continuity", "print"),
    ("dc comics", "dc-comics", "print"),
    ("marvel comics", "marvel-comics", "print"),
)

# Labels naming the same continuity under different wiki conventions.
_CONTINUITY_GROUPS = (
    frozenset({"post-flashpoint", "prime-earth", "new-52", "earth-0"}),
    frozenset({"post-crisis", "new-earth"}),
)
_GENERIC_PRINT_LABELS = frozenset({"dc-comics", "marvel-comics", "main-continuity"})


def _continuity_group(label: str) -> str:
    for group in _CONTINUITY_GROUPS:
        if label in group:
            return "group:" + ",".join(sorted(group))
    return "single:" + label


def _continuity_label_in_text(text: Any) -> tuple[str | None, str | None]:
    """The first (most specific) continuity marker in one text."""
    normalized = normalized_identity_text(str(text or ""))
    if not normalized:
        return None, None
    padded = f" {normalized} "
    for marker, label, kind in _CONTINUITY_MARKERS:
        if f" {marker} " in padded:
            return label, kind
    return None, None


def _title_continuity(title: Any) -> tuple[str | None, str | None]:
    """Continuity signalled by a page title: the trailing
    parenthetical disambiguator first, then the whole title."""
    head, _base, paren = _fanon_title_parts(str(title or ""))
    if paren:
        label, kind = _continuity_label_in_text(paren)
        if label:
            return label, kind
    return _continuity_label_in_text(head)


def page_continuity(
    *,
    title: str = "",
    url: str = "",
    origin: str = "",
    categories: list[str] | tuple = (),
) -> tuple[str | None, str | None]:
    """The continuity a fetched page belongs to, from its strongest
    signals: title, origin field, then categories. The recorded URL is
    consulted only when no title was fetched (it names the candidate,
    not the resolved page)."""
    label, kind = _title_continuity(title)
    if label:
        return label, kind
    label, kind = _continuity_label_in_text(origin)
    if label:
        return label, kind
    for category in categories or ():
        label, kind = _continuity_label_in_text(category)
        if label:
            return label, kind
    if url:
        return _title_continuity(title_from_wiki_url(url))
    return None, None


def profile_continuity_scope(profile: dict[str, Any]) -> tuple[str | None, str | None, str]:
    """(label, kind, origin) of the profile's own continuity scope.

    Strongest first: the variant record's key/name, the profile name's
    trailing parenthetical, the version-scope rule's scoped key.
    (None, None, "") when the profile carries no continuity signal --
    generic profiles may take any print page (see continuity_check).
    """
    key, key_origin = _profile_scope_key(profile)
    if key:
        label, kind = _continuity_label_in_text(key)
        if label:
            return label, kind, key_origin
    label, kind = _title_continuity(str(profile.get("name") or ""))
    if label:
        return label, kind, "profile_name"
    scope = profile.get("version_scope")
    if isinstance(scope, dict) and scope.get("scoped_key"):
        label, kind = _continuity_label_in_text(scope.get("scoped_key"))
        if label:
            return label, kind, "version_scope.scoped_key"
    return None, None, ""


def _profile_is_comics(profile: dict[str, Any]) -> bool:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    category = str(profile.get("category") or identity.get("category") or "").casefold()
    return category in {"comic", "comics"}


def continuity_check(
    profile: dict[str, Any],
    *,
    page_title: str = "",
    page_url: str = "",
    origin: str = "",
    categories: list[str] | tuple = (),
) -> dict[str, Any]:
    """Shared continuity verdict for one fetched page.

    mismatch is True only on positive evidence that the page names a
    different continuity than the profile's scope. Known equivalences
    (Prime Earth == the Post-Flashpoint/New 52 continuity; New Earth
    == Post-Crisis) count as the same continuity. A generic print
    scope ("(DC Comics)"-style variants) accepts any print page but
    never a screen adaptation; an unscoped comics profile likewise
    rejects screen-adaptation pages. When the page names no
    continuity, or the profile's scope cannot be determined and the
    page is print, the verdict is no mismatch.
    """
    scope_label, scope_kind, scope_origin = profile_continuity_scope(profile)
    page_label, page_kind = page_continuity(
        title=page_title, url=page_url, origin=origin, categories=categories
    )
    result: dict[str, Any] = {
        "mismatch": False,
        "reason": "",
        "profile_scope": scope_label or "",
        "profile_scope_origin": scope_origin,
        "page_continuity": page_label or "",
        "page_kind": page_kind or "",
        "detail": "",
    }
    if not page_label:
        return result
    if scope_label:
        if scope_kind != page_kind:
            result["mismatch"] = True
        elif (
            scope_label not in _GENERIC_PRINT_LABELS
            and page_label not in _GENERIC_PRINT_LABELS
            and _continuity_group(scope_label) != _continuity_group(page_label)
        ):
            result["mismatch"] = True
    elif page_kind == "adaptation" and _profile_is_comics(profile):
        result["mismatch"] = True
    if result["mismatch"]:
        result["reason"] = "continuity_mismatch"
        result["detail"] = (
            f"page continuity '{page_label}' ({page_kind}) != "
            f"profile scope '{scope_label or 'comics'}'"
        )
    return result


def duplicate_key_for_attempt(attempt: SourceAttempt) -> str:
    host = urlparse(attempt.url).netloc.casefold()
    title = normalized_identity_text(attempt.normalized_page_title)
    revision = str(attempt.revision_id or "")
    if revision:
        return f"{host}|{title}|{revision}"
    return f"{host}|{title}"


def exception_retryable(exc: Exception) -> bool:
    text = str(exc).casefold()
    retryable_markers = (
        "timeout",
        "429",
        "too many requests",
        "5xx",
        "500",
        "502",
        "503",
        "504",
        "connection reset",
        "connection",
        "temporarily unavailable",
        "maxlag",
    )
    deterministic_types = (TypeError, AttributeError, ValueError, KeyError)
    if isinstance(exc, deterministic_types):
        return False
    return any(marker in text for marker in retryable_markers)


def sanitized_exception_message(exc: Exception) -> str:
    return re.sub(r"\s+", " ", str(exc)).strip()[:500]


def primary_sort_key(attempt: SourceAttempt) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        int(attempt.exact_name_match),
        int(attempt.alias_match),
        int(attempt.franchise_match),
        int(attempt.variant_match),
        attempt.provider_priority,
        attempt.rank,
        attempt.core_field_count,
        attempt.ability_count,
    )


def annotate_attempt_quality(profile: dict[str, Any], attempt: SourceAttempt) -> None:
    fields = set(attempt.extracted_fields)
    attempt.core_field_count = sum(
        1 for field_name in ("attack_potency", "speed", "durability") if field_name in fields
    )
    attempt.ability_count = int("powers_and_abilities" in fields or "abilities" in fields)
    attempt.identity_score = identity_score_for_attempt(profile, attempt)
    attempt.identity_match = attempt.identity_score >= IDENTITY_MATCH_THRESHOLD
    attempt.variant_score = variant_score_for_attempt(profile, attempt)
    attempt.provider_priority = provider_priority(attempt.authority, attempt.provider_id)
    attempt.duplicate_key = duplicate_key_for_attempt(attempt)
    fields_map = attempt_field_map(attempt)
    verdict = continuity_check(
        profile,
        page_title=attempt.normalized_page_title,
        origin=str(fields_map.get("origin") or ""),
    )
    attempt.continuity_mismatch = bool(verdict["mismatch"])
    attempt.continuity_detail = str(verdict["detail"] or "")


def eligible_primary_attempts(attempts: list[SourceAttempt]) -> list[SourceAttempt]:
    eligible = [
        attempt
        for attempt in attempts
        if attempt.fetch_status == "fetched"
        and attempt.identity_match
        and attempt.core_field_count >= 3
        and attempt.ability_count >= 1
        and attempt.promotion_allowed
        and attempt.variant_score >= 0
        and not attempt.continuity_mismatch
    ]
    deduped: dict[str, SourceAttempt] = {}
    for attempt in eligible:
        existing = deduped.get(attempt.duplicate_key)
        if existing is None or primary_sort_key(attempt) > primary_sort_key(existing):
            deduped[attempt.duplicate_key] = attempt
    eligible = list(deduped.values())
    eligible.sort(key=primary_sort_key, reverse=True)
    return eligible


def attempt_field_map(attempt: SourceAttempt) -> dict[str, str]:
    return {
        str(candidate.get("field")): str(candidate.get("value"))
        for candidate in attempt.field_candidates
        if candidate.get("field") and candidate.get("value")
    }


def has_independent_corroboration(primary: SourceAttempt, other_attempts: list[SourceAttempt]) -> bool:
    primary_host = urlparse(primary.url).netloc.casefold()
    for attempt in other_attempts:
        if attempt.continuity_mismatch:
            continue
        if not attempt.identity_match or attempt.core_field_count < 3 or attempt.ability_count < 1:
            continue
        if attempt.source_id == primary.source_id:
            continue
        if attempt.duplicate_key == primary.duplicate_key:
            continue
        host = urlparse(attempt.url).netloc.casefold()
        if attempt.provider_id and primary.provider_id and attempt.provider_id != primary.provider_id:
            return True
        if host and primary_host and host != primary_host:
            return True
    return False


def apply_primary_profile_state(
    profile: dict[str, Any],
    *,
    primary: SourceAttempt | None,
    corroborated: bool,
    force_promotable: bool = False,
    primary_source_id: str | None = None,
) -> None:
    from battlebot.profiles.evidence_quality import evidence_quality_blockers

    generation = profile.get("generation") if isinstance(profile.get("generation"), dict) else {}
    review = profile.get("review") if isinstance(profile.get("review"), dict) else {}
    content_blockers = evidence_quality_blockers(profile)
    if (primary or force_promotable) and not content_blockers:
        profile["profile_type"] = "auto_evidence_profile"
        profile["status"] = "verified" if corroborated else "provisional"
        profile["battle_eligible"] = True
        generation["confidence"] = max(
            float(generation.get("confidence") or 0),
            0.80 if corroborated else 0.60,
        )
        generation["ineligible_reasons"] = []
        review["readiness_state"] = "verified" if corroborated else "provisional"
        review["profile_state"] = "verified" if corroborated else "auto_evidence_profile"
        review["primary_source_id"] = primary.source_id if primary else primary_source_id
        review["secondary_disagreement_policy"] = "warning_only"
        profile["review"] = review
    else:
        profile["profile_type"] = "needs_review"
        profile["status"] = "needs_review"
        profile["battle_eligible"] = False
        review["readiness_state"] = "needs_review"
        profile["review"] = review
        # Frag-10: the old setdefault() no-opped on the empty list the
        # promotion branch had just written, so a demoted profile
        # kept ineligible_reasons=[] and failed schema validation
        # ("ineligible profile requires generation.ineligible_reasons").
        # 136 stored profiles were invalid from exactly this defect
        # (frag-10 calib1). An empty or missing list is restored to
        # the generic reason before blockers are unioned in; a
        # non-empty list is left alone.
        if not generation.get("ineligible_reasons"):
            generation["ineligible_reasons"] = ["needs_review"]
        if content_blockers:
            generation["ineligible_reasons"] = sorted(set(generation.get("ineligible_reasons") or []) | set(content_blockers))
    profile["generation"] = generation


def boost_confidence_from_cross_checks(profile: dict[str, Any], attempts: list[SourceAttempt]) -> None:
    high_values = {
        (candidate["field"], str(candidate["value"]).strip().casefold())
        for attempt in attempts
        if attempt.authority == "high"
        for candidate in attempt.field_candidates
        if candidate.get("field") in {"attack_potency", "speed", "durability"} and candidate.get("value")
    }
    if not high_values:
        return
    supported_fields = {
        str(candidate["field"])
        for attempt in attempts
        if attempt.authority in {"medium", "low"}
        for candidate in attempt.field_candidates
        if (candidate.get("field"), str(candidate.get("value") or "").strip().casefold()) in high_values
    }
    power_scale = profile.get("power_scale") or {}
    for field_name in supported_fields:
        entry = power_scale.get(field_name)
        if isinstance(entry, dict):
            entry["confidence"] = min(float(entry.get("confidence") or 0) + 0.05, 0.85)


def update_repair_metadata(
    profile: dict[str, Any],
    *,
    repaired_fields: list[str],
    unresolved_fields: list[str],
    attempts: list[SourceAttempt],
    needs_human_source_choice: bool = False,
    candidate_sources: list[dict[str, Any]] | None = None,
    chosen_source_id: str | None = None,
) -> None:
    failure_reasons = Counter(
        attempt.extraction_failure_reason or attempt.fetch_status or attempt.note
        for attempt in attempts
        if attempt.extraction_failure_reason or attempt.fetch_status or attempt.note
    )
    profile["repair"] = {
        "attempted_at": service.utc_now(),
        "repaired_fields": sorted(set(repaired_fields)),
        "unresolved_fields": unresolved_fields,
        "source_attempts": [
            {
                "source_id": attempt.source_id,
                "url": attempt.url,
                "ok": attempt.ok,
                "note": attempt.note,
                "extracted_fields": attempt.extracted_fields,
                "normalized_page_title": attempt.normalized_page_title,
                "source_type": attempt.source_type,
                "revision_id": attempt.revision_id,
                "fetch_status": attempt.fetch_status,
                "http_status": attempt.http_status,
                "content_length": attempt.content_length,
                "content_kind": attempt.content_kind,
                "headings_detected": attempt.headings_detected,
                "stat_labels_detected": attempt.stat_labels_detected,
                "extraction_failure_reason": attempt.extraction_failure_reason,
                "rank": attempt.rank,
                "provider_id": attempt.provider_id,
                "authority": attempt.authority,
                "promotion_allowed": attempt.promotion_allowed,
                "allowed_fields": attempt.allowed_fields,
                "field_candidates": attempt.field_candidates,
                "identity_match": attempt.identity_match,
                "identity_score": attempt.identity_score,
                "variant_score": attempt.variant_score,
                "provider_priority": attempt.provider_priority,
                "core_field_count": attempt.core_field_count,
                "ability_count": attempt.ability_count,
                "exact_name_match": attempt.exact_name_match,
                "alias_match": attempt.alias_match,
                "franchise_match": attempt.franchise_match,
                "variant_match": attempt.variant_match,
                "duplicate_key": attempt.duplicate_key,
                "retryable": attempt.retryable,
                "exception_class": attempt.exception_class,
            }
            for attempt in attempts
        ],
        "needs_human_source_choice": needs_human_source_choice,
        "candidate_sources": candidate_sources or [],
        "chosen_source_id": chosen_source_id,
        "failure_reasons": dict(failure_reasons.most_common()),
        "confidence": 0.75 if repaired_fields else 0.0,
    }


def rank_attempt(profile: dict[str, Any], attempt: SourceAttempt) -> int:
    return rank_source_candidate(
        profile,
        {
            "title": attempt.normalized_page_title,
            "authority": attempt.authority,
            "extracted_fields": attempt.extracted_fields,
            "rank": 10 if attempt.revision_id else 0,
        },
    )


def attempt_from_result(
    profile: dict[str, Any],
    source: dict[str, Any],
    fields: dict[str, str],
    metadata: dict[str, Any],
    *,
    ok: bool,
    note: str,
) -> SourceAttempt:
    # Scalar hygiene for the repair path: a stat value that is template
    # boilerplate, page scaffolding, an editor note, an insubstantive
    # placeholder ("Self-explanatory"), or an infobox-header dump is
    # dropped before it can be counted or merged -- the same screens
    # the recovery path applies (stat_field_rejection_reasons).
    fields = dict(fields)
    dropped_scalar: dict[str, list[str]] = {}
    for field_name in list(fields):
        if field_name in POWER_FIELDS or field_name in ("lifting_strength", "striking_strength"):
            reasons = stat_field_rejection_reasons(fields[field_name])
            if reasons:
                dropped_scalar[field_name] = reasons
                del fields[field_name]
    if dropped_scalar:
        metadata = {**metadata, "dropped_scalar_fields": dropped_scalar}
    # List-item hygiene for the repair path: the same item screens
    # the recovery path applies (placeholder + fragment + tail
    # cleaning) run on every list section before its items can be
    # counted or merged. The drain previously merged list debris the
    # recovery path had already dropped -- editor-note footers,
    # version-key labels, fragment shards (the grodd/etrigan drain
    # merges). Drops and strips are recorded on the attempt metadata
    # exactly as the recovery path records them in its tried entries.
    dropped_items: dict[str, list[dict[str, Any]]] = {}
    stripped_items: dict[str, list[dict[str, Any]]] = {}
    for field_name in list(fields):
        if field_name in _RECOVERY_SECTIONS:
            kept_text, field_dropped, field_stripped = (
                filter_list_field_items_detailed(
                    fields[field_name], section=field_name
                )
            )
            if field_dropped:
                dropped_items[field_name] = field_dropped
            if field_stripped:
                stripped_items[field_name] = field_stripped
            if kept_text:
                fields[field_name] = kept_text
            else:
                del fields[field_name]
    if dropped_items:
        metadata = {**metadata, "dropped_items": dropped_items}
    if stripped_items:
        metadata = {**metadata, "stripped_items": stripped_items}
    source_id = source_id_for(source, profile.get("name") or "source")
    authority = str(metadata.get("authority") or source.get("authority") or "")
    confidence = 0.75 if metadata.get("revision_id") else 0.5
    attempt = SourceAttempt(
        source_id,
        str(source.get("url") or metadata.get("url") or ""),
        ok,
        note,
        sorted(fields),
        normalized_page_title=str(metadata.get("title") or source.get("title") or ""),
        source_type=str(metadata.get("source_type") or source.get("source_type") or ""),
        revision_id=str(metadata.get("revision_id") or source.get("revision_id") or ""),
        fetch_status=str(metadata.get("fetch_status") or ("fetched" if ok else "failed")),
        http_status=metadata.get("http_status"),
        content_length=int(metadata.get("content_length") or 0),
        content_kind=str(metadata.get("content_kind") or "unknown"),
        headings_detected=list(metadata.get("headings_detected") or []),
        stat_labels_detected=list(metadata.get("stat_labels_detected") or []),
        extraction_failure_reason="" if fields else str(metadata.get("note") or "no_fields_extracted"),
        provider_id=str(metadata.get("provider_id") or source.get("provider_id") or ""),
        authority=str(metadata.get("authority") or source.get("authority") or ""),
        promotion_allowed=bool(metadata.get("promotion_allowed", source.get("promotion_allowed", False))),
        allowed_fields=list(metadata.get("allowed_fields") or source.get("allowed_fields") or []),
        source_payload=dict(source),
        metadata=dict(metadata),
        field_candidates=[
            {
                "field": field_name,
                "value": value,
                "source_id": source_id,
                "provider_id": str(metadata.get("provider_id") or source.get("provider_id") or ""),
                "authority": authority,
                "confidence": confidence,
            }
            for field_name, value in fields.items()
        ],
    )
    attempt.rank = rank_attempt(profile, attempt)
    annotate_attempt_quality(profile, attempt)
    return attempt


def debug_report_path(profile_path: Path, debug_dir: Path) -> Path:
    return debug_dir / f"{service.slugify(profile_path.stem)}.json"


def write_debug_report(
    profile_path: Path,
    *,
    debug_dir: Path,
    result: RepairResult,
    dry_run: bool,
) -> None:
    failure_reasons = Counter(
        attempt.extraction_failure_reason or attempt.fetch_status or attempt.note
        for attempt in result.source_attempts
        if attempt.extraction_failure_reason or attempt.fetch_status or attempt.note
    )
    payload = {
        "profile_path": str(profile_path),
        "dry_run": dry_run,
        "changed": result.changed,
        "promoted": result.promoted,
        "repaired_fields": result.repaired_fields,
        "unresolved_fields": result.unresolved_fields,
        "needs_human_source_choice": result.needs_human_source_choice,
        "candidate_sources": result.candidate_sources,
        "source_attempts": [attempt.__dict__ for attempt in result.source_attempts],
        "errors": result.errors,
        "chosen_source_id": result.chosen_source_id,
        "failure_reasons": dict(failure_reasons.most_common()),
    }
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_report_path(profile_path, debug_dir).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return


def _collapse_duplicate_source_ids(profile: dict[str, Any]) -> int:
    """Keep one recorded source per source id where variants are one source.

    enrich_sources records several title-spelling candidates that can
    slugify to the same source id (e.g. "Name Series" and
    "Name %28Series%29"). readiness groups sources by id, so two recorded
    URLs under one id read as ambiguous_source_identity forever, even
    though the variants are the same logical source. Collapse each id
    group: resolved entries (revision_id) are always kept; unresolved
    stubs whose URL matches a resolved URL are kept; other stubs are
    dropped when the group has a resolved entry. When a group is all
    unresolved stubs, keep one (preferring the parenthetical %28 wiki
    spelling). Returns the number of dropped records.
    """
    sources = profile.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        return 0
    groups: dict[str, list[int]] = {}
    for idx, entry in enumerate(sources):
        if isinstance(entry, dict) and entry.get("id"):
            groups.setdefault(str(entry["id"]), []).append(idx)
    drop: set[int] = set()
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        urls = {str(sources[i].get("url") or "") for i in idxs}
        if len(urls) < 2:
            continue
        resolved_urls = {
            str(sources[i].get("url") or "")
            for i in idxs
            if sources[i].get("revision_id")
        }
        if resolved_urls:
            for i in idxs:
                if sources[i].get("revision_id"):
                    continue
                if str(sources[i].get("url") or "") not in resolved_urls:
                    drop.add(i)
        else:
            keep = next(
                (i for i in idxs if "%28" in str(sources[i].get("url") or "")),
                idxs[0],
            )
            drop.update(i for i in idxs if i != keep)
    if drop:
        profile["sources"] = [
            entry for idx, entry in enumerate(sources) if idx not in drop
        ]
    return len(drop)


VERSION_SCOPE_RULE_ID = "repair_rule:version_scope_default_v1"
_VERSION_SCOPE_AXES = (
    "tier",
    "attack_potency",
    "speed",
    "durability",
    "range",
    "stamina",
    "intelligence",
    "lifting_strength",
    "striking_strength",
)


def _profile_scope_key(profile: dict[str, Any]) -> tuple[str | None, str]:
    """The profile's own version key, when one is recorded.

    Variant profiles record the source key they were harvested for in
    ``variant.source_key`` / ``variant.variant_name``. That is the single
    unambiguous scope for the profile's stats.
    """
    variant = profile.get("variant")
    if isinstance(variant, dict):
        for field_name in ("source_key", "variant_name"):
            value = str(variant.get(field_name) or "").strip()
            if value:
                return value, f"variant.{field_name}"
    return None, ""


def apply_version_scope_default(profile: dict[str, Any]) -> dict[str, Any]:
    """Attribute pipe-joined multi-key stat text to the profile's one key.

    Harvested power_scale texts can carry one value per source version key,
    joined with '|' in source-key order. readiness blocks those axes as
    unresolved_version_scope because the profile does not say which value
    is its own. This rule resolves the scope ONLY when it is unambiguous:

    - the profile's key comes from its variant record, or (with no variant
      record) is the first listed key form -- the primary/default key, the
      same base-form convention the fight packet builder already uses;
    - per axis, the value is taken from an explicit 'Key = value' labelled
      section when one exists (the harvester's own labelled_section rule),
      else positionally when the segment count equals the key count.

    Anything else (segment/key count mismatch, key not among the listed
    keys, empty or still-piped segment) is refused per axis and left for
    human or source-level repair. Successful scoping is recorded in
    profile['version_scope'] with the rule id and timestamp.
    """
    from battlebot.harvest.version_scope import labelled_section

    report: dict[str, Any] = {
        "rule": VERSION_SCOPE_RULE_ID,
        "fired": False,
        "key": None,
        "key_origin": "",
        "axes": {},
        "refused": [],
    }
    forms = [
        form
        for form in profile.get("forms") or []
        if isinstance(form, dict) and form.get("source_field") == "keys"
    ]
    labels = [str(form.get("name") or "").strip() for form in forms]
    labels = [label for label in labels if label]
    key, key_origin = _profile_scope_key(profile)
    if key is None:
        if labels:
            key, key_origin = labels[0], "primary_form_position"
        else:
            report["refused"].append("no_scope_key")
            return report
    report["key"] = key
    report["key_origin"] = key_origin

    power = profile.get("power_scale")
    if not isinstance(power, dict):
        report["refused"].append("no_power_scale")
        return report
    label_set = list(dict.fromkeys(labels + [key]))
    for axis in _VERSION_SCOPE_AXES:
        entry = power.get(axis)
        raw_text = entry.get("text") if isinstance(entry, dict) else entry
        if not raw_text or "|" not in str(raw_text):
            continue
        text = str(raw_text)
        chosen: str | None = None
        method = ""
        explicit = labelled_section(text, key, label_set)
        if explicit:
            chosen, method = explicit, "labelled_section"
        else:
            parts = [part.strip() for part in text.split("|")]
            if labels and len(parts) == len(labels) and key in labels:
                chosen, method = parts[labels.index(key)], "positional"
        if not chosen or not chosen.strip() or "|" in chosen:
            report["refused"].append(axis)
            continue
        if isinstance(entry, dict):
            new_entry = dict(entry)
            new_entry["text"] = chosen
            power[axis] = new_entry
        else:
            power[axis] = chosen
        report["axes"][axis] = {
            "method": method,
            "segments": len(text.split("|")),
        }
    if report["axes"]:
        report["fired"] = True
        remaining_piped = []
        for axis in _VERSION_SCOPE_AXES:
            entry = power.get(axis)
            value = entry.get("text") if isinstance(entry, dict) else entry
            if value and "|" in str(value):
                remaining_piped.append(axis)
        scope = profile.get("version_scope")
        if not isinstance(scope, dict):
            scope = {}
        scope.update(
            {
                "evidence_scoped": not remaining_piped,
                "scoped_key": key,
                "scoped_by": VERSION_SCOPE_RULE_ID,
                "scoped_at": service.utc_now(),
                "key_origin": key_origin,
                "axes": report["axes"],
                "remaining_piped_axes": remaining_piped,
            }
        )
        profile["version_scope"] = scope
    return report


async def repair_profile(
    profile_path: Path,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
    promote_if_valid: bool = False,
    move: bool = False,
    needs_review_dir: Path = service.DEFAULT_NEEDS_REVIEW_DIR,
    generated_dir: Path = service.DEFAULT_GENERATED_DIR,
    roster_dir: Path = Path("profiles/rosters"),
    notes_path: Path = service.DEFAULT_REVIEW_NOTES_PATH,
    source_timeout_seconds: float = 4.0,
    fetch_sources: bool = True,
    debug_dir: Path = DEFAULT_DEBUG_DIR,
    verbose: bool = False,
    max_source_candidates: int = 8,
    choose_source_id: str | None = None,
    provider_ids: list[str] | None = None,
) -> RepairResult:
    profile = service.load_yaml(profile_path)
    repaired_fields: list[str] = []
    attempts: list[SourceAttempt] = []
    errors: list[str] = []

    if "sources" in missing_targets(profile):
        profile.setdefault("sources", [])

    # Fast path: a profile an earlier repair pass already brought to a
    # battle-ready state (provisional/verified + battle_eligible) whose
    # approval blockers are now empty can be promoted through the normal
    # approval gate without re-fetching sources. approve_profile re-runs
    # approval_blockers and schema validation itself, so no gate is skipped.
    if (
        promote_if_valid
        and not dry_run
        and not choose_source_id
        and profile.get("battle_eligible")
        and profile.get("status") in {"provisional", "verified"}
        and not service.approval_blockers(profile)
    ):
        approval = service.approve_profile(
            profile_path,
            needs_review_dir=needs_review_dir,
            generated_dir=generated_dir,
            notes_path=notes_path,
            approved_by="auto_repair",
        )
        fast_promoted = bool(approval.get("ok"))
        if fast_promoted and move:
            profile_path.unlink(missing_ok=True)
        result = RepairResult(
            path=profile_path,
            changed=False,
            promoted=fast_promoted,
            repaired_fields=[],
            unresolved_fields=[],
            source_attempts=[],
            errors=[]
            if fast_promoted
            else [f"fast_path_approval_failed: {approval.get('error')}"],
            needs_human_source_choice=False,
            candidate_sources=[],
            chosen_source_id=choose_source_id,
        )
        write_debug_report(profile_path, debug_dir=debug_dir, result=result, dry_run=dry_run)
        if verbose:
            print(f"debug_report: {debug_report_path(profile_path, debug_dir)}")
        return result

    providers = source_registry.enabled_providers(provider_ids)
    candidates = profile_source_candidates(profile, roster_dir, provider_ids)[:max_source_candidates]
    candidate_ids = {source_id_for(source, profile_path.stem) for source in candidates}
    if choose_source_id and choose_source_id not in candidate_ids:
        error = f"choose_source_id_not_found: {choose_source_id}"
        result = RepairResult(
            path=profile_path,
            changed=False,
            promoted=False,
            repaired_fields=[],
            unresolved_fields=missing_targets(profile),
            source_attempts=[],
            errors=[error],
            candidate_sources=[candidate_row_from_source(source, profile_path.stem) for source in candidates],
            chosen_source_id=choose_source_id,
        )
        write_debug_report(profile_path, debug_dir=debug_dir, result=result, dry_run=dry_run)
        if verbose:
            print(f"debug_report: {debug_report_path(profile_path, debug_dir)}")
        return result

    if not fetch_sources:
        attempts = [
            SourceAttempt(
                source_id_for(source, profile_path.stem),
                str(source.get("url") or ""),
                False,
                "dry_run_fetch_skipped",
                normalized_page_title=str(source.get("title") or ""),
                source_type=str(source.get("source_type") or ""),
                extraction_failure_reason="dry_run_fetch_skipped",
                provider_id=str(source.get("provider_id") or ""),
                authority=str(source.get("authority") or ""),
                promotion_allowed=bool(source.get("promotion_allowed", False)),
                allowed_fields=list(source.get("allowed_fields") or []),
            )
            for source in candidates
        ]
        unresolved = missing_targets(profile)
        result = RepairResult(
            path=profile_path,
            changed=False,
            promoted=False,
            repaired_fields=[],
            unresolved_fields=unresolved,
            source_attempts=attempts,
            candidate_sources=[candidate_row_from_source(source, profile_path.stem) for source in candidates],
            chosen_source_id=choose_source_id,
        )
        write_debug_report(profile_path, debug_dir=debug_dir, result=result, dry_run=dry_run)
        if verbose:
            print(f"debug_report: {debug_report_path(profile_path, debug_dir)}")
        return result

    selected_source_fetched = False
    for source in candidates:
        source_id = source_id_for(source, profile_path.stem)
        if choose_source_id and source_id != choose_source_id:
            attempts.append(
                SourceAttempt(
                    source_id,
                    str(source.get("url") or ""),
                    False,
                    "not_selected",
                    normalized_page_title=str(source.get("title") or ""),
                    source_type=str(source.get("source_type") or ""),
                    fetch_status="not_attempted",
                    extraction_failure_reason="not_selected",
                    provider_id=str(source.get("provider_id") or ""),
                    authority=str(source.get("authority") or ""),
                    promotion_allowed=bool(source.get("promotion_allowed", False)),
                    allowed_fields=list(source.get("allowed_fields") or []),
                )
            )
            continue
        if choose_source_id and selected_source_fetched:
            attempts.append(
                SourceAttempt(
                    source_id,
                    str(source.get("url") or ""),
                    False,
                    "duplicate_selected_source_id_not_fetched",
                    normalized_page_title=str(source.get("title") or ""),
                    source_type=str(source.get("source_type") or ""),
                    fetch_status="not_attempted",
                    extraction_failure_reason="duplicate_selected_source_id_not_fetched",
                    provider_id=str(source.get("provider_id") or ""),
                    authority=str(source.get("authority") or ""),
                    promotion_allowed=bool(source.get("promotion_allowed", False)),
                    allowed_fields=list(source.get("allowed_fields") or []),
                )
            )
            continue
        if choose_source_id:
            selected_source_fetched = True
        try:
            raw_fields, metadata = await asyncio.wait_for(
                fetch_source_fields(source),
                timeout=source_timeout_seconds,
            )
        except TimeoutError:
            attempts.append(
                SourceAttempt(
                    source_id,
                    str(source.get("url") or ""),
                    False,
                    f"source_timeout_after_{source_timeout_seconds:g}s",
                    normalized_page_title=str(source.get("title") or ""),
                    source_type=str(source.get("source_type") or ""),
                    fetch_status="timeout",
                    extraction_failure_reason="timeout",
                    provider_id=str(source.get("provider_id") or ""),
                    authority=str(source.get("authority") or ""),
                    promotion_allowed=bool(source.get("promotion_allowed", False)),
                    allowed_fields=list(source.get("allowed_fields") or []),
                    retryable=True,
                    exception_class="TimeoutError",
                    source_payload=dict(source),
                )
            )
            errors.append(f"source timeout: {source.get('url')}")
            continue
        except Exception as exc:
            retryable = exception_retryable(exc)
            message = sanitized_exception_message(exc)
            attempts.append(
                SourceAttempt(
                    source_id,
                    str(source.get("url") or ""),
                    False,
                    message,
                    normalized_page_title=str(source.get("title") or ""),
                    source_type=str(source.get("source_type") or ""),
                    fetch_status="error",
                    extraction_failure_reason=message,
                    provider_id=str(source.get("provider_id") or ""),
                    authority=str(source.get("authority") or ""),
                    promotion_allowed=bool(source.get("promotion_allowed", False)),
                    allowed_fields=list(source.get("allowed_fields") or []),
                    retryable=retryable,
                    exception_class=type(exc).__name__,
                    source_payload=dict(source),
                )
            )
            errors.append(f"provider_exception:{type(exc).__name__}: {message}")
            continue
        provider = providers.get(str(source.get("provider_id") or ""))
        fields = source_registry.filter_allowed_fields(raw_fields, provider)
        metadata.setdefault("provider_id", source.get("provider_id") or "")
        metadata.setdefault("authority", source.get("authority") or "")
        metadata.setdefault("promotion_allowed", bool(source.get("promotion_allowed", False)))
        metadata.setdefault("allowed_fields", source.get("allowed_fields") or [])
        if raw_fields and not fields:
            metadata["note"] = "fields_blocked_by_provider_allowed_fields"
        attempt = attempt_from_result(
            profile,
            source,
            fields,
            metadata,
            ok=bool(fields),
            note=metadata.get("note") or ("ok" if fields else "no_fields_extracted"),
        )
        attempts.append(attempt)

    eligible_attempts = eligible_primary_attempts(attempts)
    primary = eligible_attempts[0] if eligible_attempts else None
    corroborated = has_independent_corroboration(primary, eligible_attempts[1:]) if primary else False

    # Apply repairs from primary source if available
    if primary:
        fields = attempt_field_map(primary)
        applied_source_id = apply_source_metadata(profile, primary.source_payload, primary.metadata)
        confidence = 0.80 if corroborated else 0.60
        repaired_fields.extend(
            apply_extracted_fields(
                profile_path,
                profile,
                fields,
                source_id=applied_source_id,
                confidence=confidence,
                overwrite=overwrite,
                dry_run=dry_run,
                notes_path=notes_path,
                allow_power_fields=True,
            )
        )

    # Apply repairs from any other sources with core fields
    # This ensures we extract available values even if sources aren't fully eligible
    additional_repaired, sources_used_for_repair = apply_repairs_from_available_sources(
        profile_path,
        profile,
        [attempt for attempt in attempts if attempt is not primary and attempt.source_id],
        dry_run=dry_run,
        notes_path=notes_path,
    )
    repaired_fields.extend(additional_repaired)

    # Recompute unresolved fields AFTER applying all available repairs
    unresolved = missing_targets(profile)
    needs_human_source_choice = False
    has_promotion_source = bool(primary)
    
    # Determine if profile is now promotable based on repaired state
    has_core_fields = not any(field in unresolved for field in ("attack_potency", "speed", "durability"))
    has_abilities = "abilities" not in unresolved
    has_sources = "sources" not in unresolved
    is_now_promotable = has_core_fields and has_abilities and has_sources
    
    disagreements = high_authority_core_disagreements(attempts)
    if disagreements:
        review = profile.get("review") if isinstance(profile.get("review"), dict) else {}
        warnings = list(review.get("warnings") or [])
        warnings.append(f"secondary_core_disagreement_warning: {', '.join(disagreements)}")
        review["warnings"] = sorted(set(warnings))
        profile["review"] = review
    boost_confidence_from_cross_checks(profile, attempts)
    candidate_sources = sorted(
        [
            candidate_row_from_attempt(attempt)
            for attempt in attempts
            if attempt.extracted_fields and retained_repair_candidate(attempt)
        ],
        key=lambda item: item["rank"],
        reverse=True,
    )
    if choose_source_id:
        chosen_attempt = next((attempt for attempt in attempts if attempt.source_id == choose_source_id), None)
        chosen_fields = set(chosen_attempt.extracted_fields) if chosen_attempt else set()
        required = {"attack_potency", "speed", "durability", "powers_and_abilities"}
        if not chosen_attempt:
            errors.append(f"choose_source_id_not_found: {choose_source_id}")
        elif not required.issubset(chosen_fields):
            missing = sorted(required - chosen_fields)
            errors.append(f"chosen_source_missing_required_fields: {choose_source_id}: {', '.join(missing)}")
        elif not (
            chosen_attempt.fetch_status == "fetched"
            and chosen_attempt.identity_match
            and chosen_attempt.core_field_count >= 3
            and chosen_attempt.ability_count >= 1
            and chosen_attempt.promotion_allowed
        ):
            errors.append(f"chosen_source_not_promotion_allowed: {choose_source_id}")
    
    # Apply profile state based on repair success and eligibility.
    # If we have all required fields after repairs and at least one identity-matching source,
    # promote the profile even if no previously eligible primary source existed.
    has_identity_match_source = any(
        attempt.identity_match
        for attempt in attempts
        if attempt.fetch_status == "fetched"
        and attempt.promotion_allowed
        and attempt.core_field_count >= 3
        and attempt.ability_count >= 1
        and not attempt.continuity_mismatch
    )
    force_promotable = is_now_promotable and has_identity_match_source
    has_promotion_source = has_promotion_source or force_promotable
    primary_source_id = primary.source_id if primary else (
        sources_used_for_repair[0].source_id if sources_used_for_repair else None
    )
    apply_primary_profile_state(
        profile,
        primary=primary,
        corroborated=corroborated,
        force_promotable=force_promotable,
        primary_source_id=primary_source_id,
    )

    update_repair_metadata(
        profile,
        repaired_fields=repaired_fields,
        unresolved_fields=unresolved,
        attempts=attempts,
        needs_human_source_choice=needs_human_source_choice,
        candidate_sources=candidate_sources,
        chosen_source_id=choose_source_id,
    )

    _collapse_duplicate_source_ids(profile)
    apply_version_scope_default(profile)
    changed = bool(repaired_fields)
    promoted = False
    if not dry_run:
        service.write_yaml(profile_path, profile)
        if (
            promote_if_valid
            and not needs_human_source_choice
            and has_promotion_source
            and not service.approval_blockers(profile)
        ):
            approval = service.approve_profile(
                profile_path,
                needs_review_dir=needs_review_dir,
                generated_dir=generated_dir,
                notes_path=notes_path,
                approved_by="auto_repair",
            )
            promoted = bool(approval.get("ok"))
            if promoted and move:
                profile_path.unlink(missing_ok=True)

    result = RepairResult(
        path=profile_path,
        changed=changed,
        promoted=promoted,
        repaired_fields=sorted(set(repaired_fields)),
        unresolved_fields=unresolved,
        source_attempts=attempts,
        errors=errors,
        needs_human_source_choice=needs_human_source_choice,
        candidate_sources=candidate_sources,
        chosen_source_id=choose_source_id,
    )
    write_debug_report(profile_path, debug_dir=debug_dir, result=result, dry_run=dry_run)
    if verbose:
        print(f"debug_report: {debug_report_path(profile_path, debug_dir)}")
    return result


def format_result(result: RepairResult) -> str:
    return "\n".join(
        [
            f"{result.path}",
            f"  changed: {result.changed}",
            f"  promoted: {result.promoted}",
            f"  repaired_fields: {result.repaired_fields}",
            f"  unresolved_fields: {result.unresolved_fields}",
            f"  source_attempts: {len(result.source_attempts)}",
            f"  needs_human_source_choice: {result.needs_human_source_choice}",
            f"  chosen_source_id: {result.chosen_source_id or ''}",
            f"  errors: {len(result.errors)}",
        ]
    )


def load_debug_report(profile_path: Path, debug_dir: Path) -> dict[str, Any]:
    path = debug_report_path(profile_path, debug_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def candidate_rows_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = report.get("candidate_sources") or []
    if candidates:
        return [dict(candidate) for candidate in candidates if isinstance(candidate, dict)]
    rows = []
    for attempt in report.get("source_attempts") or []:
        if not isinstance(attempt, dict):
            continue
        rows.append(
            {
                "source_id": attempt.get("source_id") or "",
                "title": attempt.get("normalized_page_title") or "",
                "url": attempt.get("url") or "",
                "rank": attempt.get("rank") or 0,
                "extracted_fields": attempt.get("extracted_fields") or [],
                "provider_id": attempt.get("provider_id") or "",
                "authority": attempt.get("authority") or "",
                "promotion_allowed": bool(attempt.get("promotion_allowed", False)),
                "allowed_fields": attempt.get("allowed_fields") or [],
            }
        )
    return rows


def format_candidate_rows(profile_path: Path, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{profile_path}\n  No source candidates found."
    lines = [str(profile_path)]
    for row in rows:
        fields = ", ".join(str(field) for field in row.get("extracted_fields") or []) or "none"
        lines.append(
            "  "
            f"{row.get('source_id') or ''} | "
            f"provider={row.get('provider_id') or 'n/a'} | "
            f"authority={row.get('authority') or 'n/a'} | "
            f"title={row.get('title') or 'n/a'} | "
            f"rank={row.get('rank') or 0} | "
            f"fields={fields} | "
            f"url={row.get('url') or 'n/a'}"
        )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto-repair needs_review profiles from sources")
    parser.add_argument("target", type=Path)
    parser.add_argument("--max-profiles", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--promote-if-valid", action="store_true")
    parser.add_argument("--move", action="store_true")
    parser.add_argument("--needs-review-dir", type=Path, default=service.DEFAULT_NEEDS_REVIEW_DIR)
    parser.add_argument("--generated-dir", type=Path, default=service.DEFAULT_GENERATED_DIR)
    parser.add_argument("--roster-dir", type=Path, default=Path("profiles/rosters"))
    parser.add_argument("--notes-path", type=Path, default=service.DEFAULT_REVIEW_NOTES_PATH)
    parser.add_argument("--source-timeout-seconds", type=float, default=4.0)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug-dir", type=Path, default=DEFAULT_DEBUG_DIR)
    parser.add_argument("--max-source-candidates", type=int, default=8)
    parser.add_argument(
        "--providers",
        help="Comma-separated provider IDs to use for candidate discovery.",
    )
    parser.add_argument(
        "--choose-source-id",
        help="Apply repair fields only from the explicitly selected source candidate.",
    )
    parser.add_argument(
        "--list-candidates",
        action="store_true",
        help="Print source candidates from the latest debug report, or plan a dry-run candidate list.",
    )
    parser.add_argument(
        "--fetch-in-dry-run",
        action="store_true",
        help="Attempt live source fetches during --dry-run instead of only planning attempts.",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    results = []
    exit_code = 0
    for path in profile_paths(args.target, args.max_profiles):
        if args.list_candidates:
            report = load_debug_report(path, args.debug_dir)
            rows = candidate_rows_from_report(report)
            if not rows:
                result = await repair_profile(
                    path,
                    dry_run=True,
                    needs_review_dir=args.needs_review_dir,
                    generated_dir=args.generated_dir,
                    roster_dir=args.roster_dir,
                    notes_path=args.notes_path,
                    source_timeout_seconds=args.source_timeout_seconds,
                    fetch_sources=args.fetch_in_dry_run,
                    debug_dir=args.debug_dir,
                    verbose=args.verbose,
                    max_source_candidates=args.max_source_candidates,
                    provider_ids=parse_provider_ids(args.providers),
                )
                rows = result.candidate_sources or [candidate_row_from_attempt(attempt) for attempt in result.source_attempts]
            print(format_candidate_rows(path, rows))
            continue

        result = await repair_profile(
            path,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            promote_if_valid=args.promote_if_valid,
            move=args.move,
            needs_review_dir=args.needs_review_dir,
            generated_dir=args.generated_dir,
            roster_dir=args.roster_dir,
            notes_path=args.notes_path,
            source_timeout_seconds=args.source_timeout_seconds,
            fetch_sources=not args.dry_run or args.fetch_in_dry_run,
            debug_dir=args.debug_dir,
            verbose=args.verbose,
            max_source_candidates=args.max_source_candidates,
            choose_source_id=args.choose_source_id,
            provider_ids=parse_provider_ids(args.providers),
        )
        results.append(result)
        print(format_result(result))
        if any(error.startswith("choose_source_id_not_found") for error in result.errors):
            exit_code = 2
    if not results and not args.list_candidates:
        print("No profiles found.")
    return exit_code


def parse_provider_ids(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Targeted evidence recovery (Fix A)
#
# Re-extracts ONLY the missing stats/abilities evidence for a profile from
# its OWN already-recorded sources, using the harvester's full fallback
# parser chain (mwparserfromhell -> wikitextparser -> rendered HTML ->
# LLM, the last step env-gated by HARVEST_LLM_FALLBACK). No new sources:
# fetching goes through the same per-source provider entry points repair
# uses, constrained to the profile's recorded source records.
#
# Every fetched page must pass the recovery guard before anything merges:
# (1) the page must be about THIS character (fanon-normalized title vs the
# profile's identity names), (2) the page must carry positive evidence of
# the profile's franchise (categories / origin field / title
# disambiguator / dedicated host; pages reached by search substitution
# need one of those strong channels), (3) real-world/non-fiction pages
# are rejected for fictional characters, (4) each recovered field is
# filtered for template boilerplate, page scaffolding, and infobox-header
# dumps, and (5) the page's continuity must match the profile's version
# scope (continuity_check, shared with the repair path). When search
# substitution fails the guard, the recorded title itself is fetched
# directly and guarded too.
# Recovered fields are scoped to the profile's version key with the same
# labelled/positional rules as harvest-time scoping, merged without
# overwriting existing usable evidence, and stamped through
# apply_primary_profile_state exactly like a normal repair. Every merge
# records provenance (source id, fetched title/URL, revision, via,
# guard channels) in the report and the review note.
# ---------------------------------------------------------------------------

_RECOVERY_AXES = (
    "tier",
    "attack_potency",
    "speed",
    "durability",
    "range",
    "stamina",
    "intelligence",
    "lifting_strength",
    "striking_strength",
)
_RECOVERY_SECTIONS = ("powers_and_abilities", "standard_equipment", "weaknesses")

_STRONG_FRANCHISE_CHANNELS = {"categories", "origin", "title_disambiguator", "dedicated_host"}
_NONFICTION_CATEGORIES = {"real", "real_world", "nonfiction", "non-fiction"}


def _recovery_key_labels(fields: dict[str, str]) -> list[str]:
    raw = re.split(
        r"(?i)\b(?:Name|Origin|Age|Gender|Classification)\s*:",
        fields.get("keys") or "",
    )[0]
    return [part.strip() for part in raw.split("|") if part.strip()]


def _recovery_scope_key(
    profile: dict[str, Any], page_labels: list[str]
) -> str | None:
    """The profile's version key for one source page, when unambiguous.

    Order: the variant record's key; an exact profile-name match among the
    page's keys; the first listed key form when it is one of the page's
    keys; the page's only key. Anything else is genuinely ambiguous.
    """
    variant_key, _origin = _profile_scope_key(profile)
    if variant_key:
        return variant_key
    folded = {label.casefold(): label for label in page_labels}
    name = str(profile.get("name") or "").strip()
    if name and name.casefold() in folded:
        return folded[name.casefold()]
    forms = [
        form
        for form in profile.get("forms") or []
        if isinstance(form, dict) and form.get("source_field") == "keys"
    ]
    form_names = [str(form.get("name") or "").strip() for form in forms]
    form_names = [label for label in form_names if label]
    if form_names and form_names[0].casefold() in folded:
        return folded[form_names[0].casefold()]
    if len(page_labels) == 1:
        return page_labels[0]
    return None


def _scope_recovery_fields(
    fields: dict[str, str],
    *,
    key: str | None,
    page_labels: list[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Scope extracted fields to the profile's key, harvest rules.

    Per field: an explicit 'Key = value' labelled section wins; else a
    positional segment when segment count equals the page key count; else
    the whole text when the page has a single key. Unresolvable fields on
    multi-key pages are dropped (unknown scope) rather than guessed.
    """
    from battlebot.harvest.version_scope import labelled_section

    if not page_labels:
        return dict(fields), {}
    labels = list(dict.fromkeys(page_labels + ([key] if key else [])))
    scoped: dict[str, str] = {}
    methods: dict[str, str] = {}
    for field_name in _RECOVERY_AXES + _RECOVERY_SECTIONS:
        text = fields.get(field_name) or ""
        if not text:
            continue
        if key:
            explicit = labelled_section(text, key, labels)
            if explicit:
                scoped[field_name] = explicit
                methods[field_name] = "labelled_section"
                continue
        parts = [part.strip() for part in text.split("|")]
        if key and len(parts) == len(page_labels) and key in page_labels:
            scoped[field_name] = parts[page_labels.index(key)]
            methods[field_name] = "positional"
        elif len(page_labels) == 1:
            scoped[field_name] = text
            methods[field_name] = "single_key"
        # else: multi-key page, field cannot be attributed -> dropped
    return scoped, methods


# ---------------------------------------------------------------------------
# Recovery guard (Fix A hardening)
# ---------------------------------------------------------------------------


def _guard_token_set(value: Any) -> set[str]:
    return set(normalized_identity_text(str(value or "")).split())


def _fanon_title_parts(title: str) -> tuple[str, str, str]:
    """Split a fetched page title into (head, base, disambiguator).

    Fanon wikis suffix user pages as 'Title/Username'; the part after the
    first '/' is the author, not the subject. A trailing parenthetical is
    the disambiguator (usually the franchise); it is stripped from the
    base used for name matching but kept as franchise evidence.
    """
    head = str(title or "").strip()
    if "/" in head:
        head = head.split("/", 1)[0].strip()
    match = re.search(r"\(([^()]*)\)\s*$", head)
    if match:
        return head, head[: match.start()].strip(), match.group(1).strip()
    return head, head, ""


def _disambiguator_candidates(paren: str) -> list[str]:
    """Disambiguator strings to test for franchise evidence.

    '(Canon, Kimetsu no Yaiba)' yields both the full text and the part
    after the Canon marker; a bare '(Canon)' yields nothing testable.
    """
    text = str(paren or "").strip()
    if not text:
        return []
    candidates = [text]
    lowered = text.casefold()
    if lowered == "canon":
        return []
    if lowered.startswith("canon,"):
        candidates.append(text.split(",", 1)[1].strip())
    elif lowered.startswith("canon "):
        candidates.append(text[len("canon "):].strip())
    return [item for item in candidates if item]


def _guard_name_match(profile: dict[str, Any], fetched_title: str) -> bool:
    """True when the fetched page is about the profile's character."""
    if title_wrong_for_profile(profile, fetched_title):
        return False
    head, base, _paren = _fanon_title_parts(fetched_title)
    bases: set[str] = set()
    for variant in {fetched_title, head, base}:
        if variant:
            bases |= title_identity_bases(variant, profile)
    names = {
        local_identity_text(profile, name)
        for name in profile_identity_names(profile)
    } - {""}
    if any(name in bases for name in names):
        return True
    base_tokens = _guard_token_set(base)
    if not base_tokens:
        return False
    return any(set(name.split()) == base_tokens for name in names)


def _franchise_token_sets(profile: dict[str, Any]) -> list[set[str]]:
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    values = [
        profile.get("franchise"),
        identity.get("franchise"),
        profile.get("series"),
        identity.get("series"),
    ]
    token_sets: list[set[str]] = []
    for value in values:
        tokens = _guard_token_set(value)
        if tokens and tokens not in token_sets:
            token_sets.append(tokens)
    return token_sets


def _tokens_cover(token_sets: list[set[str]], haystack: set[str]) -> bool:
    return any(tokens and tokens <= haystack for tokens in token_sets)


def _guard_franchise_channels(
    profile: dict[str, Any],
    *,
    fetched_title: str,
    fetched_url: str,
    fields: dict[str, str],
    categories: list[str],
    wikitext: str,
) -> list[str]:
    """Positive franchise-evidence channels present on the fetched page."""
    token_sets = _franchise_token_sets(profile)
    if not token_sets:
        return []
    channels: list[str] = []
    category_tokens: set[str] = set()
    for category in categories:
        category_tokens |= _guard_token_set(category)
    if _tokens_cover(token_sets, category_tokens):
        channels.append("categories")
    origin_tokens = _guard_token_set(fields.get("origin"))
    if origin_tokens and (
        _tokens_cover(token_sets, origin_tokens)
        or any(origin_tokens <= tokens for tokens in token_sets)
    ):
        channels.append("origin")
    _head, _base, paren = _fanon_title_parts(fetched_title)
    for candidate in _disambiguator_candidates(paren):
        candidate_tokens = _guard_token_set(candidate)
        if candidate_tokens and (
            _tokens_cover(token_sets, candidate_tokens)
            or any(candidate_tokens <= tokens for tokens in token_sets)
        ):
            channels.append("title_disambiguator")
            break
    host = urlparse(fetched_url or "").netloc.casefold()
    if host:
        host_tokens = set(re.split(r"[^a-z0-9]+", host)) - {""}
        slug = service.slugify(str(profile.get("franchise") or ""))
        if (slug and slug in host) or _tokens_cover(token_sets, host_tokens):
            channels.append("dedicated_host")
    if wikitext:
        haystack = wikitext[:6000] + wikitext[-6000:]
        if _tokens_cover(token_sets, _guard_token_set(haystack)):
            channels.append("wikitext")
    return channels


def _guard_nonfiction_hits(
    profile: dict[str, Any],
    *,
    fetched_url: str,
    fields: dict[str, str],
    categories: list[str],
    wikitext: str,
) -> list[str]:
    """Real-world subject signals; any hit rejects for fictional profiles."""
    identity = profile.get("identity") if isinstance(profile.get("identity"), dict) else {}
    category = str(profile.get("category") or identity.get("category") or "").casefold()
    if category in _NONFICTION_CATEGORIES:
        return []
    hits: list[str] = []
    host = urlparse(fetched_url or "").netloc.casefold()
    if host == "wikipedia.org" or host.endswith(".wikipedia.org"):
        hits.append("wikipedia_domain")
    category_names = {str(item or "").strip().casefold() for item in categories}
    if "real world" in category_names:
        hits.append("real_world_category")
    origin = str(fields.get("origin") or "").casefold()
    if "real world" in origin:
        hits.append("real_world_origin")
    lead = str(wikitext or "")[:1500].casefold()
    if re.search(r"\bis an?\s+(genus|species|family|subfamily|tribe|order)\s+of\b", lead):
        hits.append("taxonomy_lead")
    return hits


_BOILERPLATE_INSTRUCTION_PATTERNS = (
    r"add any explanations",
    r"using brackets,?\s+not in bold",
    r"\(in bold[;,)]",
    r"the character'?s (attack power or destructive capacity|destructive capacity|attack power|speed|durability|stamina|range|intelligence|lifting strength|striking strength)\b",
    r"current (tier|level) of the character",
    r"for characters who have (transformation|multiple|power-up)",
    r"insert (those|the following) (transformations|power-ups)",
    r"lorem ipsum",
    r"this (article|page) is a (stub|work in progress)",
    r"under construction",
)
_BOILERPLATE_MARKUP_PATTERNS = (
    r"\{\{",
    r"\}\}",
    r"\{\|",
    r"\|\}",
    r"\[\[\s*category\s*:",
    r"#tag\s*:",
    r"<nowiki",
    r"\btemplate\s*:",
    r"\d{2,4}\s*px\s*\|",
    r"\.(?:png|jpe?g|gif|webp)\s*\|",
)

# Page scaffolding inside a scalar stat value: wiki section markers and
# the fanon author's editorial furniture (the Aquaman Prime Earth
# intelligence merge: "Above Average Note: Please do not edit this page
# without permission... ==Explanations & Related Blog Posts== ...
# ==Gallery== ... ==Others== Notable Victories:"). A scalar stat is a
# value, never a page skeleton, so any of these reject it.
_SCALAR_SCAFFOLDING_PATTERNS = (
    r"==",
    r"\bnotable (?:victories|losses)\s*:",
    r"\bplease do not edit\b",
    r"\bdo not edit this page\b",
    r"\bexplanations\s*(?:&|and)\s*related blog posts\b",
)

# Whole-value placeholders that are long enough to slip past the
# length-based insubstantive check but carry no information.
_INSUBSTANTIVE_SCALAR_EXACT = frozenset({"self explanatory"})


# ---------------------------------------------------------------------------
# CSPW template stat screens (third debris generation). Sample 50f's
# gate failed on a single source -- an unfilled character-stats-
# profiles template page -- whose editorial furniture merged as
# stats:
#   (a) WIP-placeholder stats: attack_potency read "Will Finish Upon
#       Return", an editor's promise to complete the page, not a
#       value. The anchored families below cover its close cousins
#       ("to be added", "will be added", "coming soon", ...) --
#       anchored to the start of the value so a substantive sentence
#       that merely mentions pending work later is untouched.
#   (b) field-definition stats: range read "The distance the
#       character's attacks/abilities can cover." -- the template's
#       own generic definition of the field, not this character's
#       range. The patterns key on the generic third-person "the
#       character's <field concept>" phrasing (real stat values speak
#       of THIS character: "his attacks", "her range") and on
#       "how far/fast/... the character" definitional openings.
# Wiring: template_stat_reasons is called from
# boilerplate_reasons(scalar=True), so it fires everywhere scalar
# stats are screened -- the recovery field loop's axes branch (and
# its keys hygiene check) and, via stat_field_rejection_reasons, the
# repair path's attempt_from_result choke point. The item side of
# the same template family is screened with the item filters (see
# _TEMPLATE_ITEM_PATTERNS near placeholder_item_reasons).
# ---------------------------------------------------------------------------

_WIP_PLACEHOLDER_STAT_PATTERNS = (
    r"^\s*will finish\b",
    r"\bwill finish (?:upon|on|when)\b",
    r"^\s*will (?:add|update|complete|fill in)\b",
    r"^\s*(?:will be|to be) (?:added|finished|completed|filled(?: in)?|written|updated)\b",
    r"^\s*coming soon\b",
    r"^\s*not (?:yet )?(?:added|finished|completed|written|complete)\b",
    r"^\s*(?:tba|tbd)\b",
)

_FIELD_DEFINITION_STAT_PATTERNS = (
    r"\bthe character'?s (?:attacks?|abilities|powers|attack power|destructive capacity|durability|speed|stamina|range|intelligence|strength)\b",
    r"\bhow (?:far|fast|much|strong|durable)\b[^.]{0,60}\bthe character\b",
)


def template_stat_reasons(text: Any) -> list[str]:
    """CSPW template-residue checks for one scalar stat value.

    Returns wip_placeholder_stat for editor placeholders and
    field_definition_stat for the template's own definition of the
    field; an empty list means the value is a real stat.
    """
    value = str(text or "")
    if not value.strip():
        return []
    lowered = value.casefold()
    reasons: list[str] = []
    if any(
        re.search(pattern, lowered)
        for pattern in _WIP_PLACEHOLDER_STAT_PATTERNS
    ):
        reasons.append("wip_placeholder_stat")
    if any(
        re.search(pattern, lowered)
        for pattern in _FIELD_DEFINITION_STAT_PATTERNS
    ):
        reasons.append("field_definition_stat")
    return reasons


# ---------------------------------------------------------------------------
# Bare-qualifier scalars (fourth debris generation). Sample 50g's
# midnighter merges set tier to "At least" -- the qualifier half of
# a real value ("At least Small Building level (...)") whose value
# token the parser dropped. A scalar made ONLY of qualifier words
# carries no value at all, so it is debris wherever it lands.
# Wiring: bare_qualifier_reasons is called from
# boilerplate_reasons(scalar=True) -- hence the recovery axes branch
# and, via stat_field_rejection_reasons, the repair path's
# attempt_from_result choke point -- and from
# fragment_scalar_reasons for audit parity.
# ---------------------------------------------------------------------------

_BARE_QUALIFIER_TOKENS = frozenset(
    {
        "at", "least", "most", "around", "over", "under", "likely",
        "possibly", "roughly", "about", "approximately", "nearly",
        "almost", "far", "higher", "lower", "much",
    }
)


def bare_qualifier_reasons(text: Any) -> list[str]:
    """Reject a scalar stat value that is only a qualifier phrase.

    Every token must be a qualifier word and no digit may appear:
    a value token anywhere ("At least 8-C, likely higher", "At
    least Small Building level (...)") makes it a real stat.
    """
    value = str(text or "").strip()
    if not value:
        return []
    cleaned = re.sub(r"[^a-z0-9+]+", " ", value.casefold()).strip()
    if not cleaned or any(ch.isdigit() for ch in cleaned):
        return []
    tokens = cleaned.split()
    if len(tokens) <= 3 and all(
        token in _BARE_QUALIFIER_TOKENS for token in tokens
    ):
        return ["bare_qualifier"]
    return []


# ---------------------------------------------------------------------------
# Qualifier-only tier backstop (tenth debris generation, scalars). The
# frag-4 bare_qualifier screen only fires on values of <=3 qualifier
# tokens, so the gate-50m rating-stripped tiers slipped through:
# "likely higher. with swords" (arcee), "At most, possibly far
# higher" (blackarachnia), "At least, higher with the Heart of
# Darkness" (galvatron), "At most. higher with Stealth Force, even
# higher with Heavy Iron 2.0" (ironhide), "At least, likely higher,
# even higher with Beast Mode" (predaking). The source tier is "Low
# 5-B, likely higher. High 5-A with swords" -- the parser drops the
# bold-marked rating tokens ({{Low 5-B}}, {{High 5-A}}) and keeps the
# plain-text qualifiers, so the value carries qualifiers but no
# rating at all. The backstop fires when a value has >=1 qualifier
# token, NO tier-rating token (\b\d+-[A-C]\b), and -- clause by
# clause (split on , . ; | and " and ", with-tails truncated, and
# subordinate clauses stripped) -- nothing substantive remains.
# Controls that survive: "At least 8-C" (rating token), "At least
# Small Building level" ("level" is substantive), "Unknown"/"Varies"
# (no qualifier token), "8-C, higher with the Moon" (rating token).
# Version digits do NOT count as ratings ("Heavy Iron 2.0").
# Wiring: boilerplate_reasons(scalar=True) -- hence the recovery axes
# branch and, via stat_field_rejection_reasons, the repair path's
# attempt_from_result choke point -- and fragment_scalar_reasons for
# audit parity. Calibrated (frag-10 calib1): 1,654 of 5,519 stored
# tier values carry no rating token; the stored corpus is heavily
# rating-stripped, which is why the parser fix (harvester) is the
# real repair and this screen is only the backstop.
# ---------------------------------------------------------------------------

_TIER_RATING_RE = re.compile(r"\b\d+-[A-C]\b")
_TIER_QUALIFIER_TOKENS = _BARE_QUALIFIER_TOKENS | frozenset(
    {"even", "physically", "up", "to", "or"}
)


def _qualifier_only_stat(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _TIER_RATING_RE.search(text):
        return False
    toks = re.findall(r"[a-z]+", text.casefold())
    if not any(token in _TIER_QUALIFIER_TOKENS for token in toks):
        return False
    for clause in re.split(r"[,.;|]|\band\b", text.casefold()):
        clause = clause.strip()
        if not clause:
            continue
        ctoks = re.findall(r"[a-z]+(?:'[a-z]+)?", clause)
        if not ctoks:
            continue
        if ctoks[0] == "with":
            continue
        if "with" in ctoks:
            ctoks = ctoks[: ctoks.index("with")]
        stripped = _strip_subordinate_clauses(ctoks)
        if stripped and all(
            token in _TIER_QUALIFIER_TOKENS for token in stripped
        ):
            continue
        return False
    return True


# Media-filename stat screen (tenth debris generation, scalars): a
# stat value carrying bare image filenames -- devastator's range
# ("...SolarBeamRifleDevastation.png DrillMisslesDevastation.jpg
# DrillsDevastation.jpg", gate 50m). Citation links legitimately
# contain ".jpg" inside their URLs, so URLs are stripped before the
# filename test; a bare "Name.png" token with no URL around it is
# gallery residue, not a stat. Calibrated (frag-10 calib1): 110 raw
# stat values match a naive extension test, nearly all of them URL
# citations that the strip-then-test rule spares.
_MEDIA_FILENAME_RE = re.compile(
    r"\b[\w\-.]+\.(?:png|jpe?g|gif|webp|svg|bmp|tiff)\b", re.I
)
_MEDIA_URL_RE = re.compile(r"https?://[^\s\]\)]+")


def _media_filename_value(value: str) -> bool:
    stripped = _MEDIA_URL_RE.sub("", str(value or ""))
    return bool(_MEDIA_FILENAME_RE.search(stripped))


def boilerplate_reasons(text: Any, *, scalar: bool) -> list[str]:
    """Template-residue checks for one recovered field's text.

    Instruction patterns (the source wiki's unfilled profile template)
    apply to every field; markup-residue and substantiveness checks
    apply to scalar stat fields and the keys field, whose values must be
    prose/values, not template fragments. Returns reason strings; an
    empty list means the text is clean.
    """
    value = str(text or "")
    if not value.strip():
        return []
    lowered = value.casefold()
    reasons: list[str] = []
    if any(re.search(pattern, lowered) for pattern in _BOILERPLATE_INSTRUCTION_PATTERNS):
        reasons.append("template_instruction")
    if scalar:
        if any(re.search(pattern, lowered) for pattern in _BOILERPLATE_MARKUP_PATTERNS):
            reasons.append("markup_residue")
        if any(re.search(pattern, lowered) for pattern in _SCALAR_SCAFFOLDING_PATTERNS):
            reasons.append("page_scaffolding")
        for reason in template_stat_reasons(value):
            if reason not in reasons:
                reasons.append(reason)
        for reason in bare_qualifier_reasons(value):
            if reason not in reasons:
                reasons.append(reason)
        if _qualifier_only_stat(value):
            reasons.append("qualifier_only_stat")
        if _media_filename_value(value):
            reasons.append("media_fragment")
        cleaned = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
        if len(cleaned) < 8 or cleaned in _INSUBSTANTIVE_SCALAR_EXACT:
            reasons.append("insubstantive")
    return reasons



_PLACEHOLDER_ITEM_PATTERNS = (
    r"a list of the character'?s\b",
    r"\blist of (?:the character'?s|their|his|her|its) (?:general )?(?:abilities|powers|skills|techniques|feats)\b",
    r"\bplease (?:add|fill|expand|complete|update|edit|insert)\b",
    r"\bto be (?:added|filled in|completed|written|expanded)\b",
    r"\badd (?:links|any|more|the following|a description)\b",
    r"\beditor'?s note\b",
    r"\bthis (?:section|list|page|article) is (?:incomplete|empty|a stub|under construction)\b",
    r"^\s*(?:tba|tbd|n/?a|none(?:\s+notable)?|unknown)\s*[.!]?\s*$",
)

# Page scaffolding that surfaces as a whole list item when a section's
# raw text is itemized: wiki section markers and the VS Battles
# victories/losses record headers (the Aladdin sample-2 escape, whose
# sole weakness item was "None Notable == Others == Notable Victories:
# Notable Losses:"). Prose that merely mentions victories or losses
# does not carry the colon form and is not matched.
_SCAFFOLDING_ITEM_PATTERNS = (
    r"==",
    r"\bnotable (?:victories|losses)\s*:",
)


# CSPW template items (the item side of the third debris generation):
# the source template's own instructions and its bare "<stat> feats"
# section labels, itemized as if they were the character's weaknesses
# -- the harley-quinn-post-flashpoint sample-50f merge: "Self-
# explanatory Feats: List all of the character's amazing feats.
# Strength feats", plus standalone "speed feats" / "durability feats"
# items. A substantive item that merely MENTIONS feats does not
# match: the instruction patterns key on the template's imperative
# phrasing, and the label check requires the whole item to be just a
# stat label plus "feats".
_TEMPLATE_ITEM_PATTERNS = (
    r"\blist all of (?:the character'?s|their|his|her|its)\b",
    r"^\s*self[-\s]?explanatory\b",
    r"\bfeats\s*:\s*list\b",
)

_FEATS_LABEL_STATS = frozenset(
    {
        "attack potency", "lifting strength", "striking strength",
        "combat speed", "travel speed", "attack speed",
        "energy projection", "strength", "speed", "durability",
        "stamina", "intelligence", "attack", "defense", "defence",
        "offense", "offence", "range", "combat", "skill", "reaction",
        "magic", "hax",
    }
)


def _feats_label_item(lowered: str) -> bool:
    """True when the whole item is a bare "<stat> feats" label."""
    text = lowered.strip().rstrip(".!").strip()
    if not text.endswith("feats"):
        return False
    head = text[: -len("feats")].strip()
    if head in _FEATS_LABEL_STATS:
        return True
    # A bare two-token "<word> feats" item is a section label,
    # never a substantive entry.
    tokens = head.split()
    return len(tokens) == 1 and tokens[0].isalpha()


def _explicit_none_item(value: str, lowered: str) -> bool:
    """A list piece that is itself an explicit-none statement.

    Whole-value statements ("None notable") plus the short-tail
    forms the corpus stores as items ("None notable as of Season 2",
    "None Notable (Has never displayed a weakness)"): a none head
    with at most a few words of tail is still the statement that
    there is nothing to list -- it is never a weakness.
    """
    if explicit_none_value(value):
        return True
    if re.match(r"[\s'*]*none[-\s]+(?:notable|known)\b", lowered):
        return _fragment_word_count(lowered) <= 8
    return False


def placeholder_item_reasons(item: Any) -> list[str]:
    """Per-item placeholder checks for one recovered list entry.

    Section-level checks cannot see a single template-instruction item
    hiding in a list -- the Nobara failure, where a fanon placeholder
    sentence ("A list of the character's general abilities (Please add
    links...)") merged as the profile's sole ability. Returns reason
    strings; empty means the item is substantive.
    """
    value = str(item or "")
    if not value.strip():
        return ["empty_item"]
    lowered = value.casefold()
    reasons: list[str] = []
    if _explicit_none_item(value, lowered):
        reasons.append("explicit_none")
    if any(re.search(pattern, lowered) for pattern in _PLACEHOLDER_ITEM_PATTERNS):
        reasons.append("placeholder_instruction")
    if any(re.search(pattern, lowered) for pattern in _BOILERPLATE_INSTRUCTION_PATTERNS):
        reasons.append("template_instruction")
    if any(re.search(pattern, lowered) for pattern in _TEMPLATE_ITEM_PATTERNS):
        if "template_instruction" not in reasons:
            reasons.append("template_instruction")
    if _feats_label_item(lowered):
        reasons.append("feats_label")
    for reason in editorial_item_reasons(value):
        if reason not in reasons:
            reasons.append(reason)
    if any(re.search(pattern, lowered) for pattern in _SCAFFOLDING_ITEM_PATTERNS):
        reasons.append("page_scaffolding")
    if any(re.search(pattern, lowered) for pattern in _BOILERPLATE_MARKUP_PATTERNS):
        reasons.append("markup_residue")
    if re.search(r"\bfile\s*:", lowered) or re.search(
        r"\.(?:png|jpe?g|gif|webp)\b", lowered
    ):
        reasons.append("media_fragment")
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    if len(cleaned) < 3:
        reasons.append("insubstantive")
    return reasons


def filter_list_field_items(
    text: Any, *, section: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Item-filter one recovered list section (abilities/weaknesses/...).

    Splits exactly the way list_items_from_text will, evaluates every
    item, and returns (kept_text, dropped): kept_text holds only the
    substantive items, dropped records each removed item with its
    reasons. kept_text is empty when nothing substantive survives --
    the field then recovers nothing. Every item passes the placeholder
    screen AND the fragment screen (parser splitting debris); `section`
    is the recovery field name, forwarded to the fragment screen for
    its weaknesses-only shard rule. Editor-note / version-key tails
    are stripped before screening (see clean_item_tails); use
    filter_list_field_items_detailed when the strip records matter.
    """
    kept, dropped, _stripped = filter_list_field_items_detailed(
        text, section=section
    )
    return kept, dropped


def filter_list_field_items_detailed(
    text: Any, *, section: str | None = None
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """filter_list_field_items plus strip provenance.

    Returns (kept_text, dropped, stripped): stripped records each
    item whose editor-note / version-key tail was removed but whose
    substantive clause survived, as {"item", "kept", "reasons"}.
    An item that is ONLY a tail is dropped, with the tail reasons.
    """
    from battlebot.harvest.auto_profile_harvester import (
        split_listish,
        unpack_mediawiki_templates,
    )

    raw = str(text or "")
    if not raw.strip():
        return "", [], []
    pieces = split_listish(unpack_mediawiki_templates(raw))
    if not pieces:
        # Unbalanced or tabber/template residue: nothing itemizable.
        return "", [{"item": raw[:120], "reasons": ["unparseable_list"]}], []
    kept: list[str] = []
    dropped: list[dict[str, Any]] = []
    stripped: list[dict[str, Any]] = []
    for piece in pieces:
        cleaned, tail_reasons = clean_item_tails(piece)
        if not cleaned:
            dropped.append(
                {"item": piece[:120], "reasons": tail_reasons or ["empty_item"]}
            )
            continue
        reasons = placeholder_item_reasons(cleaned)
        for reason in fragment_item_reasons(cleaned, section=section):
            if reason not in reasons:
                reasons.append(reason)
        if reasons:
            dropped.append({"item": piece[:120], "reasons": reasons})
        else:
            kept.append(cleaned)
            if tail_reasons:
                stripped.append(
                    {
                        "item": piece[:120],
                        "kept": cleaned[:120],
                        "reasons": tail_reasons,
                    }
                )
    return ", ".join(kept), dropped, stripped


_INFOBOX_HEADER_KEYS = frozenset(
    {
        "name", "origin", "age", "gender", "classification", "alias",
        "aliases", "occupation", "affiliation", "affiliations", "status",
        "species", "race", "height", "weight", "hair", "hair color",
        "eye color", "eyes", "birthday", "birthplace", "blood type",
        "relatives", "family", "first appearance", "debut", "alignment",
        "kanji", "romaji", "voice actor", "portrayed by",
    }
)


def infobox_header_reasons(text: Any) -> list[str]:
    """Reject a scalar stat value that is really the page's infobox header.

    A header dump is a run of Key: value pairs (Name:/Origin:/Gender:/
    Age:/...) in ANY separator shape -- pipes, semicolons, newlines
    (the Kamui / The Captain tier failure) or comma/space runs (the
    Sailor Galaxia sample-2 escape: "Key: Sailor Galaxia Name: Galaxia,
    ... Origin: Pretty Soldier Sailor Moon Gender:..."). So count
    distinct header keys wherever "Key:"/"Key =" appears in the text,
    regardless of what separates the pairs. A leading "Key:" segment --
    the infobox's own key row leaking into the value -- counts as one
    header key toward the threshold. Three or more distinct header keys
    means the value is the infobox, not a stat.
    """
    lowered = str(text or "").casefold()
    keys: set[str] = set()
    if re.match(r"\s*key\s*[:=]", lowered):
        keys.add("key")
    for key in sorted(_INFOBOX_HEADER_KEYS, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(key)}\s*[:=]", lowered):
            keys.add(key)
    return ["infobox_header"] if len(keys) >= 3 else []


def stat_field_rejection_reasons(text: Any) -> list[str]:
    """All field-level screens for one scalar stat value: template
    boilerplate, page scaffolding, editor notes, insubstantive
    placeholders, and infobox-header dumps. Applied identically by
    the repair path (attempt_from_result) and the recovery path."""
    reasons = boilerplate_reasons(text, scalar=True)
    for reason in infobox_header_reasons(text):
        if reason not in reasons:
            reasons.append(reason)
    return reasons


# ---------------------------------------------------------------------------
# Fragment screen. The fallback parser chain splits page sections
# into list items and scalar values, and its splitting sheds fragment
# debris the placeholder/scaffolding screens do not model -- the five
# shapes that failed gated sample 50d (which had zero
# franchise/continuity/infobox failures):
#   1. section-boundary bundles: a "None Notable" weakness carrying
#      the next section's header plus raw Category: markup;
#   2. scalar tail-fragments: a tier value that is only the tail of a
#      longer string (", higher as Werebeast");
#   3. sentence shards itemized as one-word weaknesses ("space",
#      "energy" split out of a prose paragraph);
#   4. comma-bundled items held together by split_listish's
#      "Resistance to..." keep-whole rule, stray paren included
#      ("Resistance to Extreme Temperatures), Berserker Mode, ...");
#   5. conjunction-orphaned list shards ("Gravity Manipulation with
#      her Mega Rod and", "and Healing with her Mother Box") and
#      glued "Resistance to: ..." two-item merges.
# Wiring: filter_list_field_items (the recovery field loop) and,
# since the frag job's Part 2, attempt_from_result -- the drain's
# repair path merged list debris unfiltered until the same screens
# were wired into its choke point. The scalar branch is wired into
# the recovery field loop and (via stat_field_rejection_reasons)
# attempt_from_result.
# ---------------------------------------------------------------------------

_FRAGMENT_SECTION_HEADER_PATTERNS = (
    r"\bnotable (?:attacks|techniques)(?:\s*/\s*(?:attacks|techniques))?\s*:",
    r"\bpowers and (?:abilities|techniques)\s*:",
    r"\bstandard equipment\s*:",
)

_FRAGMENT_BARE_HEADER = re.compile(
    r"^\s*(?:powers and abilities|standard equipment|weaknesses?|"
    r"equipment|intelligence|notable attacks(?:\s*/\s*techniques)?|"
    r"attacks?|techniques?)\s*:\s*$",
    re.IGNORECASE,
)

# A conjunction-led or conjunction-tailed item is an orphan shard only
# when it is short enough to be a noun-phrase fragment. A long prose
# clause that happens to begin mid-sentence after a comma split
# ("and his losses against faster opponents have exposed his stamina
# limits", 11 words) is substantive text, not a list shard.
_FRAGMENT_ORPHAN_MAX_WORDS = 8


def _fragment_word_count(lowered: str) -> int:
    return len(re.findall(r"[a-z0-9]+(?:'[a-z]+)?", lowered))


# ---------------------------------------------------------------------------
# Tail cleaning + prose shards (fragment screen, second iteration).
# Sample 50e failed on three shapes the first screen did not model:
#   6. editor-note tails: a real weakness clause carrying the source
#      page's editorial footer ("...Order and Chaos. Notes: Before
#      making any changes to this page"), and pure-note items whose
#      only head is a version-key label ("Deviantart 2 Note: ...");
#   7. version-key labels itemized as weaknesses: bare site/key
#      labels ("Deviantart 1") and label tails on real clauses
#      ("Grodd is prone to blind savage rage when angered. Respect
#      Threads: Amino Apps");
#   8. multi-word prose comma-shards in weaknesses: a lore paragraph
#      comma-split into sentence fragments above the sub-2-word
#      threshold ("a woman and a god", "specifically Kent").
# Chris-approved treatment for tails: when a substantive clause
# precedes the tail, STRIP the tail and keep the clause (recorded as
# a strip, not a drop); when the item is only the note/label, REJECT.
# ---------------------------------------------------------------------------

_EDITOR_NOTE_MARKER = re.compile(r"(?i)\bnotes?\s*:\s*")

# The source wiki's page footer. It usually rides in behind a
# "Note:"/"Notes:" marker, but comma-splitting can separate the two,
# leaving a bare "* Before making any changes..." tail.
_EDITOR_NOTE_PHRASE = re.compile(r"(?i)before making any changes")

# A version-key / respect-thread label segment running to the end of
# the item, either as the whole item or after a sentence boundary.
_VERSION_LABEL_TAIL = re.compile(
    r"(?i)(?:^|[.;]\s*)"
    r"(respect\s+threads?\s*:.*|deviant\s?art\b.*|amino\s+apps\b.*)$"
)

# The whole item is just a site/key label plus an optional version
# number ("Deviantart 1", "Deviantart 2 ...").
_BARE_VERSION_LABEL = re.compile(
    r"(?i)^\s*(?:deviant\s?art|amino\s+apps|respect\s+threads?)"
    r"\b[\s\d.…]*$"
)

# A tail may be stripped only off a head that can stand as an item on
# its own: at least three words and not itself a bare label.
_TAIL_HEAD_MIN_WORDS = 3


def _tail_head_substantive(head: str) -> bool:
    cleaned = head.strip().strip(".;, ")
    if _fragment_word_count(cleaned.casefold()) < _TAIL_HEAD_MIN_WORDS:
        return False
    return not _BARE_VERSION_LABEL.match(cleaned)


def clean_item_tails(item: Any) -> tuple[str, list[str]]:
    """Strip editor-note / version-key tails off one list item.

    Returns (cleaned_item, strip_reasons). A substantive clause keeps
    its text minus the tail (reasons editor_note_tail /
    version_key_label_tail). When nothing substantive precedes the
    tail -- the item IS the note or label -- returns ("", reasons)
    with editor_note_item / version_key_label, and the caller drops
    the item with those reasons. An item with no tail returns
    (item, []).
    """
    text = str(item or "").strip()
    if not text:
        return "", []
    reasons: list[str] = []
    marker = _EDITOR_NOTE_MARKER.search(text)
    phrase = _EDITOR_NOTE_PHRASE.search(text)
    cut: int | None = None
    if marker and (phrase is None or marker.start() <= phrase.start()):
        cut = marker.start()
    elif phrase:
        cut = phrase.start()
        head_tmp = text[:cut].rstrip()
        if head_tmp.endswith("*"):
            # "... * Before making any changes": swallow the bullet.
            cut = len(head_tmp) - 1
    if cut is not None:
        head = text[:cut].rstrip()
        if _tail_head_substantive(head):
            text = head.rstrip(" .;,")
            reasons.append("editor_note_tail")
        else:
            drop = ["editor_note_item"]
            if _BARE_VERSION_LABEL.match(head.strip().strip(".;, ")):
                drop.append("version_key_label")
            return "", drop
    label = _VERSION_LABEL_TAIL.search(text)
    if label:
        head = text[: label.start()].rstrip()
        if _tail_head_substantive(head):
            text = head.rstrip(" .;,")
            reasons.append("version_key_label_tail")
        else:
            return "", ["version_key_label"]
    if _BARE_VERSION_LABEL.match(text):
        return "", ["version_key_label"]
    return text, reasons


# Prose-shard rule (weaknesses only): a comma-split sentence fragment
# starts mid-sentence, so it opens lowercase with a continuation word
# (article / demonstrative / adverb / relative / preposition), stays
# short, and carries no verb of its own. Calibrated against the live
# corpus: pronoun-led clauses ("he can simply use the opponent's
# abilities") are spared by the opener set, auxiliary-bearing clauses
# by the aux set, and verb-bearing openers ("as the Attack Forme
# lowers durability") by the finite-verb escape. A second narrow
# clause catches parenthetical name-list shards ("Inza (Kent's wife)
# and Nabu."), which start capitalized but are pure apposition.
_PROSE_SHARD_MAX_WORDS = 6
_PROSE_SHARD_OPENERS = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those",
        "specifically", "including", "especially", "particularly",
        "notably", "however", "also", "usually", "often", "sometimes",
        "despite", "although", "though", "while", "when", "which",
        "who", "whom", "whose", "such", "as", "then",
    }
)
_PROSE_SHARD_AUX = frozenset(
    {
        "is", "are", "was", "were", "has", "have", "had", "can",
        "could", "will", "would", "shall", "should", "may", "might",
        "must", "does", "did", "be", "been", "being", "am",
    }
)


def _looks_like_finite_verb(token: str) -> bool:
    if token.endswith("'s"):
        # Possessive, not a verb ("Kent's wife").
        token = token[:-2]
    return (
        len(token) >= 4
        and token.endswith("s")
        and not token.endswith(("ss", "us", "is"))
    )


def _prose_shard(item: str, lowered: str, words: int) -> bool:
    tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", lowered)
    if not tokens or words < 2 or words > _PROSE_SHARD_MAX_WORDS:
        return False
    if any(token in _PROSE_SHARD_AUX for token in tokens):
        return False
    if any(_looks_like_finite_verb(token) for token in tokens):
        return False
    if item.strip()[:1].islower() and tokens[0] in _PROSE_SHARD_OPENERS:
        return True
    return (
        "(" in item
        and " and " in lowered
        and sum(1 for token in item.split() if token[:1].isupper()) >= 2
    )


# Prose-shard continuation rule (weaknesses only, second generation):
# the 50h gate showed comma-split prose continuations escaping
# _prose_shard two ways -- they carry an auxiliary verb ("have it
# carry her", "Can be sometimes exhausted by using her") or run past
# the 6-word cap ("use it to absorb energy from something or trap
# someone in a pocket dimension"). Two signals catch the family
# while sparing complete clauses:
#   (a) Dangling end: a SHORT item (<=10 words, single-sentence)
#       whose final whole token is a pronoun, possessive, preposition
#       or conjunction -- a word a clause cannot end on -- with no
#       subject pronoun (he/she/they/we) that could head a clause.
#       The whole-token test keeps hyphenated compounds ("cave-in")
#       and the length cap keeps stored multi-sentence prose out.
#   (b) Long subjectless continuation: a lowercase-opening,
#       single-sentence item past the word cap with no auxiliary and
#       no finite verb anywhere, carrying an object pronoun or an
#       infinitive chain -- a complete clause cannot be built
#       without a finite verb. Items carrying a subject pronoun or
#       a proper noun are spared: past-tense clauses ("he learned
#       how to...", "which allowed Denji to...") head exactly
#       there, and sparing a subordinate fragment is the cheap
#       direction.
_PROSE_CONT_DANGLING_END = frozenset(
    {
        "her", "him", "it", "them", "his", "hers", "its", "their",
        "himself", "herself", "itself", "themselves",
        "to", "from", "with", "by", "in", "on", "at", "of", "for",
        "against", "into", "onto", "upon", "and", "or", "but", "than",
    }
)
_PROSE_CONT_SUBJECTS = frozenset({"he", "she", "they", "we"})
_PROSE_CONT_DANGLING_MAX_WORDS = 10
# Function words that cannot head a clause: when a verb follows one
# of these, the verb is not subject-led.
_PROSE_CONT_FUNCTION = _PROSE_SHARD_AUX | frozenset(
    {
        "the", "a", "an", "this", "that", "these", "those",
        "to", "from", "with", "by", "in", "on", "at", "of", "for",
        "against", "into", "onto", "upon", "and", "or", "but", "than",
        "as", "so", "if", "when", "while", "not", "no",
        "sometimes", "always", "often", "usually", "still", "already",
        "even", "also", "just", "now", "then", "simply", "quickly",
        # Frag-10: "yet" and "thus" head continuations, not clauses --
        # "yet believes himself to be and thus can be overwhelmed..."
        # (gate 50m, casey-jones) miscounted "believes"/"can" as
        # headed because neither word was in this set. "however" and
        # the other conjunctive adverbs join them: "however this can
        # be negated..." (frag-8 control) is a main clause, and its
        # subject must not be read as clause-internal.
        "yet", "thus", "however", "therefore", "meanwhile", "instead",
        "otherwise", "furthermore", "moreover", "nevertheless",
        "nonetheless", "consequently", "accordingly",
    }
)


def _single_sentence(text: str) -> bool:
    return not re.search(r"[.!?]\s+[A-Z]", text.strip())


def _prose_shard_continuation(item: str, lowered: str, words: int) -> bool:
    tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", lowered)
    if len(tokens) < 2 or not _single_sentence(item):
        return False
    if words <= _PROSE_CONT_DANGLING_MAX_WORDS:
        raw_words = item.strip().rstrip(" .,;:").split()
        last = raw_words[-1].casefold().strip("()[]{}\"'") if raw_words else ""
        # Headed-clause spare: a clause whose verb is led by a
        # subject token ("opponents would...", "Whitesnake can...",
        # "it rips...") may legitimately END on a pronoun object;
        # it is whole, not dangling. The Raven shards open on the
        # auxiliary itself or on a bare verb -- no verb in them is
        # preceded by a subject -- so the spare never reaches them.
        headed = tokens[0] == "it" or any(
            (
                token in _PROSE_SHARD_AUX
                or _looks_like_finite_verb(token)
            )
            and idx > 0
            and tokens[idx - 1] not in _PROSE_CONT_FUNCTION
            for idx, token in enumerate(tokens)
        )
        if (
            last in _PROSE_CONT_DANGLING_END
            and not headed
            and not any(token in _PROSE_CONT_SUBJECTS for token in tokens)
        ):
            return True
    if (
        item.strip()[:1].islower()
        and tokens[0] != "it"
        and words > _PROSE_SHARD_MAX_WORDS
        and not any(token in _PROSE_SHARD_AUX for token in tokens)
        and not any(_looks_like_finite_verb(token) for token in tokens)
        and not any(token in _PROSE_CONT_SUBJECTS for token in tokens)
        and not any(
            token[:1].isupper() for token in item.split()[1:]
        )
        and (
            any(token in {"it", "him", "her", "them"} for token in tokens[:-1])
            or " to " in lowered
        )
    ):
        return True
    return False


# Glued tab-key composites (fourth debris generation, items). The
# CSPW pages carry a tabber whose tab labels the itemizer glued onto
# the first ability of a tab: "Base Hax Hammer Harleen Hax AoR
# Harley Hax Death Manipulation" (the harley-quinn-post-flashpoint
# sample-50g merge; frag-2 removed the identical composite from
# harley-quinn-dc-comics). The fingerprint is the tab category label
# recurring as the tabber cycles forms. Calibrated on the live
# corpus (67.5k distinct item names, incl. 63.5k from generated
# profiles): the exact-case token "Hax" appearing twice or more
# matches ZERO corpus names, while every broader repeated-token
# rule caught legitimate names (franchise-token runs, parenthetical
# lists). Prose uses lowercase ("mind hax") and is untouched: the
# check runs on the item's original case.
_TAB_KEY_LABEL = "Hax"


def _tab_key_composite(value: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9']+", value)
    return tokens.count(_TAB_KEY_LABEL) >= 2


# Editorial essay screen (sixth debris generation, items): wiki
# explanation/editor prose itemized as character content -- the
# superman-prime-earth sample-50i merge, whose ENTIRE weaknesses
# recovery was fragments of the page's explanatory essay ("as well
# as how the powers and nature of the character fundamentally
# work. This is particularly useful for more high-tiered
# characters...") plus a second-person instruction to whoever
# edits the page ("it is very important that you make sure that
# the text has good grammar/sentence structure"). Two families:
#   editor_instruction -- imperatives addressed to an editor and
#       references to the text/page/grammar as an artifact under
#       construction. Character content never tells its reader to
#       mind the grammar.
#   editorial_essay -- meta prose explaining powers or tiers in
#       general to readers ("the character" as a generic stand-in,
#       tier-system vocabulary), stating no trait of THIS
#       character. The seam every pattern keys on: character
#       content speaks about the character; this speaks about the
#       page, the text, or characters in general.
_EDITOR_INSTRUCTION_PATTERNS = (
    r"\bit is (?:very )?important that you\b",
    r"\byou (?:should|must|need to|have to) (?:specify|state|mention|note|include|list|indicate|describe)\b",
    r"\bmake sure (?:that )?(?:the text|the page|your (?:grammar|spelling))\b",
    r"\bgood grammar\b",
    r"\bsentence structure\b",
    r"\bgrammar\s*(?:/|and)\s*sentence\b",
    r"\bdo not (?:add|remove|edit|delete|change|revert)\b",
    r"\bwhen (?:writing|editing|creating) (?:a |the |this )?(?:page|profile|article)\b",
)
_EDITORIAL_ESSAY_PATTERNS = (
    r"\bhow the (?:powers|abilities|nature)(?: and (?:powers|nature|abilities))? of the character\b",
    r"\bpowers and nature of the character\b",
    r"\bthe nature of the character\b",
    r"\bthe character\b[^.]{0,80}\bfundamentally\b",
    r"\bfundamentally\b[^.]{0,40}\bthe character\b",
    r"\bparticularly useful for\b[^.]{0,60}\bcharacters\b",
    r"\bmore (?:high|low)-tiered\b",
    r"\b(?:high|low)-tiered characters\b",
    r"\bthis (?:section|page|explanation) (?:explains|will explain|is meant to|is intended to)\b",
    r"\bexplanation (?:section|page)\b",
)


def editorial_item_reasons(item: Any) -> list[str]:
    """Editorial-essay checks for one recovered list item.

    Returns reason strings; an empty list means the item is
    character content, not page prose about character content.
    """
    value = str(item or "")
    if not value.strip():
        return []
    lowered = value.casefold()
    reasons: list[str] = []
    if any(re.search(p, lowered) for p in _EDITOR_INSTRUCTION_PATTERNS):
        reasons.append("editor_instruction")
    if any(re.search(p, lowered) for p in _EDITORIAL_ESSAY_PATTERNS):
        reasons.append("editorial_essay")
    return reasons


# Concessive tail shards (sixth debris generation, weaknesses
# only): a fronted concessive clause with no main clause of its
# own -- the starfire sample-50i weakness "though this is draining
# to use", the tail of a sentence whose main clause stayed on the
# page. _prose_shard misses it because it carries an auxiliary, and
# _prose_shard_continuation misses it because it ends cleanly and
# opens on a subordinator. Test: the item OPENS with a concessive
# subordinator; a fronted subordinate clause is only a whole item
# when a main clause follows the comma -- no comma, or a post-comma
# tail with no subject-led verb, means the item is the subordinate
# clause alone. Items that merely CONTAIN a concessive clause after
# a main clause ("He is strong, though he tires quickly") do not
# open with the subordinator and are untouched.
_CONCESSIVE_OPENERS = ("even though ", "although ", "though ")
# Calibration round 1 (348 raw hits over the stored weakness
# corpus) showed the corpus legitimately stores concessive
# QUALIFIERS as standalone items -- clauses with a real subject
# and concrete limitation content ("although this drains her
# spiritual energy quickly", "though his transformations fix his
# eyesight"). Those are content, however fragmentary their syntax.
# The debris shape is narrower: a SHORT tail whose subject is a
# bare demonstrative or missing entirely and whose predicate is a
# vague property with no concrete content noun -- "though this is
# draining to use" states a cost of NOTHING named. The rule below
# therefore also requires: no subject pronoun / possessive /
# determiner-led subject heading the clause, no concrete content
# marker anywhere in the item, and <= 12 words.
_CONCESSIVE_SUBJECT_HEADS = frozenset(
    {
        "he", "she", "they", "we", "it", "you",
        "his", "her", "hers", "their", "theirs",
        "the", "a", "an",
    }
)
_CONCESSIVE_CONTENT_MARKERS = (
    r"\b(?:energy|strength|stamina|endurance|body|health|damage|"
    r"sight|eyesight|form|forms|power|powers|weakness|weaknesses|"
    r"cost|claim|magic|blood|life|mind|soul|durability)\b",
    r"\b(?:circumvent\w*|mitigat\w*|contradict\w*|unaffected|immune|"
    r"negat\w*|nullif\w*|counter\w*|ignor\w*|curb\w*|work-arounds?)\b",
    r"\b(?:will not|won't|does not|doesn't|did not|no longer)\b",
    # A verbless limitation with its condition stated ("although
    # weaker without her helmet") conveys the whole weakness; a
    # comparison tail ("though stronger than he ever let Vergil
    # see") does not match the condition form and still fires.
    r"\bweaker\b[^.]{0,30}\b(?:without|when|if|while)\b",
)
_CONCESSIVE_MAX_WORDS = 12


def _tail_has_main_clause(tail: str) -> bool:
    tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", tail.casefold())
    if not tokens:
        return False
    if any(
        (token in _PROSE_SHARD_AUX or _looks_like_finite_verb(token))
        and idx > 0
        and tokens[idx - 1] not in _PROSE_CONT_FUNCTION
        for idx, token in enumerate(tokens)
    ):
        return True
    # Subject-pronoun-led tail whose verb is shielded by an adverb
    # ("it also leaves her exhausted"): the pronoun heads a clause
    # as long as some verb follows it.
    return tokens[0] in {"it", "he", "she", "they", "we"} and any(
        token in _PROSE_SHARD_AUX or _looks_like_finite_verb(token)
        for token in tokens[1:]
    )


def _concessive_shard(item: str, lowered: str, words: int) -> bool:
    stripped = lowered.strip().lstrip("([{\"'* ")
    if stripped.startswith("and "):
        stripped = stripped[len("and "):]
    opener = next(
        (op for op in _CONCESSIVE_OPENERS if stripped.startswith(op)), None
    )
    if opener is None:
        return False
    if not _single_sentence(item):
        return False
    if "," in item or ";" in item:
        tail = re.split(r"[,;]", item, maxsplit=1)[1]
        if _tail_has_main_clause(tail):
            return False
    if words > _CONCESSIVE_MAX_WORDS:
        return False
    rest_tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", stripped[len(opener):])
    if rest_tokens and rest_tokens[0] in _CONCESSIVE_SUBJECT_HEADS:
        return False
    # A concrete subject performing the clause ("though rage can
    # override these", "although Madara dropped a second rock") is a
    # content clause, however subordinate its syntax: a verb in the
    # first three tokens headed by a non-function token.
    if any(
        (token in _PROSE_SHARD_AUX or _looks_like_finite_verb(token))
        and idx > 0
        and rest_tokens[idx - 1] not in _PROSE_CONT_FUNCTION
        for idx, token in enumerate(rest_tokens[:3])
    ):
        return False
    if any(re.search(p, lowered) for p in _CONCESSIVE_CONTENT_MARKERS):
        return False
    return True


# Section-integrity screen (sixth debris generation, weaknesses
# only): a named technique entry -- the character's OWN notable
# attack, label-headed "Name: <the character performs the attack>"
# -- itemized into the weaknesses field (starfire sample-50i:
# "Starbolt: Starfire can fire bolts of stellar energy out of her
# hands", "Nova: Starfire releases an omnidirectional energy
# pulse"). The content is real; the defect is purely that it is
# filed as a weakness. Per-item provenance does not survive field
# extraction, so the test is textual: an attack predicate plus an
# energy/projectile object, and NO limitation language anywhere in
# the item. A body that says the technique drains, exhausts, or
# backfires is stating a cost and is spared, as is any item naming
# a vulnerability. The screen only rejects from weaknesses; it
# never reroutes the item into abilities.
_TECHNIQUE_FINITE_VERBS = frozenset(
    {
        "fires", "shoots", "releases", "unleashes", "launches",
        "emits", "generates", "creates", "summons", "hurls",
        "projects", "channels", "manifests", "conjures",
        "produces", "expels", "detonates", "ignites",
    }
)
_TECHNIQUE_BASE_VERBS = (
    "fire|shoot|release|unleash|launch|emit|generate|create|summon|"
    "hurl|blast|project|channel|manifest|conjure|produce|expel|"
    "detonate|ignite"
)
_TECHNIQUE_OBJECTS = frozenset(
    {
        "energy", "bolt", "bolts", "beam", "beams", "blast", "blasts",
        "pulse", "pulses", "wave", "waves", "projectile",
        "projectiles", "flame", "flames", "lightning", "plasma",
        "radiation", "laser", "lasers", "ray", "rays", "orb", "orbs",
        "sphere", "spheres", "missile", "missiles", "explosion",
        "explosions", "aura", "tendrils", "spikes",
    }
)
_TECHNIQUE_WEAKNESS_MARKERS = (
    r"\b(?:weak|weakness|vulnerable|vulnerability|susceptible|susceptibility)\b",
    r"\b(?:drains|drained|draining|exhausts|exhausted|exhausting|fatigues|fatigued)\b",
    r"\b(?:drawback|downside|limitation|backfire|backfires|recoil|overuse|strain|strains)\b",
    r"\b(?:cannot|can't|can’t|unable|ineffective|useless)\b",
    r"\bnot immune\b",
    r"\b(?:leaves|leaving|drains|tires|hurts|harms|injures|damages|costs) (?:him|her|them|himself|herself|itself|themselves)\b",
    r"\bno (?:effect|defense|defence|resistance) against\b",
)


def _attack_predicate(lowered: str) -> bool:
    tokens = set(re.findall(r"[a-z]+(?:'[a-z]+)?", lowered))
    if tokens & _TECHNIQUE_FINITE_VERBS:
        return True
    return bool(
        re.search(
            rf"\b(?:can|could|will|would|is able to|was able to)\s+"
            rf"(?:\w+ly\s+)?(?:{_TECHNIQUE_BASE_VERBS})\b",
            lowered,
        )
    )


def _technique_label_body(value: str) -> str | None:
    """Split a "Name: body" technique entry, or None.

    The label must look like a name: 1-5 tokens, the first
    capitalized, every other token capitalized or a small connector
    -- sentence-like heads ("She is weak to...") are not labels.
    """
    match = re.match(r"^\s*(?P<label>[^:]{1,45}?):\s+(?P<body>\S.*)$", value.strip(), re.S)
    if not match:
        return None
    label = match.group("label").strip()
    if any(ch in label for ch in ".!?"):
        return None
    tokens = label.split()
    if not 1 <= len(tokens) <= 5:
        return None
    if not tokens[0][:1].isupper():
        return None
    connectors = {"of", "the", "and", "&", "de", "von"}
    for token in tokens[1:]:
        if token[:1].isupper() or token.casefold() in connectors or token.isdigit():
            continue
        return None
    return match.group("body")


def _own_technique_in_weaknesses(value: str, lowered: str) -> bool:
    if any(re.search(p, lowered) for p in _TECHNIQUE_WEAKNESS_MARKERS):
        return False
    tokens = set(re.findall(r"[a-z]+(?:'[a-z]+)?", lowered))
    if not tokens & _TECHNIQUE_OBJECTS:
        return False
    body = _technique_label_body(value)
    if body is not None:
        return _attack_predicate(body.casefold())
    return _attack_predicate(lowered)


_NAME_ONLY_TECHNIQUE_MARKERS = frozenset(
    {
        "punch", "punches", "strike", "strikes", "kick", "kicks",
        "blast", "blasts", "beam", "beams", "slam", "slams",
        "smash", "smashes", "chop", "chops", "slash", "slashes",
        "barrage", "uppercut", "headbutt", "suplex", "slap", "slaps",
        "rush",
    }
)
_NAME_FORM_CONNECTORS = frozenset({"of", "the", "and", "&", "de", "von"})


def _name_only_technique(value: str, lowered: str) -> bool:
    """Seventh generation: a bare technique NAME filed as a weakness.

    The frag-6 technique screen keys on labels and attack predicates;
    a name-only item ("Out Orbital Punch" -- description == name)
    carries neither. The discriminative residue is the NAME FORM:
    2-5 tokens, every token capitalized or a small connector (a move
    title, not a phrase), whose final token is an action noun
    (Punch / Strike / Kick / Blast / Beam / Slam / ...), with no
    limitation semantics anywhere in the item. Generic lowercase
    phrases ("energy blasts") and possessive vulnerability phrases
    ("Cyclops's optical blasts") are not name forms and survive, as
    do weapon-noun names ("Archangel Blades", "Spirit Bomb"): a bare
    weapon name in weaknesses conventionally means the character can
    be killed by it, so object nouns are excluded from the marker
    set by calibration decision.
    """
    if any(re.search(p, lowered) for p in _TECHNIQUE_WEAKNESS_MARKERS):
        return False
    text = value.strip().rstrip(".:!").strip()
    tokens = text.split()
    if not 2 <= len(tokens) <= 5:
        return False
    last = re.sub(r"[^a-z]", "", tokens[-1].casefold())
    if last not in _NAME_ONLY_TECHNIQUE_MARKERS:
        return False
    for token in tokens:
        core = token.strip(".,:;'\"()")
        if not core:
            return False
        if (
            core[:1].isupper()
            or core.casefold() in _NAME_FORM_CONNECTORS
            or core.isdigit()
        ):
            continue
        return False
    return True


# Page-disclaimer screen (eighth debris generation, weaknesses only):
# a fan-page disclaimer / editor attribution itemized as a weakness --
# the carnage-marvel-cinematic-universe sample-50k merge ("any
# information displayed on any profile based on Death Battle are
# solely based on whatever is said in their videos and not my own
# opinion. So if a character is weaker or stronger on a profile than
# they actually are then it isn't my fault."). Two rules, one reason:
#   (a) first-person voice AND a strong disclaimer/attribution
#       phrase. Weak markers are deliberately excluded: "based on"
#       and "according to" fire on narrative prose, "as stated"
#       matches inside "was stated", and "My Hero Academia" supplies
#       a phantom "my". A trailing lowercase "i" is ignored: the
#       120-char item-name cap cuts words mid-stream ("...his death
#       i"), manufacturing a first-person token.
#   (b) the capped-name safety net: the cap strips the first-person
#       tail, so a name carrying "displayed on any profile" fires
#       with no pronoun at all. Calibration (68,191 stored weakness
#       items): rule (a) 6 hits, all genuine disclaimers/editor notes
#       (the carnage text, a "Message me on Discord ... this page"
#       note x3, an "I just inputted everything according to the
#       legends" note x2); rule (b) 2 hits, both the stored
#       tifa-lockhart-classic copy of the same carnage disclaimer.
_PAGE_DISCLAIMER_STRONG = (
    "not my own",
    "my own opinion",
    "my fault",
    "isn't my fault",
    "not my fault",
    "message me",
    "this page",
    "this wiki",
    "displayed on",
    "their videos",
    "whatever is said",
    "in my opinion",
    "i think",
    "i believe",
    "according to the legends",
)
_PAGE_DISCLAIMER_FP = re.compile(
    r"\b(i|my|me|we|our|us|myself|ourselves|i'm|i've|i'll|we're|we've)\b"
)


def _page_disclaimer(value: str, lowered: str) -> bool:
    if "displayed on any profile" in lowered:
        return True
    raw = str(value or "").strip()
    # Trailing lowercase "i" is the 120-char cap cutting a word
    # ("...his death i"), not a first-person pronoun. A real
    # sentence-final "I" is uppercase and survives this strip.
    raw = re.sub(r"\si$", "", raw)
    low = raw.casefold()
    if not _PAGE_DISCLAIMER_FP.search(low):
        return False
    return any(phrase in low for phrase in _PAGE_DISCLAIMER_STRONG)


# Prose-sentence-shard screen (eighth debris generation, weaknesses
# only): the LEADING-EDGE complement to the existing shard screens.
# The 50k darwin/kraven merges are continuations of a sentence whose
# head stayed on the page -- an item that OPENS on a conjunction
# ("but will not meet his desires in many situations. For example"),
# a preposition ("during his fight with the Hulk"), or a gerund
# ("leading to mistakes."), or that ENDS on a lead-in ("For
# example"). The discriminative test is that the item has no clause
# of its own: no subject-led finite clause, and no main clause after
# a comma. Spares, all calibrated:
#   - a subject-led clause ("but he cannot fly", "however this can
#     be negated...") is a complete statement, not a shard. The
#     subject check expands contractions ("it's" -> it + is,
#     "they'll" -> they + will, "won't" -> will + not) and reads
#     -ed and irregular-past verbs, which the older helpers miss.
#   - a comma followed by a main clause ("During full moons, he
#     loses control") is a fronted phrase, not a fragment.
#   - a limitation marker anywhere ("vulnerable", "powerless",
#     "exhausted", "lacking", "at the cost of", "suffering from",
#     "incapable of", "open to attack") states a real limitation
#     and is spared even in fragment form.
#   - "without" + a noun phrase is a conditional weakness ("Without
#     his armor"); "without" + a gerund ("without discussing the
#     method") is a continuation and fires.
# Known accepted losses (fragmentary limitation phrasing the screen
# drops): "due to not having his symbol in her armor", "getting
# shocked when things don't go his way", plural-verb clauses with
# no pronoun subject ("however his feet remain on the ground...").
# Calibration (68,191 stored weakness items, final rule): 2,874 raw
# hits; sampled hits are fragment-class throughout (ability-prose
# tails, list fragments, narrative continuations). The darwin lead
# clause ("His body will adapt to whatever means to make Darwin
# survive") is deliberately NOT caught: it is a complete clause,
# and the naive item-level rule for it has a 12,691-item
# false-positive pool; a sibling-cluster rule is likewise dead
# (4,951 runs in stored data, including real limitation content
# such as Storm's emotional-dependence and Thor's holding-back
# statements). The gate decides whether the lead clause re-merges.
_SHARD_CONJ_OPENERS = (
    "but ", "and ", "or ", "so ", "yet ", "however ", "although ",
    # Frag-10: bare "rather " ("rather easy to outmaneuver.",
    # gate 50m devastator); "rather than " was already here.
    "though ", "rather than ", "rather ",
)
_SHARD_PREP_OPENERS = (
    "during ", "after ", "before ", "with ", "without ", "by ",
    "through ", "despite ", "because of ", "due to ", "in spite of ",
    # Frag-10: "to " leads prepositional continuations ("to the
    # point where it could potentially impede his judgement",
    # gate 50m ultra-magnus). The limitation and comma spares in
    # _prose_sentence_shard still protect real "to ..." items.
    "instead of ", "like ", "to ",
)
# Adverb openers (frag-9): "even" leads the same continuation shape
# as a conjunction ("even in the eminence of a battle."). "or" was
# simply missing from the frag-8 conjunction set (the gate-50l venom
# item "or by anything that can pass through the symbiote..." slipped
# through on exactly that gap); "like" is a prepositional opener
# ("like all others of its kind"). All three are extensions of this
# same reason, not new reasons: same spares, same calibration base.
_SHARD_ADV_OPENERS = ("even ", "especially ",)
_SHARD_TRAILING_LEADIN = ("for example", "for instance", "such as", "e.g.")
# First tokens ending in -ing that are names or nouns, not gerunds
# ("Lightning slapping Fang..." is a character name, not a verb).
_SHARD_GERUND_DENY = frozenset({
    "king", "ring", "thing", "spring", "morning", "evening",
    "lightning", "nothing", "something", "anything", "everything",
    "padding", "wedding", "building", "blessing",
})
_SHARD_SUBJECTS = frozenset({
    "he", "she", "they", "we", "it", "this", "that", "these", "those",
    "i", "you", "there", "who",
})
_SHARD_AUX = _PROSE_SHARD_AUX | frozenset({"cannot", "do", "does"})
# Function words that cannot head a clause -- the frag-5 set plus
# possessives and determiners: a "verb" preceded by one is a noun
# ("his desires", "the attack"), not a subject-led verb.
# _SHARD_NOUN_HEADS extends that with determiners, quantifiers,
# numbers, and the adjectives that commonly precede plural nouns in
# weakness prose ("many situations", "grievous injuries", "dark
# forces"): an -s token after one of these is a plural noun, not a
# 3rd-person verb, so it must not count as a headed clause.
_SHARD_NOUN_HEADS = frozenset({
    "his", "her", "their", "its", "my", "your", "our",
    "many", "much", "few", "several", "some", "any", "all", "most",
    "more", "less", "each", "every", "no", "one", "two", "three",
    "four", "five", "six", "seven", "eight", "nine", "ten", "both",
    "either", "neither", "another", "other", "such", "same", "own",
    "first", "second", "third", "next", "last", "single", "whole",
    "entire", "only", "great", "dark", "lost", "new", "old", "big",
    "small", "large", "high", "low", "long", "short", "good", "bad",
    "strong", "weak", "full", "true", "real", "secret", "hidden",
    "ancient", "final", "main", "major", "minor", "primary",
    "supreme", "ultimate", "eternal", "divine", "holy", "cosmic",
    "mystic", "magical", "physical", "mental", "spiritual",
    "psychic", "elemental", "natural", "human", "superhuman",
    "grievous", "severe", "terrible", "horrible", "awful",
    "serious", "critical", "deadly", "fatal", "mortal", "immortal",
    "infernal", "celestial", "demonic", "angelic", "arcane",
    "sacred", "cursed", "blessed", "pure", "bright", "brilliant",
    "radiant", "shining", "glowing", "blazing", "frozen", "burning",
    "broken", "shattered", "twisted", "corrupted", "silent",
    "swift", "slow", "quick", "rapid", "sudden", "instant",
    "endless", "boundless", "limitless", "countless", "nameless",
    "faceless", "formless", "timeless", "ageless", "fearless",
    "helpless", "hopeless", "restless", "breathless", "speechless",
    "motionless", "lifeless", "soulless", "heartless", "merciless",
    "ruthless", "relentless", "tireless", "unstoppable",
    "unbreakable", "invincible", "invulnerable", "undying",
    "deathless",
    # Frag-10: comparative/superlative forms of the same adjectives --
    # "the stronger mutants they may face" (gate 50m, casey-jones)
    # counted "mutants" as a headed -s verb because "stronger" was
    # not in this set. A plural noun after a comparative adjective
    # is a noun, never a verb.
    "stronger", "strongest", "weaker", "weakest", "greater",
    "greatest", "darker", "darkest", "higher", "highest", "lower",
    "lowest", "longer", "longest", "shorter", "shortest", "bigger",
    "biggest", "smaller", "smallest", "larger", "largest", "better",
    "best", "worse", "worst", "older", "oldest", "newer", "newest",
    "faster", "fastest", "slower", "slowest", "quicker", "quickest",
    "harder", "hardest", "tougher", "toughest", "brighter",
    "brightest", "heavier", "heaviest", "deadlier", "deadliest",
    "smarter", "smartest", "lighter", "lightest",
})
_SHARD_FUNCTION = _PROSE_CONT_FUNCTION | _SHARD_NOUN_HEADS
_SHARD_IRREGULAR_PAST = frozenset({
    "grew", "took", "made", "gave", "came", "went", "saw", "knew",
    "got", "found", "left", "felt", "brought", "began", "kept",
    "held", "meant", "set", "put", "cut", "hit", "ran", "sat",
    "stood", "spoke", "told", "thought", "became", "fell", "rose",
    "drew", "chose", "broke", "woke", "drove", "ate", "drank",
    "flew", "forgot", "froze", "hid", "rode", "sang", "sank",
    "shook", "stole", "swore", "tore", "wore", "won", "lost",
    "paid", "sold", "sent", "spent", "built", "bought", "caught",
    "taught", "read", "led", "fed", "met", "shot", "shut", "split",
    "spread", "bit", "bled", "bred", "clung", "dealt", "dug",
    "dreamt", "fled", "flung", "forbade", "foresaw", "foretold",
    "forsook", "ground", "hung", "heard", "knelt", "laid", "lay",
    "lit", "misled", "overcame", "overtook", "partook", "sought",
    "shrank", "shrunk", "slid", "slung", "slit", "smelt", "sowed",
    "sped", "spelled", "spilled", "spun", "spoiled", "sprang",
    "stank", "strove", "stuck", "swept", "swung", "threw", "thrust",
    "understood", "undertook", "underwent", "upheld", "upset",
    "wept", "withdrew", "withstood", "wrung", "wrote", "swam",
    "rang", "stung", "struck", "swept", "arose", "awoke", "bore",
    "borne", "beat", "beaten", "bent", "bound", "burst", "chosen",
    "clung", "crept", "dealt", "driven", "eaten", "fallen", "fed",
    "flown", "forbidden", "forgotten", "frozen", "given", "grown",
    "hidden", "known", "proven", "risen", "rung", "seen", "shaken",
    "shown", "sung", "sunk", "taken", "torn", "woken", "worn",
    "written",
})
_SHARD_LIMITATION_RE = re.compile(
    r"\b(?:weak\w*|vulnerab\w*|susceptib\w*|allerg\w*|immun\w*|"
    r"intoleran\w*|powerless|helpless|drain\w*|exhaust\w*|fatigue\w*|"
    r"drawback\w*|limit\w*|backfire\w*|recoil\w*|cannot|can't|"
    r"unable|ineffective\w*|dependent\w*|addict\w*|fear\w*|afraid|"
    r"blind\w*|deaf\w*|loses|losing|loss of|lost (?:his|her|their|its)|"
    r"sick\w*|ill\b|incapab\w*|lack\w*|requir\w*|cost\w*|"
    # Frag-10: a stat-lowering statement is a limitation ("as the
    # Attack Forme lowers durability" is a pinned corpus control),
    # which is what separates it from the narrative as-clauses the
    # subordinate-opener screen drops ("as he passes up a chance to
    # kill Wheeljack...").
    r"lower\w*|"
    r"suffer\w* from|open to (?:attack|harm|damage))\b",
    re.I,
)
_SHARD_CONTRACTIONS = {
    "it's": ("it", "is"), "he's": ("he", "is"), "she's": ("she", "is"),
    "that's": ("that", "is"), "there's": ("there", "is"),
    "what's": ("what", "is"), "who's": ("who", "is"),
    "it'll": ("it", "will"), "he'll": ("he", "will"),
    "she'll": ("she", "will"), "we'll": ("we", "will"),
    "they'll": ("they", "will"), "you'll": ("you", "will"),
    "i'll": ("i", "will"),
    "we're": ("we", "are"), "they're": ("they", "are"),
    "you're": ("you", "are"),
    "we've": ("we", "have"), "they've": ("they", "have"),
    "i've": ("i", "have"),
    "i'd": ("i", "would"), "he'd": ("he", "would"),
    "she'd": ("she", "would"), "it'd": ("it", "would"),
    "they'd": ("they", "would"), "we'd": ("we", "would"),
    "won't": ("will", "not"), "can't": ("can", "not"),
    "don't": ("do", "not"), "doesn't": ("does", "not"),
    "didn't": ("did", "not"), "isn't": ("is", "not"),
    "aren't": ("are", "not"), "wasn't": ("was", "not"),
    "weren't": ("were", "not"), "couldn't": ("could", "not"),
    "wouldn't": ("would", "not"), "shouldn't": ("should", "not"),
    "hasn't": ("has", "not"), "haven't": ("have", "not"),
    "mustn't": ("must", "not"), "mightn't": ("might", "not"),
    "needn't": ("need", "not"),
}
_SHARD_DETERMINERS = frozenset({
    "his", "her", "their", "its", "the", "a", "an", "my", "your", "our",
})


# Subordinate/relative clause markers (frag-10). A clause that opens
# on one of these is not a main clause, however complete its
# subject+verb pair looks: "when the incantation is uttered its
# effect is..." is whole only because of the clause AFTER the comma.
_SUBORD_MARKERS = frozenset({
    "as", "if", "when", "because", "while", "since", "unless",
    "although", "though", "where", "that", "who", "which", "whom",
    "whose",
})


# Prepositions (frag-10): a noun inside a prepositional phrase is the
# phrase's object, not a relative-clause head -- "with his sword he
# cuts through anything" (frag-8 control) has a main clause after the
# PP, while "the dog they saw" (that-less relative) does not.
_SHARD_PREPS = frozenset({
    "with", "by", "in", "on", "at", "of", "for", "from", "to",
    "through", "despite", "after", "before", "during", "without",
    "into", "onto", "upon", "against", "per", "via", "under", "over",
    "between", "among",
})


def _subject_is_clause_internal(tokens: list[str], idx: int) -> bool:
    """True when the subject pronoun at `idx` heads a subordinate,
    relative, or gerund phrase rather than a main clause -- so a verb
    after it must not count as a subject-led (or headed) main clause.

    The frag-9 headed/subject-led spares fired on clause-internal
    verbs: "the stronger mutants they may face" (gate 50m,
    casey-jones) counted "may" as headed because "they" precedes it,
    and "feeling he don't ever live up to Optimus Prime" (gate 50m,
    rodimus-prime) counted "do" the same way. A subject is internal
    when the token before it is a content word that is itself the head
    of a noun phrase (preceded by another content word, not a subject
    or function word -- "stronger mutants they"), a gerund ("feeling
    he"), or a subordinate marker ("where it", "that he"); a relative
    pronoun attached to a preceding noun ("anything that can pass")
    is internal by the frag-9 rule this generalizes. A leading subject
    ("He is...") or one after a verb ("said they may face") still
    counts as a main-clause subject.
    """
    if idx <= 0:
        return False
    token = tokens[idx]
    prev = tokens[idx - 1]
    if prev in _SHARD_FUNCTION:
        return False
    if token in ("that", "who", "which", "whom", "whose"):
        return True
    if prev in _SUBORD_MARKERS and prev not in ("though", "although"):
        # Concessive "though"/"although" are excluded: the frag-8
        # calibration pins though-led clauses as survivable controls
        # ("though he manages to gain some control over this as time
        # goes on.", "though he eventually recovered"), present and
        # past tense alike -- a concessive clause narrates a completed
        # or ongoing state, not a fragment continuation.
        return True
    # NOTE: no gerund branch here. A gerund followed by a subject+verb
    # ("meaning he'll occasionally slide along the ground", a frag-8
    # control) is a legitimate participial clause, and the rodimus
    # case ("feeling he don't...") is already handled by the
    # agreement guard in _shard_headed / _shard_subject_led, which
    # refuses "do" after "he". Treating gerund-led subjects as
    # internal would drop the control.
    if (
        idx >= 2
        and not prev.endswith("ly")
        and not _shard_is_verb(prev)
    ):
        # prev is a content noun, not a verb: the subject opens a
        # that-less relative clause ("the dog they saw", "his power
        # they stole") rather than a main clause. The -ly guard keeps
        # manner adverbs out ("silently they crept" is a main clause);
        # -s plural nouns ("mutants") look like verbs and fall
        # through to the noun-phrase branch below. The idx>=2 guard
        # keeps sentence adverbs out: "however this can be negated..."
        # (frag-8 control) has its subject at idx 1 with no noun
        # phrase before it, so it is a main-clause subject. And a noun
        # inside a prepositional phrase is the phrase's object, not a
        # relative-clause head: "with his sword he cuts through
        # anything" (frag-8 control) is a main clause after the PP.
        if not any(t in _SHARD_PREPS for t in tokens[max(0, idx - 4): idx - 1]):
            return True
    if (
        idx >= 2
        and tokens[idx - 2] not in _SHARD_SUBJECTS
        and tokens[idx - 2] not in _SHARD_DETERMINERS
        and not _shard_is_verb(tokens[idx - 2])
    ):
        # The word before the noun is another content word, not a
        # verb, a subject, or a determiner: a noun phrase ("stronger
        # mutants they", "the dog they" via the noun branch), not
        # verb+subject ("said they"). The determiner exclusion matters:
        # "with his sword he cuts" (frag-8 control) has "his" before
        # "sword", and the subject after the noun phrase is the main
        # clause's subject, not a relative-clause subject.
        return True
    return False


_SINGULAR_SUBJECTS = frozenset({"he", "she", "it", "this", "that"})
_PLURAL_SUBJECTS = frozenset({"they", "we", "you", "i"})


def _subject_verb_agrees(subject: str, verb: str) -> bool:
    """Nonstandard-agreement guard (frag-10): "he don't" is not a
    subject-led finite clause. "do" after a singular subject and
    "does" (or any 3rd-person -s verb) after a plural subject do not
    count as the subject's verb -- the gate-50m rodimus-prime item
    ("feeling he don't ever live up to Optimus Prime") survived on
    exactly that miscount. Ambiguous subjects ("who", "there") and
    past-tense forms are untouched.
    """
    if verb == "do" and subject in _SINGULAR_SUBJECTS:
        return False
    if verb == "does" and subject in _PLURAL_SUBJECTS:
        return False
    if (
        verb not in _SHARD_AUX
        and _looks_like_finite_verb(verb)
        and subject in _PLURAL_SUBJECTS
    ):
        return False
    return True


def _shard_expand_contractions(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    for token in tokens:
        expanded.extend(_SHARD_CONTRACTIONS.get(token, (token,)))
    return expanded


def _shard_is_verb(token: str) -> bool:
    # Full verb test, used ONLY for the subject-led spare, where a
    # subject pronoun precedes the verb. -ed and irregular-past
    # forms belong here only: in _shard_headed they misread
    # participles used as adjectives ("combat-related power" ->
    # "related" as a verb headed by "combat") and dropped a verbatim
    # shard from the screen.
    return (
        token in _SHARD_AUX
        or _looks_like_finite_verb(token)
        or (len(token) >= 4 and token.endswith("ed"))
        or token in _SHARD_IRREGULAR_PAST
    )


def _shard_headed(tokens: list[str]) -> bool:
    # Narrower verb test: an auxiliary or a 3rd-person -s verb.
    # A plural noun or a participle must not count as a verb here;
    # the noun-head words in _SHARD_FUNCTION keep those cases out.
    # Frag-10: a verb whose preceding subject pronoun is itself
    # clause-internal (see _subject_is_clause_internal) or whose
    # subject-verb agreement is nonstandard ("he don't") does not
    # count as a headed main clause either.
    for idx, token in enumerate(tokens):
        if not (token in _SHARD_AUX or _looks_like_finite_verb(token)):
            continue
        if idx <= 0:
            continue
        prev = tokens[idx - 1]
        if prev in _SHARD_FUNCTION:
            continue
        if prev in _SHARD_SUBJECTS:
            if _subject_is_clause_internal(tokens, idx - 1):
                continue
            if not _subject_verb_agrees(prev, token):
                continue
        return True
    return False


def _shard_subject_led(tokens: list[str]) -> bool:
    for idx, token in enumerate(tokens):
        if token not in _SHARD_SUBJECTS:
            continue
        # A relative pronoun attached to a preceding noun ("anything
        # that can pass...", "the suit that protects...") is not a
        # main-clause subject: it opens a relative clause, so a verb
        # after it must not count as a subject-led main clause. A
        # leading relative pronoun, or one after a function word,
        # still counts ("that he cannot control" is subject-led).
        # Frag-10 generalizes the exclusion to every subject pronoun
        # via _subject_is_clause_internal (gerund-led "feeling he",
        # noun-phrase "mutants they", subordinate "where it"), and
        # nonstandard agreement ("he don't") no longer counts as a
        # subject-led verb.
        if _subject_is_clause_internal(tokens, idx):
            continue
        for nxt in tokens[idx + 1: idx + 3]:
            if _shard_is_verb(nxt) and _subject_verb_agrees(token, nxt):
                return True
        return False
    return False


def _shard_comma_main_clause(text: str) -> bool:
    if "," not in text:
        return False
    tail = re.findall(
        r"[a-z]+(?:'[a-z]+)?", text.split(",", 1)[1].casefold())
    tail = _shard_expand_contractions(tail)
    return _shard_headed(tail) or _shard_subject_led(tail)


def _prose_sentence_shard(value: str, lowered: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _SHARD_LIMITATION_RE.search(text):
        return False
    stripped = lowered.strip().lstrip("([\"'* ")
    opener: str | None = None
    for op in _SHARD_CONJ_OPENERS:
        if stripped.startswith(op):
            opener = "conjunction"
            break
    if opener is None:
        for op in _SHARD_PREP_OPENERS:
            if stripped.startswith(op):
                opener = "preposition"
                break
    if opener is None:
        for op in _SHARD_ADV_OPENERS:
            if stripped.startswith(op):
                opener = "adverb"
                break
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", lowered)
    if not toks:
        return False
    if opener is None:
        first = toks[0]
        if (
            len(first) >= 4
            and first.endswith("ing")
            and first not in _SHARD_GERUND_DENY
        ):
            opener = "gerund"
    tail = re.sub(r"[.\s]+$", "", lowered.strip())
    trailing = any(tail.endswith(lead) for lead in _SHARD_TRAILING_LEADIN)
    if opener is None and not trailing:
        return False
    # "without" + a noun phrase is a conditional weakness ("Without
    # his armor"); "without" + a gerund ("without discussing the
    # method") is a continuation and fires. Same for "even without"
    # ("even without her horn" is a real limitation statement).
    without_rest: list[str] | None = None
    if stripped.startswith("without "):
        without_rest = toks[1:]
    elif stripped.startswith("even without "):
        without_rest = toks[2:]
    if without_rest is not None:
        rest = without_rest
        while rest and rest[0] in _SHARD_DETERMINERS:
            rest = rest[1:]
        if rest and not rest[0].endswith("ing"):
            return False
    expanded = _shard_expand_contractions(toks)
    if _shard_headed(expanded):
        return False
    if _shard_subject_led(expanded):
        return False
    if _shard_comma_main_clause(text):
        return False
    return True


# Relative-pronoun opener screen (ninth debris generation, weaknesses
# only): an item that OPENS on a relative pronoun (which/that/who/
# whom/whose/what) is a continuation of a sentence whose head stayed
# on the page -- "which has causes drastic shifts in his personality.",
# "which can weaken or nullify the suit's healing powers." (gate 50l,
# venom-earth-616). The frag-8 headed-clause spare does NOT apply
# here: the relative pronoun is itself the subject of its clause, so
# "which bounces upon hitting the ground" looks headed while still
# being a fragment with no antecedent. An item is whole only if it
# carries a MAIN clause of its own: a main clause after a comma, or a
# second independent clause after a sentence boundary. No limitation
# spare either: the relative clause's own verb ("weaken") does not
# make the item whole. One spare, and it is load-bearing: a PAST-
# TENSE relative clause narrates a completed event (a documented
# exploit), which the frag-5 long-clause calibration deliberately
# protects -- "which allowed Denji to successfully ambush her in
# their final confrontation" is a pinned zero-reason control, so the
# screen spares relative clauses whose main verb is past tense
# (-ed, irregular past, was/were/had). The gate-50l items are
# present-tense/modal property statements ("has causes", "can
# weaken") and still fire. Calibration (68,315 stored weakness items,
# frag-9 calib1 with the frag-8 spares): 131 residual; the true hit
# count under this screen's own completeness test is measured by
# calib3 (the frag-8 headed spare hid ~1,250 "which" continuations
# from that count). Sampled residual hits are fragment-class
# throughout (narrative/ability continuations).
_REL_PRONOUNS = (
    "which ", "that ", "who ", "whom ", "whose ", "what ",
    # Frag-10: "where " opens the same relative continuation
    # ("where he is ticklish.", gate 50m shredder).
    "where ",
)


def _rel_has_main_clause(text: str) -> bool:
    if _shard_comma_main_clause(text):
        return True
    parts = re.split(r"[.!?]\s+", text.strip())
    for tail in parts[1:]:
        toks = re.findall(r"[a-z]+(?:'[a-z]+)?", tail.casefold())
        expanded = _shard_expand_contractions(toks)
        if _shard_headed(expanded) or _shard_subject_led(expanded):
            return True
    return False


_REL_PAST_AUX = frozenset({"was", "were", "had"})


def _rel_clause_is_past(tokens: list[str]) -> bool:
    """True when the relative clause's main verb is past tense: it
    narrates a completed event, which the frag-5 calibration protects.
    The first verb decides: an auxiliary / 3rd-person -s verb is
    present tense (fire), an -ed form, irregular past, or was/were/had
    is past tense (spare). No verb at all means present/fragment."""
    for token in tokens:
        if token in _REL_PAST_AUX:
            return True
        if len(token) >= 4 and token.endswith("ed"):
            return True
        if token in _SHARD_IRREGULAR_PAST:
            return True
        if token in _SHARD_AUX or _looks_like_finite_verb(token):
            return False
    return False


def _relative_pronoun_opener(value: str, lowered: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    stripped = lowered.strip().lstrip("([\"'* ")
    if not any(stripped.startswith(p) for p in _REL_PRONOUNS):
        return False
    if _rel_has_main_clause(text):
        return False
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", lowered)
    if _rel_clause_is_past(toks):
        return False
    return True


# Numeric-split fragment screen (ninth debris generation, weaknesses
# only): the second half of a number split at its thousands comma --
# "000 hertz" (gate 50l, venom-mcu). The first half is prevented at
# the source by the split_listish thousands-comma guard; this is the
# backstop for halves already split in stored data or arriving by
# another path. An item opening with exactly three digits (fourth
# character not a digit) and carrying no clause of its own is a split
# half or an image-size fragment ("335 px", "250 pxthumb", "688").
# Calibration (68,315 stored weakness items): 190 items open with
# exactly three digits, all debris in the sampled 25; the limitation
# spare protects real numeric limits ("180 degree blind spot"). No
# rule on items ENDING in a bare digit: 1,172 such items, including
# legit "Season 3" / "White & Red #3" shapes.
_NUMERIC_SPLIT_RE = re.compile(r"^\d{3}(?!\d)")


def _numeric_split_fragment(value: str, lowered: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if not _NUMERIC_SPLIT_RE.match(text.lstrip("([\"'* ")):
        return False
    if _SHARD_LIMITATION_RE.search(text):
        return False
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", lowered)
    expanded = _shard_expand_contractions(toks)
    if _shard_headed(expanded) or _shard_subject_led(expanded):
        return False
    if _shard_comma_main_clause(text):
        return False
    return True


# Header + cut-off clause screen (ninth debris generation, weaknesses
# only): an item of the form "Header: <rest>" where the post-colon
# text is a cut-off fragment -- "Sonic and Heat: The Venom symbiote",
# "Darkforce: As Anti-Venom is formed from the Lightforce",
# "Antibody Overuse: If Anti-Venom overuses his healing powers"
# (gate 50l, venom-earth-616). Three firing shapes, in order:
#   1. subordinate-only rest: opens As/If/When/Because/While/After/
#      Before/Although/Though/Since/Unless/Once/Until with no main
#      clause after a comma and no limitation marker. The subordinate
#      check runs BEFORE the headed check: "If Anti-Venom overuses
#      his healing powers" has a finite verb inside the subordinate
#      clause, which must not count as a clause of its own.
#   2. shard rest: the post-colon text itself trips the prose-shard
#      screens ("Through the Force", "Drawing power from the moon",
#      "Like all Ainur").
#   3. short definite-NP rest: "The " + 2-4 words, no verb
#      ("The Venom symbiote"). Calibrated: 7 such items corpus-wide.
# A rest that is whole -- subject-led finite clause, main clause
# after a comma, leading finite verb ("Burns on contact"), or a
# limitation marker anywhere -- survives, as do longer definitions
# ("Ki Blast: The most basic form of energy wave."). "A "/"An "
# definitions are deliberately NOT caught (187 items, technique
# definitions, no verbatim failure) and neither is the 1,610-item
# other-bare-NP class: accepted residual, the gate decides.
_HEADER_SUBORD_OPENERS = (
    "as ", "if ", "when ", "because ", "while ", "after ", "before ",
    "although ", "though ", "since ", "unless ", "once ", "until ",
)
_HEADER_CUTOFF_RE = re.compile(r"^(.{1,80}?):\s+(.+)$")


def _header_rest_complete(rest: str) -> bool:
    if _SHARD_LIMITATION_RE.search(rest):
        return True
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", rest.casefold())
    expanded = _shard_expand_contractions(toks)
    if _shard_headed(expanded) or _shard_subject_led(expanded):
        return True
    if _shard_comma_main_clause(rest):
        return True
    if toks and (toks[0] in _SHARD_AUX or _looks_like_finite_verb(toks[0])):
        return True
    return False


def _header_cutoff(value: str, lowered: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    m = _HEADER_CUTOFF_RE.match(text)
    if not m or not (1 <= len(m.group(1).split()) <= 6):
        return False
    rest = m.group(2).strip()
    if not rest:
        return False
    rest_low = rest.casefold()
    if any(rest_low.startswith(op) for op in _HEADER_SUBORD_OPENERS):
        if _shard_comma_main_clause(rest):
            return False
        if _SHARD_LIMITATION_RE.search(rest):
            return False
        return True
    if _header_rest_complete(rest):
        return False
    if _prose_sentence_shard(rest, rest_low):
        return True
    words = rest.split()
    if rest_low.startswith("the ") and 2 <= len(words) <= 4:
        return True
    return False


# ---------------------------------------------------------------------------
# Tenth debris generation (frag-10): clause-aware main-clause test and
# the three screens built on it. The frag-9 spares (_shard_headed /
# _shard_subject_led) fire on ANY subject+verb pair in the item,
# including verbs inside subordinate and relative clauses -- "when
# anything related to the Kraang is brought up" looked headed because
# of the "is" inside the when-clause, and "to the point where it
# could potentially impede his judgement" looked headed because of
# the "could" inside the where-clause. The test below strips
# subordinate/relative clauses (marker ... first finite verb) and
# and-coordinated clause continuations before asking whether a main
# clause remains, so a subordinate clause alone never counts as one.
# ---------------------------------------------------------------------------


def _strip_subordinate_clauses(tokens: list[str]) -> list[str]:
    """Remove subordinate/relative clauses (marker ... first finite
    verb) from a token list, repeatedly, so main-clause detection is
    not fooled by subordinate verbs. A marker with no verb after it
    drops everything from the marker on."""
    toks = list(tokens)
    while True:
        midx = None
        for i, t in enumerate(toks):
            if t in _SUBORD_MARKERS:
                midx = i
                break
        if midx is None:
            break
        # Narrow verb test on purpose: the broad _shard_is_verb counts
        # -ed participles, so "when anything related to the Kraang is
        # brought up" stopped the strip at the adjective "related" and
        # left "is" looking like a main-clause verb. An auxiliary or
        # 3rd-person -s verb is the subordinate clause's finite verb;
        # a clause with only a participle verb has no finite verb at
        # all and drops from the marker on, which is the correct
        # outcome for a fragment either way.
        vidx = None
        for j in range(midx + 1, len(toks)):
            if toks[j] in _SHARD_AUX or _looks_like_finite_verb(toks[j]):
                vidx = j
                break
        if vidx is None:
            toks = toks[:midx]
            break
        toks = toks[:midx] + toks[vidx + 1:]
    # Coordinated continuations of a stripped subordinate clause
    # ("while the latter was on a Star Destroyer and Vader was on
    # Cymoon 1"): "and/or/but <word> <verb>" is a clause of its own,
    # not a main clause. Removing one can only remove its verb; a
    # real main clause elsewhere in the item survives the removal.
    changed = True
    while changed:
        changed = False
        for i, t in enumerate(toks):
            if t not in ("and", "or", "but") or i + 2 >= len(toks):
                continue
            for j in range(i + 1, min(i + 4, len(toks))):
                if toks[j] in _SHARD_AUX or _looks_like_finite_verb(toks[j]):
                    if toks[j - 1] not in _SHARD_FUNCTION:
                        toks = toks[:i] + toks[j + 1:]
                        changed = True
                    break
            if changed:
                break
    return toks


def _main_clause_present(text: str) -> bool:
    """True when the text carries a main clause of its own: a
    limitation statement, or any comma/sentence segment whose
    subordinate clauses stripped away still leaves a headed or
    subject-led finite clause. Parenthetical asides are stripped
    first -- a clause inside parens must not rescue a fragmentary
    item ("very short tempered (If ... he will throw a tantrum)").
    """
    if _SHARD_LIMITATION_RE.search(text):
        return True
    stripped = re.sub(r"\([^)]*\)", " ", str(text or ""))
    stripped = re.sub(r"\[[^\]]*\]", " ", stripped)
    for sentence in re.split(r"[.!?]\s+", stripped.strip()):
        for segment in sentence.split(","):
            toks = re.findall(r"[a-z]+(?:'[a-z]+)?", segment.casefold())
            toks = _shard_expand_contractions(toks)
            toks = _strip_subordinate_clauses(toks)
            if _shard_headed(toks) or _shard_subject_led(toks):
                return True
    return False


# Subordinate-opener screen (frag-10, weaknesses only): an item that
# OPENS on a subordinate conjunction and carries no main clause of
# its own -- "as he passes up a chance to kill Wheeljack in order to
# save Laserbeak." (soundwave), "As Ironhide ages" (ironhide),
# "especially when anything related to the Kraang is brought up"
# (leatherhead; the leading adverb is stripped before the opener
# test). Calibrated over 7,840 stored profiles / 68,345 weakness
# items (frag-10 calib1): as 1,065 raw / 907 residual, if 316/306,
# when 175/139, because 36/28, while 307/238, since 52/51, unless
# 26/26. "once" and "until" are deliberately EXCLUDED: their samples
# are legit limitations ("Once per day", "once a month on the night
# of the full moon") or version labels ("Until Multiverse of
# Madness"). "though"/"although" are excluded too -- the frag-8
# pinned concessive controls ("though he manages to gain some
# control over this as time goes on.") must keep surviving. A main
# clause after a comma, a sentence boundary, or a second
# subject+verb pair inside the item spares it ("after Noon his power
# will begin to decline.", "when the incantation is uttered its
# effect is the equivalent of a wish").
_SUBORD_CLAUSE_OPENERS = (
    "as ", "if ", "when ", "because ", "while ", "since ", "unless ",
)
_SUBORD_LEAD_ADVERBS = frozenset({
    "especially", "particularly", "notably", "specifically", "even",
    "also", "just", "simply", "very", "really", "quite", "so", "too",
})


def _subordinate_opener(value: str, lowered: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _SHARD_LIMITATION_RE.search(text):
        return False
    stripped = lowered.strip().lstrip("([\"'* ")
    words = stripped.split()
    while words and words[0] in _SUBORD_LEAD_ADVERBS:
        words = words[1:]
    if not words:
        return False
    rest = " ".join(words)
    if not any(rest.startswith(op) for op in _SUBORD_CLAUSE_OPENERS):
        return False
    return not _main_clause_present(text)


# Lowercase-predicate screen (frag-10, weaknesses only): a lowercase
# item opening on a degree adverb or bare predicate adjective with no
# main clause -- "insane and is very self loathing."
# (blackarachnia), "very short tempered (...)" (starscream). The
# first-token set is calibrated, not open-ended: degree/emphasis
# adverbs and the predicate adjectives the corpus actually opens on
# (very 16, completely 11, particularly 9, extremely/highly 6,
# incredibly 5, simply/quite 2, plus "so" 310 / "just" 68, whose
# main-clause items the completeness test spares). "nearly"/"almost"
# are deliberately excluded ("nearly indestructible" is a real
# limitation statement), and relative pronouns are excluded -- they
# belong to the relative-pronoun screen with its past-tense spare.
_LOWER_PRED_FIRST = frozenset({
    "very", "so", "too", "quite", "just", "really", "insane",
    "short", "rather", "completely", "particularly", "extremely",
    "highly", "incredibly", "simply", "utterly", "remarkably",
    "surprisingly", "notably", "specifically", "especially",
    "basically", "literally", "absolutely", "totally", "entirely",
    "mostly", "largely", "merely", "barely", "hardly", "scarcely",
})


def _lowercase_predicate(value: str, lowered: str) -> bool:
    text = str(value or "").strip()
    if not text or not text[:1].islower():
        return False
    if _SHARD_LIMITATION_RE.search(text):
        return False
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", lowered)
    if not toks:
        return False
    first = toks[0]
    if first in ("which", "that", "who", "whom", "whose", "what", "where"):
        return False
    if first not in _LOWER_PRED_FIRST:
        return False
    return not _main_clause_present(text)


# Trailing-fragment screen (frag-10, weaknesses only): a
# multi-sentence item whose FINAL sentence is a fragment -- "He is"
# (devastator, dangling auxiliary), "As the Constructicons'"
# (devastator, subordinate tail), "If the allspark shard in his
# head is removed" (starscream). Calibrated (frag-10 calib1):
# subordinate-led final sentences 1,562, dangling-aux finals 27.
# The generic short-no-verb-tail class (6,555 items) is deliberately
# NOT screened: hand review showed it mixes real fragments with
# legitimate short closes, so the screen fires only on the two
# narrow shapes below.
def _trailing_fragment(value: str, lowered: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    sentences = [
        s.strip() for s in re.split(r"[.!?]\s+", text) if s.strip()
    ]
    if len(sentences) < 2:
        return False
    final = sentences[-1]
    # The limitation spare is scoped to the FINAL sentence, not the
    # whole item: "His lacking intelligence offers little combat
    # adaptability" is a real limitation statement, but it does not
    # rescue the fragment tail "As the Constructicons'" (devastator).
    if _SHARD_LIMITATION_RE.search(final):
        return False
    final_low = final.casefold()
    if any(final_low.startswith(op) for op in _SUBORD_CLAUSE_OPENERS):
        if not _main_clause_present(final):
            return True
    if final_low.startswith("to "):
        if not _main_clause_present(final):
            return True
    toks = re.findall(r"[a-z]+(?:'[a-z]+)?", final_low)
    toks = _shard_expand_contractions(toks)
    if len(toks) == 2 and toks[0] in _SHARD_SUBJECTS and toks[1] in _SHARD_AUX:
        return True
    return False


def fragment_item_reasons(item: Any, *, section: str | None = None) -> list[str]:
    """Fragment-debris checks for one recovered list item.

    Returns reason strings; an empty list means the item is whole.
    `section` is the recovery field name; the sub-2-word shard rule
    applies to the weaknesses section only -- single-word abilities
    ("Flight") are legitimate items and are never size-checked.
    """
    value = str(item or "")
    if not value.strip():
        return []
    lowered = value.casefold()
    reasons: list[str] = []
    words = _fragment_word_count(lowered)
    if re.search(r"\bcategory\s*:", lowered):
        reasons.append("category_markup")
    if (
        any(
            re.search(pattern, lowered)
            for pattern in _FRAGMENT_SECTION_HEADER_PATTERNS
        )
        or _FRAGMENT_BARE_HEADER.match(value)
        or (value.strip().endswith(":") and words <= 5)
    ):
        # A short item that ENDS in a colon is a sub-header or a
        # label introducing a list ("The True Fate:"), never a whole
        # item; colon-bearing names ("Straw Doll Technique:
        # Resonance") do not end in a colon and are untouched.
        reasons.append("section_header")
    if value.count("(") != value.count(")"):
        reasons.append("unbalanced_parenthesis")
    if words <= _FRAGMENT_ORPHAN_MAX_WORDS and (
        re.match(r"and\s+", lowered.strip())
        or re.search(r"\b(?:and|or)\s*[.,;]?\s*$", lowered)
    ):
        reasons.append("conjunction_orphan")
    if re.match(r"\s*resistance to\s*:", lowered):
        reasons.append("glued_fragment")
    if _tab_key_composite(value):
        reasons.append("tab_key_composite")
    if section == "weaknesses" and words < 2:
        reasons.append("weakness_fragment")
    if section == "weaknesses" and _prose_shard(value, lowered, words):
        reasons.append("prose_shard")
    if section == "weaknesses" and _prose_shard_continuation(value, lowered, words):
        reasons.append("prose_shard_continuation")
    if section == "weaknesses" and _concessive_shard(value, lowered, words):
        reasons.append("concessive_shard")
    if section == "weaknesses" and _own_technique_in_weaknesses(value, lowered):
        reasons.append("technique_in_weaknesses")
    if section == "weaknesses" and _name_only_technique(value, lowered):
        reasons.append("name_only_technique_in_weaknesses")
    if section == "weaknesses" and _page_disclaimer(value, lowered):
        reasons.append("page_disclaimer")
    if section == "weaknesses" and _prose_sentence_shard(value, lowered):
        reasons.append("prose_sentence_shard")
    if section == "weaknesses" and _relative_pronoun_opener(value, lowered):
        reasons.append("relative_pronoun_opener")
    if section == "weaknesses" and _numeric_split_fragment(value, lowered):
        reasons.append("numeric_split_fragment")
    if section == "weaknesses" and _header_cutoff(value, lowered):
        reasons.append("header_cutoff")
    if section == "weaknesses" and _subordinate_opener(value, lowered):
        reasons.append("subordinate_opener")
    if section == "weaknesses" and _lowercase_predicate(value, lowered):
        reasons.append("lowercase_predicate")
    if section == "weaknesses" and _trailing_fragment(value, lowered):
        reasons.append("trailing_fragment")
    return reasons


def fragment_scalar_reasons(text: Any) -> list[str]:
    """Fragment-debris checks for one recovered scalar stat value.

    A value that is only the tail of a longer string -- it starts with
    punctuation (", higher as Werebeast") or with a bare comparative
    continuation carrying no value token of its own ("higher with the
    Moon" with no tier/digit anywhere) -- is debris, not a stat. A
    full value that merely contains a continuation later ("8-C,
    higher with ...") is untouched.
    """
    value = str(text or "").strip()
    if not value:
        return []
    reasons: list[str] = []
    if value[0] in ",;:)]}":
        reasons.append("scalar_tail_fragment")
    elif re.match(r"(?i)(?:far\s+)?(?:higher|lower)\b", value) and not re.search(
        r"\d", value
    ):
        reasons.append("scalar_tail_fragment")
    for reason in bare_qualifier_reasons(value):
        if reason not in reasons:
            reasons.append(reason)
    if _qualifier_only_stat(value):
        reasons.append("qualifier_only_stat")
    if _media_filename_value(value):
        reasons.append("media_fragment")
    return reasons


def _wikitext_categories(wikitext: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"\[\[Category:([^\]|]+)", str(wikitext or ""))
    ]


async def _fetch_page_categories(session: Any, api_url: str, title: str) -> list[str]:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "categories",
        "cllimit": "500",
        "titles": title,
        "redirects": "1",
    }
    try:
        async with session.get(api_url, params=params) as response:
            body = await response.json(content_type=None)
    except Exception:  # noqa: BLE001 - categories are one evidence channel
        return []
    pages = ((body or {}).get("query") or {}).get("pages") or []
    if not pages:
        return []
    return [
        str(row.get("title") or "").removeprefix("Category:").strip()
        for row in pages[0].get("categories") or []
        if row.get("title")
    ]


def evaluate_recovery_guard(
    profile: dict[str, Any],
    source: dict[str, Any],
    fields: dict[str, str],
    metadata: dict[str, Any],
    *,
    categories: list[str],
) -> dict[str, Any]:
    """Page-level guard verdict for one fetched recovery source page.

    Returns a JSON-safe verdict: accepted flag, how the page was reached
    ('recorded_title' when the fetched page is the recorded source page
    itself, else 'search_substitution'), the individual check results,
    franchise evidence channels, non-fiction hits, and rejection reasons.
    Boilerplate is field-level and applied separately to scoped fields.
    """
    fetched_title = str(metadata.get("title") or source.get("title") or "")
    fetched_url = str(metadata.get("url") or source.get("url") or "")
    recorded_title = str(source.get("title") or title_from_wiki_url(str(source.get("url") or "")) or "")
    via = (
        "recorded_title"
        if recorded_title
        and normalized_identity_text(fetched_title) == normalized_identity_text(recorded_title)
        else "search_substitution"
    )
    wikitext = str(metadata.get("raw_content") or "")
    all_categories = list(dict.fromkeys([*categories, *_wikitext_categories(wikitext)]))
    name_match = _guard_name_match(profile, fetched_title)
    channels = _guard_franchise_channels(
        profile,
        fetched_title=fetched_title,
        fetched_url=fetched_url,
        fields=fields,
        categories=all_categories,
        wikitext=wikitext,
    )
    nonfiction_hits = _guard_nonfiction_hits(
        profile,
        fetched_url=fetched_url,
        fields=fields,
        categories=all_categories,
        wikitext=wikitext,
    )
    continuity = continuity_check(
        profile,
        page_title=fetched_title,
        origin=str(fields.get("origin") or ""),
        categories=all_categories,
    )
    reasons: list[str] = []
    if not name_match:
        reasons.append("name_mismatch")
    if nonfiction_hits:
        reasons.extend(f"nonfiction:{hit}" for hit in nonfiction_hits)
    if continuity["mismatch"]:
        reasons.append("continuity_mismatch")
    if not channels:
        reasons.append("franchise_no_evidence")
    elif via == "search_substitution" and not (
        _STRONG_FRANCHISE_CHANNELS & set(channels)
    ):
        reasons.append("franchise_weak_evidence_only")
    return {
        "accepted": not reasons,
        "via": via,
        "fetched_title": fetched_title,
        "fetched_url": fetched_url,
        "revision_id": str(metadata.get("revision_id") or ""),
        "name_match": name_match,
        "franchise_channels": channels,
        "nonfiction_hits": nonfiction_hits,
        "continuity": continuity,
        "categories": all_categories,
        "reasons": reasons,
    }


async def recover_profile_evidence(
    profile_path: Path,
    *,
    dry_run: bool = False,
    notes_path: Path = service.DEFAULT_REVIEW_NOTES_PATH,
    max_sources: int = 3,
) -> dict[str, Any]:
    """Recover missing stats/abilities evidence from recorded sources.

    Returns a report dict; the profile file is rewritten in place when
    anything was recovered (unless dry_run). Promotion is the caller's
    decision (recompute approval_blockers on the returned profile).
    """
    import aiohttp

    from battlebot.harvest.fallback_parsers import run_parse_fallback_chain
    from battlebot.profiles.evidence_quality import (
        evidence_quality_blockers,
        has_usable_ability,
    )
    from battlebot.review.providers import mediawiki

    started = time.monotonic()
    report: dict[str, Any] = {
        "path": str(profile_path),
        "recovered_fields": [],
        "sources_tried": [],
        "merges": [],
        "guard_rejections": [],
        "parser_used": [],
        "scoped_key": None,
        "blockers_before": [],
        "blockers_after": [],
        "identity_mismatch": False,
        "error": "",
    }
    profile = service.load_yaml(profile_path)
    blockers_before = service.approval_blockers(profile)
    report["blockers_before"] = blockers_before
    stat_targets = {
        axis
        for axis in ("attack_potency", "speed", "durability")
        if f"missing_{axis}" in blockers_before or f"unlinked_stat:{axis}" in blockers_before
    }
    ability_target = (
        "missing_ability" in blockers_before
        or "missing_clean_linked_ability" in blockers_before
    )
    if not stat_targets and not ability_target:
        report["blockers_after"] = blockers_before
        report["profile"] = profile
        return report

    # The profile's own recorded mediawiki sources only, best first:
    # sources already cited by the profile's stats, then by candidate rank.
    cited_ids: set[str] = set()
    power = profile.get("power_scale") or {}
    for entry in power.values():
        if isinstance(entry, dict):
            cited_ids.update(str(s) for s in entry.get("source_ids") or [])
    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for source in profile.get("sources") or []:
        if not isinstance(source, dict):
            continue
        if source.get("continuity_suspect"):
            # Recorded source proven to resolve to a different
            # continuity's page (source-repair sweep); never fetch it.
            continue
        url = str(source.get("url") or "")
        if not url or url in seen_urls:
            continue
        if not mediawiki.resolve_mediawiki_api_url(url):
            continue
        seen_urls.add(url)
        candidates.append(source)
    candidates.sort(
        key=lambda s: (
            0 if str(s.get("id") or "") in cited_ids else 1,
            -rank_source_candidate(profile, s),
        )
    )
    candidates = candidates[:max_sources]
    if not candidates:
        report["error"] = "no_recorded_mediawiki_sources"
        report["blockers_after"] = blockers_before
        report["profile"] = profile
        return report

    timeout = aiohttp.ClientTimeout(total=20, connect=3, sock_connect=3, sock_read=12)
    best_attempt: SourceAttempt | None = None
    async with aiohttp.ClientSession(
        timeout=timeout, headers={"User-Agent": "battlebot-evidence-recovery/0.1"}
    ) as session:
        for source in candidates:
            url = str(source.get("url") or "")
            api_url = mediawiki.resolve_mediawiki_api_url(url)
            source_id = source_id_for(source, str(source.get("title") or "source"))
            tried: dict[str, Any] = {"source_id": source_id}
            report["sources_tried"].append(tried)
            parser = str(source.get("parser") or "")
            parse_fn = (
                powerlisting.parse_ability_taxonomy
                if parser == "mediawiki_ability_taxonomy"
                else parse_source_content
            )
            try:
                if parser == "mediawiki_ability_taxonomy":
                    fields0, meta = await mediawiki.fetch_mediawiki_fields(
                        source, powerlisting.parse_ability_taxonomy
                    )
                elif parser in {
                    "",
                    "mediawiki_battle_stats",
                    "mediawiki_ability_taxonomy",
                    "mediawiki_power_levels",
                }:
                    fields0, meta = await mediawiki.fetch_mediawiki_fields(
                        source, parse_source_content
                    )
                else:
                    fields0, meta = await fetch_source_fields(source)
            except Exception as exc:  # noqa: BLE001 - per-source isolation
                tried["error"] = f"{type(exc).__name__}: {exc}"
                continue
            tried["fetch_status"] = meta.get("fetch_status")
            tried["note"] = meta.get("note")
            fetched_title = str(meta.get("title") or source.get("title") or "")
            tried["title"] = fetched_title
            if meta.get("fetch_status") != "fetched" or not fetched_title:
                continue

            # --- Recovery guard: the fetched page must be this profile's
            # own character, in this profile's franchise, and fictional
            # evidence only. Search substitution gets a direct-title
            # retry under the same guard before the source is given up.
            categories = await _fetch_page_categories(session, api_url, fetched_title)
            verdict = evaluate_recovery_guard(
                profile, source, fields0, meta, categories=categories
            )
            guard_attempts = [verdict]
            if not verdict["accepted"] and verdict["via"] == "search_substitution":
                recorded_title = str(
                    source.get("title") or title_from_wiki_url(url) or ""
                )
                if recorded_title and recorded_title != fetched_title:
                    try:
                        retry_fields, retry_meta = await mediawiki.fetch_title_fields(
                            session, api_url, recorded_title, source, parse_fn
                        )
                    except Exception as exc:  # noqa: BLE001 - retry is best-effort
                        retry_fields, retry_meta = {}, {"error": f"{type(exc).__name__}: {exc}"}
                    if retry_meta.get("fetch_status") == "fetched" and retry_meta.get("title"):
                        retry_categories = await _fetch_page_categories(
                            session, api_url, str(retry_meta.get("title"))
                        )
                        retry_verdict = evaluate_recovery_guard(
                            profile, source, retry_fields, retry_meta,
                            categories=retry_categories,
                        )
                        retry_verdict["via"] = (
                            "direct_title_retry"
                            if retry_verdict["via"] == "recorded_title"
                            else retry_verdict["via"]
                        )
                        guard_attempts.append(retry_verdict)
                        if retry_verdict["accepted"]:
                            fields0, meta = retry_fields, retry_meta
                            verdict = retry_verdict
                            fetched_title = str(meta.get("title") or recorded_title)
                            tried["title"] = fetched_title
                            tried["fetch_status"] = meta.get("fetch_status")
                            tried["note"] = meta.get("note")
            tried["guard_attempts"] = guard_attempts
            tried["guard"] = verdict
            if not verdict["accepted"]:
                if "name_mismatch" in verdict["reasons"]:
                    report["identity_mismatch"] = True
                report["guard_rejections"].append(
                    {
                        "source_id": source_id,
                        "fetched_title": verdict["fetched_title"],
                        "fetched_url": verdict["fetched_url"],
                        "via": verdict["via"],
                        "reasons": verdict["reasons"],
                    }
                )
                continue
            via = verdict["via"]
            fetched_title = verdict["fetched_title"] or fetched_title

            wikitext = str(meta.get("raw_content") or "")
            fields = fields0
            if wikitext:
                async def _fetch_rendered_html() -> str:
                    params = {
                        "action": "parse",
                        "page": fetched_title,
                        "prop": "text",
                        "format": "json",
                        "formatversion": "2",
                    }
                    async with session.get(api_url, params=params) as response:
                        body = await response.json(content_type=None)
                    parse = (body or {}).get("parse") or {}
                    text = parse.get("text")
                    if isinstance(text, dict):
                        return str(text.get("*") or "")
                    return str(text or "")

                chain = await run_parse_fallback_chain(
                    wikitext=wikitext,
                    title=fetched_title,
                    first_pass_fields=fields0,
                    fetch_rendered_html=_fetch_rendered_html,
                )
                fields = chain.get("fields") or fields0
                tried["parser_used"] = chain.get("parser_used")
                report["parser_used"].append(chain.get("parser_used"))
            # Boilerplate hygiene: a template-residue keys field would
            # poison the scope labels, so drop it before label extraction.
            if fields.get("keys") and boilerplate_reasons(fields["keys"], scalar=True):
                tried.setdefault("boilerplate_fields", []).append("keys")
                fields = {k: v for k, v in fields.items() if k != "keys"}
            page_labels = _recovery_key_labels(fields)
            key = _recovery_scope_key(profile, page_labels)
            if key and report["scoped_key"] is None:
                report["scoped_key"] = key
            scoped_fields, scope_methods = _scope_recovery_fields(
                fields, key=key, page_labels=page_labels
            )
            # Explicit-none backstop: a source whose (scoped) weakness
            # section is an explicit-none statement contributes NO
            # weakness items, whatever producer built the fields --
            # the frag-7 root cause was a "None notable" section whose
            # extractor-glued tail itemized the page's own Notable
            # Attacks list into the profile's weaknesses.
            if "weaknesses" in scoped_fields and explicit_none_value(
                scoped_fields["weaknesses"]
            ):
                tried.setdefault("boilerplate_fields", []).append("weaknesses")
                tried.setdefault("boilerplate_reasons", {})["weaknesses"] = [
                    "explicit_none_weaknesses"
                ]
                del scoped_fields["weaknesses"]
                scope_methods.pop("weaknesses", None)
            # Field-level boilerplate filter: template instructions or
            # markup residue in a recovered field reject that field only.
            # List sections are filtered per item first: one placeholder
            # item must not poison (or sneak through with) real items.
            for field_name in list(scoped_fields):
                if field_name in _RECOVERY_SECTIONS:
                    kept_text, dropped_items, stripped_items = (
                        filter_list_field_items_detailed(
                            scoped_fields[field_name], section=field_name
                        )
                    )
                    if dropped_items:
                        tried.setdefault("dropped_items", {})[
                            field_name
                        ] = dropped_items
                    if stripped_items:
                        tried.setdefault("stripped_items", {})[
                            field_name
                        ] = stripped_items
                    if not kept_text:
                        tried.setdefault("boilerplate_fields", []).append(field_name)
                        tried.setdefault("boilerplate_reasons", {})[field_name] = [
                            "placeholder_items_only"
                        ]
                        del scoped_fields[field_name]
                        scope_methods.pop(field_name, None)
                        continue
                    scoped_fields[field_name] = kept_text
                scalar = field_name in _RECOVERY_AXES or field_name == "keys"
                reasons = boilerplate_reasons(scoped_fields[field_name], scalar=scalar)
                if field_name in _RECOVERY_AXES:
                    reasons = reasons + infobox_header_reasons(
                        scoped_fields[field_name]
                    )
                    # Fragment screen (scalars): a value that is only
                    # the tail of a longer string is parser debris.
                    for reason in fragment_scalar_reasons(scoped_fields[field_name]):
                        if reason not in reasons:
                            reasons.append(reason)
                if reasons:
                    tried.setdefault("boilerplate_fields", []).append(field_name)
                    tried.setdefault("boilerplate_reasons", {})[field_name] = reasons
                    del scoped_fields[field_name]
                    scope_methods.pop(field_name, None)
            tried["page_keys"] = page_labels
            tried["scoped_fields"] = sorted(scoped_fields)
            tried["scope_methods"] = scope_methods

            before_fields = set(report["recovered_fields"])
            recovered = apply_extracted_fields(
                profile_path,
                profile,
                scoped_fields,
                source_id=source_id,
                confidence=0.9,
                overwrite=False,
                dry_run=dry_run,
                notes_path=notes_path,
            )
            # Abilities: apply_extracted_fields only fills an empty list.
            # When no existing ability is usable, replace the unusable set
            # with source-backed items from the profile's own source page.
            if "powers_and_abilities" in scoped_fields and not has_usable_ability(profile):
                abilities = list_items_from_text(
                    "powers_and_abilities",
                    scoped_fields["powers_and_abilities"],
                    source_ids=[source_id],
                    inherited_tags=[],
                    inherited_dependencies=[],
                    inherited_scope_limitations=[],
                )
                if abilities:
                    profile["abilities"] = abilities
                    if "abilities" not in recovered:
                        recovered.append("abilities")
            if recovered:
                best_attempt = SourceAttempt(
                    source_id=source_id,
                    url=url,
                    ok=True,
                    note="evidence_recovery",
                    authority=str(source.get("authority") or ""),
                    promotion_allowed=bool(source.get("promotion_allowed", False)),
                    provider_id=str(source.get("provider_id") or ""),
                    revision_id=str(meta.get("revision_id") or ""),
                    fetch_status="fetched",
                )
                report["recovered_fields"] = sorted(before_fields | set(recovered))
                report["merges"].append(
                    {
                        "source_id": source_id,
                        "fetched_title": verdict["fetched_title"],
                        "fetched_url": verdict["fetched_url"],
                        "revision_id": verdict["revision_id"],
                        "via": via,
                        "franchise_channels": verdict["franchise_channels"],
                        "recovered_fields": sorted(recovered),
                    }
                )
            remaining_stats = {
                axis
                for axis in stat_targets
                if not service.power_text(profile, axis)
            }
            if not remaining_stats and (
                not ability_target or has_usable_ability(profile)
            ):
                break

    if report["recovered_fields"]:
        _collapse_duplicate_source_ids(profile)
        scope_report = apply_version_scope_default(profile)
        if scope_report.get("fired"):
            report["version_scope_fired"] = True
        if best_attempt is not None and not evidence_quality_blockers(profile):
            apply_primary_profile_state(
                profile, primary=best_attempt, corroborated=False
            )
        if not dry_run:
            service.write_yaml(profile_path, profile)
            provenance = "; ".join(
                f"{m['source_id']} -> {m['fetched_title']} "
                f"(rev {m['revision_id'] or '?'}, via {m['via']}, "
                f"franchise via {','.join(m['franchise_channels']) or 'n/a'})"
                for m in report["merges"]
            )
            service.add_review_note(
                profile_path,
                field_path="evidence_recovery",
                issue_type="auto_repair",
                note=(
                    "Evidence recovery from recorded sources: "
                    + ", ".join(report["recovered_fields"])
                    + f" (parsers: {', '.join(p for p in report['parser_used'] if p)})"
                    + (f" [provenance: {provenance}]" if provenance else "")
                ),
                notes_path=notes_path,
            )
    report["blockers_after"] = service.approval_blockers(profile)
    report["wall_seconds"] = round(time.monotonic() - started, 2)
    report["profile"] = profile
    return report
