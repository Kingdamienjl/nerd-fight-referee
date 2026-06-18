"""Automatic source-backed repair for needs_review profiles."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import yaml

from battlebot.harvest.auto_profile_harvester import (
    FIELD_ALIASES,
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
    missing = []
    for field_name in ("attack_potency", "speed", "durability"):
        if not service.power_text(profile, field_name):
            missing.append(field_name)
    if not profile.get("abilities"):
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


def attempts_with_core_fields(attempts: list[SourceAttempt]) -> list[SourceAttempt]:
    """Return attempts that have all three core fields (regardless of other eligibility)."""
    return [
        attempt
        for attempt in attempts
        if attempt.fetch_status == "fetched"
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
    if len(tokens) > len(suffix_tokens) and tokens[-len(suffix_tokens) :] == suffix_tokens:
        return " ".join(tokens[: -len(suffix_tokens)])
    return normalized


def local_identity_text(profile: dict[str, Any], value: str) -> str:
    return identity_text_without_trailing_tokens(value, str(profile.get("franchise") or ""))


def base_title_identity_text(value: str) -> str:
    return normalized_identity_text(re.sub(r"\s*\([^)]*\)\s*$", "", value).strip())


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
    title_base = base_title_identity_text(attempt.normalized_page_title)
    name = local_identity_text(profile, str(profile.get("name") or ""))
    franchise = normalized_identity_text(str(profile.get("franchise") or ""))
    match_text = normalized_identity_text(text_for_identity_matching(attempt))
    if not title or not name:
        return 0
    if title_wrong_for_profile(profile, attempt.normalized_page_title):
        return 0
    normalized_names = [local_identity_text(profile, value) for value in profile_identity_names(profile)]
    alias_names = [value for value in normalized_names if value != name]
    exact_base_name_match = title_base == name
    attempt.exact_name_match = title == name
    attempt.alias_match = any(title == alias or title_base == alias or alias in match_text for alias in alias_names)
    attempt.franchise_match = bool(franchise and franchise in match_text)
    score = 0
    if attempt.exact_name_match or exact_base_name_match:
        score += 100
    elif attempt.alias_match:
        score += 90
    elif (name in title or name in title_base) and (attempt.franchise_match or len(tokens_for_identity(name)) > 1):
        score += 80
    else:
        tokens = tokens_for_identity(name)
        if tokens and all(token in title for token in tokens):
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
    attempt.identity_match = attempt.identity_score >= 60
    attempt.variant_score = variant_score_for_attempt(profile, attempt)
    attempt.provider_priority = provider_priority(attempt.authority, attempt.provider_id)
    attempt.duplicate_key = duplicate_key_for_attempt(attempt)


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
    generation = profile.get("generation") if isinstance(profile.get("generation"), dict) else {}
    review = profile.get("review") if isinstance(profile.get("review"), dict) else {}
    if primary or force_promotable:
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
        generation.setdefault("ineligible_reasons", ["needs_review"])
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
    debug_dir.mkdir(parents=True, exist_ok=True)
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
    debug_report_path(profile_path, debug_dir).write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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
        [candidate_row_from_attempt(attempt) for attempt in attempts if attempt.extracted_fields],
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
        and attempt.core_field_count >= 3
        and attempt.ability_count >= 1
    )
    force_promotable = is_now_promotable and has_identity_match_source
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
