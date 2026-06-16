"""Automated enriched profile harvester.

Phase 2A intentionally keeps this module self-contained. It can read a CSV roster,
look up source metadata from AniList, optional IGDB, and MediaWiki-compatible APIs,
cache raw API responses under ``data/cache``, and write enriched YAML profile drafts.

It does not import profiles into Postgres, implement /fight, call the battle referee,
or perform any live Discord/worker behavior.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from battlebot.profiles import yaml_io
from battlebot.profiles.variants import variant_metadata
from battlebot.schemas.profile import CharacterProfile

DEFAULT_MEDIAWIKI_API = "https://vsbattles.fandom.com/api.php"
ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
IGDB_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_CHARACTER_URL = "https://api.igdb.com/v4/characters"

CORE_FIELDS = ("attack_potency", "speed", "durability", "powers_and_abilities")
POWER_SCALE_FIELDS = (
    "tier",
    "attack_potency",
    "speed",
    "lifting_strength",
    "striking_strength",
    "durability",
    "stamina",
    "range",
    "intelligence",
)
REQUIRED_POWER_FIELDS = ("attack_potency", "speed", "durability")

FIELD_ALIASES = {
    "tier": "tier",
    "keys": "keys",
    "key": "keys",
    "forms": "keys",
    "form": "keys",
    "attack potency": "attack_potency",
    "attack": "attack_potency",
    "ap": "attack_potency",
    "attack power": "attack_potency",
    "destructive capacity": "attack_potency",
    "attack_potency": "attack_potency",
    "speed": "speed",
    "lifting strength": "lifting_strength",
    "ls": "lifting_strength",
    "lifting_strength": "lifting_strength",
    "striking strength": "striking_strength",
    "ss": "striking_strength",
    "striking_strength": "striking_strength",
    "durability": "durability",
    "durability level": "durability",
    "stamina": "stamina",
    "range": "range",
    "standard equipment": "standard_equipment",
    "equipment": "standard_equipment",
    "notable equipment": "standard_equipment",
    "weapons": "standard_equipment",
    "standard_equipment": "standard_equipment",
    "intelligence": "intelligence",
    "weaknesses": "weaknesses",
    "weakness": "weaknesses",
    "powers and abilities": "powers_and_abilities",
    "powers & abilities": "powers_and_abilities",
    "powers": "powers_and_abilities",
    "abilities": "powers_and_abilities",
    "p&a": "powers_and_abilities",
    "powers/abilities": "powers_and_abilities",
    "powers / abilities": "powers_and_abilities",
    "powers_and_abilities": "powers_and_abilities",
}

DELIMITERLESS_FIELD_LABELS = (
    "Attack Potency",
    "AP",
    "Speed",
    "Durability",
    "Powers and Abilities",
    "Powers/Abilities",
    "Abilities",
    "Tier",
    "Stamina",
    "Range",
    "Weaknesses",
)

KEYWORD_RULES = {
    "biological_possession": ["possession", "possess", "host body", "parasite", "symbiote"],
    "armor_intrusion": ["infiltrate armor", "inside armor", "bypass armor", "armor intrusion"],
    "powered_armor": ["powered armor", "armor suit", "exoskeleton", "iron man armor"],
    "technology_dependency": ["technology", "computer", "software", "machine", "device"],
    "pilot_dependency": ["pilot", "operator", "remote controlled", "requires user"],
    "sonic_attack": ["sonic", "sound wave", "vibration", "ultrasonic"],
    "heat_attack": ["heat", "fire", "flame", "thermal", "plasma"],
    "sonic_or_heat_interaction": ["sonic", "sound", "heat", "fire", "flame"],
    "reality_warping": ["reality warping", "alter reality", "rewrite reality"],
    "time_manipulation": ["time stop", "time travel", "time manipulation", "temporal"],
    "dimensional_travel": ["dimensional travel", "dimension", "portal", "teleport"],
    "battlefield_relocation": ["battlefield", "relocate", "teleport", "banish", "portal"],
    "native_scope_limited": ["native realm", "own realm", "home dimension", "limited to"],
    "artifact_dependency": ["artifact", "relic", "gem", "stone", "amulet"],
    "resource_dependency": ["energy source", "battery", "fuel", "mana", "stamina"],
    "mind_control": ["mind control", "telepathy", "hypnosis", "brainwash"],
    "soul_attack": ["soul", "spirit", "spiritual", "soul manipulation"],
    "regeneration": ["regeneration", "regenerate", "healing factor", "heal rapidly"],
    "technology_hacking": ["hack", "hacking", "cyber", "network", "override"],
    "summoning": ["summon", "summoning", "familiar", "minion", "servant"],
}

SCOPE_DEPENDENCY_RULES = {
    "native_realm_only": ["native realm", "home realm", "own dimension"],
    "requires_artifact": ["artifact", "relic", "stone", "gem", "amulet"],
    "requires_contact": ["contact", "touch", "physical contact", "grab"],
    "requires_energy_source": ["energy source", "battery", "fuel", "mana"],
    "requires_summon": ["summon", "familiar", "servant", "minion"],
    "battlefield_dependent": ["battlefield", "terrain", "environment", "arena"],
    "dimensional_scope": ["dimension", "realm", "universe", "plane"],
    "range_limit": ["range", "distance", "meters", "kilometers", "line of sight"],
}


@dataclass(frozen=True)
class RosterRow:
    category: str
    franchise: str
    name: str
    aliases: list[str] = field(default_factory=list)
    wiki_title: str | None = None
    wiki_url: str | None = None


@dataclass
class HarvestResult:
    row: RosterRow
    output_path: Path | None
    status: str
    errors: list[str] = field(default_factory=list)


@dataclass
class QueueCycleSummary:
    roster_rows: int = 0
    completed: int = 0
    needs_review: int = 0
    pending: int = 0
    processed_this_cycle: int = 0
    generated_this_cycle: int = 0
    needs_review_this_cycle: int = 0
    failed_this_cycle: int = 0


class RawCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cooldowns_path = self.cache_dir / "_cooldowns.json"

    def cache_key(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> str:
        payload = {
            "method": method.upper(),
            "url": url,
            "params": params or {},
            "body": body,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def read(self, key: str) -> dict[str, Any] | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write(
        self,
        key: str,
        *,
        method: str,
        url: str,
        status: int,
        headers: dict[str, str],
        body: Any,
        source_type: str,
    ) -> dict[str, Any]:
        record = {
            "cache_key": key,
            "method": method.upper(),
            "url": url,
            "source_type": source_type,
            "status": status,
            "headers": dict(headers),
            "body": body,
            "retrieved_at": now_iso(),
            "response_hash": stable_hash(body),
        }
        self.path_for(key).write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        return record

    def load_cooldowns(self) -> dict[str, float]:
        if not self.cooldowns_path.exists():
            return {}
        return json.loads(self.cooldowns_path.read_text(encoding="utf-8"))

    def set_cooldown(self, host: str, until_epoch: float) -> None:
        cooldowns = self.load_cooldowns()
        cooldowns[host] = until_epoch
        self.cooldowns_path.write_text(json.dumps(cooldowns, indent=2, sort_keys=True), encoding="utf-8")

    async def wait_for_cooldown(self, host: str, min_interval: float) -> None:
        cooldowns = self.load_cooldowns()
        now = time.time()
        wait_until = max(cooldowns.get(host, 0), now + max(0, min_interval))
        wait_seconds = wait_until - now
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)


class HttpClient:
    def __init__(
        self,
        *,
        cache: RawCache,
        user_agent: str,
        min_interval_seconds: float,
        use_cache: bool,
    ) -> None:
        self.cache = cache
        self.user_agent = user_agent
        self.min_interval_seconds = min_interval_seconds
        self.use_cache = use_cache

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data_body: str | None = None,
        headers: dict[str, str] | None = None,
        source_type: str,
    ) -> dict[str, Any]:
        import aiohttp

        request_body = json_body if json_body is not None else data_body
        cache_key = self.cache.cache_key(method, url, params=params, body=request_body)
        cached = self.cache.read(cache_key)
        if cached and self.use_cache:
            return cached

        host = urlparse(url).netloc
        await self.cache.wait_for_cooldown(host, self.min_interval_seconds)

        request_headers = {"User-Agent": self.user_agent, **(headers or {})}
        timeout = aiohttp.ClientTimeout(total=8, connect=3, sock_connect=3, sock_read=5)
        async with aiohttp.ClientSession(headers=request_headers, timeout=timeout) as session:
            async with session.request(
                method,
                url,
                params=params,
                json=json_body,
                data=data_body,
            ) as response:
                text = await response.text()
                if response.status == 429:
                    retry_after = parse_retry_after(response.headers.get("Retry-After"))
                    self.cache.set_cooldown(host, time.time() + retry_after)
                try:
                    body = json.loads(text)
                except json.JSONDecodeError:
                    body = {"text": text}
                record = self.cache.write(
                    cache_key,
                    method=method,
                    url=str(response.url),
                    status=response.status,
                    headers=dict(response.headers),
                    body=body,
                    source_type=source_type,
                )
                if response.status >= 400:
                    raise RuntimeError(f"{source_type} request failed: HTTP {response.status}")
                return record


class ProfileHarvester:
    def __init__(
        self,
        *,
        http: HttpClient,
        mediawiki_api: str,
        output_dir: Path,
        needs_review_dir: Path,
        force: bool,
        debug_extract: bool,
    ) -> None:
        self.http = http
        self.mediawiki_api = mediawiki_api
        self.output_dir = output_dir
        self.needs_review_dir = needs_review_dir
        self.force = force
        self.debug_extract = debug_extract

    async def harvest_row(self, row: RosterRow) -> HarvestResult:
        errors: list[str] = []
        profile_path = profile_output_path(self.output_dir, row)
        review_path = profile_output_path(self.needs_review_dir, row)

        if not self.force and (profile_path.exists() or review_path.exists()):
            return HarvestResult(row=row, output_path=profile_path, status="skipped_existing")

        anilist_identity = await safe_call(
            lambda: self.fetch_anilist_identity(row),
            errors,
            f"AniList lookup failed for {row.name}",
        )
        igdb_identity = await safe_call(
            lambda: self.fetch_igdb_identity(row),
            errors,
            f"IGDB lookup failed for {row.name}",
        )
        wiki_source = await safe_call(
            lambda: self.fetch_mediawiki_source(row),
            errors,
            f"MediaWiki lookup failed for {row.name}",
        )

        profile = build_profile(
            row=row,
            anilist_identity=anilist_identity,
            igdb_identity=igdb_identity,
            wiki_source=wiki_source,
            errors=errors,
        )
        if self.debug_extract:
            print_extraction_debug(wiki_source, profile)

        destination = profile_path if profile["battle_eligible"] else review_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        profile["profile_hash"] = stable_hash_without_profile_hash(profile)
        write_yaml(destination, profile)
        return HarvestResult(row=row, output_path=destination, status=profile["status"], errors=errors)

    async def fetch_anilist_identity(self, row: RosterRow) -> dict[str, Any] | None:
        if row.category.lower() not in {"anime", "manga"}:
            return None
        query = """
        query($search: String) {
          Character(search: $search) {
            id
            name { full native alternative }
            image { large }
            siteUrl
            media(perPage: 10) {
              nodes {
                id
                type
                title { romaji english native }
                siteUrl
              }
            }
          }
        }
        """
        record = await self.http.request_json(
            "POST",
            ANILIST_GRAPHQL_URL,
            json_body={"query": query, "variables": {"search": row.name}},
            source_type="anilist",
        )
        return record["body"].get("data", {}).get("Character")

    async def fetch_igdb_identity(self, row: RosterRow) -> dict[str, Any] | None:
        if row.category.lower() != "game":
            return None

        client_id = os.getenv("IGDB_CLIENT_ID")
        access_token = os.getenv("IGDB_ACCESS_TOKEN")
        client_secret = os.getenv("IGDB_CLIENT_SECRET")
        if not client_id:
            return None
        if not access_token and client_secret:
            token_record = await self.http.request_json(
                "POST",
                IGDB_TOKEN_URL,
                params={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                },
                source_type="igdb_oauth",
            )
            access_token = token_record["body"].get("access_token")
        if not access_token:
            return None

        body = f'search "{row.name}"; fields name,slug,url; limit 5;'
        record = await self.http.request_json(
            "POST",
            IGDB_CHARACTER_URL,
            data_body=body,
            headers={
                "Client-ID": client_id,
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "text/plain",
            },
            source_type="igdb",
        )
        return record["body"][0] if isinstance(record["body"], list) and record["body"] else None

    async def fetch_mediawiki_source(self, row: RosterRow) -> dict[str, Any] | None:
        title = row.wiki_title or title_from_wiki_url(row.wiki_url) or row.name
        api_url = mediawiki_api_from_url(row.wiki_url) or self.mediawiki_api
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "revisions|info",
            "inprop": "url",
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "titles": title,
            "redirects": "1",
        }
        record = await self.http.request_json(
            "GET",
            api_url,
            params=params,
            source_type="mediawiki",
        )
        pages = record["body"].get("query", {}).get("pages", [])
        if not pages:
            return None
        page = pages[0]
        revision = first_revision(page)
        content = revision_content(revision)
        fields = extract_vsbattles_fields(content)
        parse_record = None
        parse_text = ""
        if count_core_fields(fields) < 3:
            try:
                parse_record = await self.fetch_mediawiki_parse(api_url, page.get("title") or title)
                parse_text = rendered_text_from_parse(parse_record["body"])
                parsed_fields = extract_vsbattles_fields(parse_text)
                fields = merge_extracted_fields(fields, parsed_fields)
            except Exception:
                parse_record = None
                parse_text = ""
        return {
            "source_id": source_id("mediawiki", page.get("pageid"), title),
            "title": page.get("title") or title,
            "full_url": page.get("fullurl") or row.wiki_url or "",
            "page_id": str(page.get("pageid") or ""),
            "revision_id": str(revision.get("revid") or ""),
            "revision_timestamp": revision.get("timestamp"),
            "retrieved_at": record["retrieved_at"],
            "cache_key": record["cache_key"],
            "parse_cache_key": parse_record["cache_key"] if parse_record else None,
            "api_url": api_url,
            "raw_content": content,
            "parse_text": parse_text,
            "fields": fields,
        }

    async def fetch_mediawiki_parse(self, api_url: str, title: str) -> dict[str, Any]:
        params = {
            "action": "parse",
            "page": title,
            "prop": "text|sections",
            "format": "json",
            "formatversion": "2",
        }
        return await self.http.request_json(
            "GET",
            api_url,
            params=params,
            source_type="mediawiki_parse",
        )


def build_profile(
    *,
    row: RosterRow,
    anilist_identity: dict[str, Any] | None,
    igdb_identity: dict[str, Any] | None,
    wiki_source: dict[str, Any] | None,
    errors: list[str],
) -> dict[str, Any]:
    extracted = wiki_source.get("fields", {}) if wiki_source else {}
    tags, scopes, dependencies = enrich_metadata(extracted)
    sources = build_sources(anilist_identity, igdb_identity, wiki_source)
    mediawiki_source_ids = [
        source["id"] for source in sources if source.get("source_type") == "mediawiki"
    ]
    claims = build_claims(extracted, sources)
    abilities = list_items_from_text(
        "powers_and_abilities",
        extracted.get("powers_and_abilities"),
        source_ids=mediawiki_source_ids,
        inherited_tags=tags,
        inherited_dependencies=dependencies,
        inherited_scope_limitations=scopes.get("scope_limitations", []),
    )
    equipment = list_items_from_text(
        "standard_equipment",
        extracted.get("standard_equipment"),
        source_ids=mediawiki_source_ids,
        inherited_tags=tags,
        inherited_dependencies=dependencies,
        inherited_scope_limitations=scopes.get("scope_limitations", []),
    )
    weaknesses = list_items_from_text(
        "weaknesses",
        extracted.get("weaknesses"),
        source_ids=mediawiki_source_ids,
        inherited_tags=tags,
        inherited_dependencies=dependencies,
        inherited_scope_limitations=scopes.get("scope_limitations", []),
    )
    required_power_count = sum(1 for field_name in REQUIRED_POWER_FIELDS if extracted.get(field_name))
    confidence = compute_confidence(
        required_power_count=required_power_count,
        has_abilities=bool(abilities),
        has_revision=has_revision(wiki_source),
    )
    ineligible_reasons = []
    if not has_revision(wiki_source):
        ineligible_reasons.append("missing_source_revision_metadata")
    for field_name in REQUIRED_POWER_FIELDS:
        if not extracted.get(field_name):
            ineligible_reasons.append(f"missing_{field_name}")
    if not abilities:
        ineligible_reasons.append("missing_powers_and_abilities")
    if confidence < 0.55:
        ineligible_reasons.append("confidence_below_0_55")

    battle_eligible = not ineligible_reasons
    now = now_iso()
    profile = {
        "schema_version": "1",
        "id": slugify(f"{row.category}-{row.franchise}-{row.name}"),
        "name": row.name,
        "franchise": row.franchise,
        "category": row.category,
        "aliases": row.aliases,
        "profile_type": "auto_evidence_profile" if battle_eligible else "needs_review",
        "status": "auto_generated" if battle_eligible else "needs_review",
        "battle_eligible": battle_eligible,
        "generation": {
            "generated_at": now,
            "generator": "battlebot.harvest.auto_profile_harvester",
            "confidence": confidence,
            "ineligible_reasons": ineligible_reasons,
        },
        "identity": build_identity(row, anilist_identity, igdb_identity),
        "canon_policy": {
            "default": "strongest_consistent_canonical_form",
            "composite_allowed": False,
        },
        "battle_policy": {
            "prepared": True,
            "standard_equipment": True,
            "standard_summons": True,
            "outside_help": False,
        },
        "variant": variant_metadata(row.name, slugify(f"{row.category}-{row.franchise}-{row.name}")),
        "forms": build_forms(extracted),
        "sources": sources,
        "power_scale": build_power_scale(extracted, mediawiki_source_ids, confidence),
        "claims": claims,
        "abilities": abilities,
        "equipment": equipment,
        "summons": [],
        "resistances": [],
        "weaknesses": weaknesses,
        "win_conditions": [],
        "loss_conditions": [],
        "battlefield_dependencies": scopes.get("battlefield_dependencies", []),
        "interaction_tags": tags,
        "resource_dependencies": dependencies,
        "scope_limitations": {
            "items": scopes.get("scope_limitations", []),
            "native_realm_only": "native_realm_only" in scopes.get("scope_limitations", []),
            "dimensional_scope": "dimensional_scope" in scopes.get("scope_limitations", []),
            "range_limit": "range_limit" in scopes.get("scope_limitations", []),
        },
        "review": {
            "ineligible_reasons": ineligible_reasons,
            "source_errors": errors,
            "notes": [],
        },
        "profile_hash": "",
    }
    return profile


def build_power_scale(
    extracted: dict[str, str],
    source_ids: list[str],
    profile_confidence: float,
) -> dict[str, dict[str, Any]]:
    return {
        field_name: {
            "text": extracted.get(field_name) or None,
            "source_ids": source_ids if extracted.get(field_name) else [],
            "confidence": profile_confidence if extracted.get(field_name) else 0.0,
        }
        for field_name in POWER_SCALE_FIELDS
    }


def build_sources(
    anilist_identity: dict[str, Any] | None,
    igdb_identity: dict[str, Any] | None,
    wiki_source: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    sources = []
    if anilist_identity:
        sources.append(
            {
                "id": source_id("anilist", anilist_identity.get("id"), anilist_identity.get("siteUrl")),
                "title": anilist_identity.get("name", {}).get("full") or "AniList Character",
                "url": anilist_identity.get("siteUrl"),
                "source_type": "anilist",
                "source_tier": "B",
                "page_id": str(anilist_identity.get("id") or ""),
                "revision_id": None,
                "revision_timestamp": None,
                "retrieved_at": None,
            }
        )
    if igdb_identity:
        sources.append(
            {
                "id": source_id("igdb", igdb_identity.get("id"), igdb_identity.get("url")),
                "title": igdb_identity.get("name") or "IGDB Character",
                "url": igdb_identity.get("url"),
                "source_type": "igdb",
                "source_tier": "B",
                "page_id": str(igdb_identity.get("id") or ""),
                "revision_id": None,
                "revision_timestamp": None,
                "retrieved_at": None,
            }
        )
    if wiki_source:
        sources.append(
            {
                "id": wiki_source["source_id"],
                "title": wiki_source["title"],
                "url": wiki_source["full_url"],
                "source_type": "mediawiki",
                "source_tier": "C",
                "page_id": wiki_source["page_id"],
                "revision_id": wiki_source["revision_id"],
                "revision_timestamp": wiki_source["revision_timestamp"],
                "retrieved_at": wiki_source["retrieved_at"],
                "raw_cache_key": wiki_source["cache_key"],
            }
        )
    return sources


def build_identity(
    row: RosterRow,
    anilist_identity: dict[str, Any] | None,
    igdb_identity: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "canonical_name": row.name,
        "franchise": row.franchise,
        "category": row.category,
        "aliases": row.aliases,
        "external_ids": {
            "anilist": str(anilist_identity.get("id")) if anilist_identity else None,
            "igdb": str(igdb_identity.get("id")) if igdb_identity else None,
        },
    }


def build_forms(extracted: dict[str, str]) -> list[dict[str, Any]]:
    keys = split_listish(extracted.get("keys")) or ["Strongest consistent canonical form"]
    return [
        {
            "id": slugify(key),
            "name": key,
            "source_field": "keys" if extracted.get("keys") else None,
        }
        for key in keys
    ]


def build_claims(extracted: dict[str, str], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids = [source["id"] for source in sources if source["source_type"] == "mediawiki"]
    claims = []
    for field_name in (
        "tier",
        "attack_potency",
        "speed",
        "lifting_strength",
        "striking_strength",
        "durability",
        "stamina",
        "range",
        "standard_equipment",
        "intelligence",
        "weaknesses",
        "powers_and_abilities",
    ):
        text = extracted.get(field_name)
        if not text:
            continue
        claims.append(
            {
                "id": slugify(f"claim-{field_name}-{stable_hash(text)[:8]}"),
                "section": section_for_field(field_name),
                "axis": axis_for_field(field_name),
                "text": text,
                "source_ids": source_ids,
                "decisive": field_name in CORE_FIELDS,
                "status": "unverified",
                "policy_flags": ["fan_wiki_single_source"] if source_ids else ["missing_source"],
            }
        )
    return claims


def enrich_metadata(extracted: dict[str, str]) -> tuple[list[str], dict[str, list[str]], list[str]]:
    searchable = "\n".join(value for value in extracted.values() if value).lower()
    tags = sorted(tag for tag, keywords in KEYWORD_RULES.items() if any(k in searchable for k in keywords))
    scope_items = sorted(
        scope for scope, keywords in SCOPE_DEPENDENCY_RULES.items() if any(k in searchable for k in keywords)
    )
    dependencies = sorted(
        item
        for item in scope_items
        if item
        in {
            "requires_artifact",
            "requires_contact",
            "requires_energy_source",
            "requires_summon",
        }
    )
    scopes = {
        "scope_limitations": [
            item
            for item in scope_items
            if item
            in {
                "native_realm_only",
                "dimensional_scope",
                "range_limit",
            }
        ],
        "battlefield_dependencies": [
            item for item in scope_items if item == "battlefield_dependent"
        ],
    }
    return tags, scopes, dependencies


def extract_vsbattles_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    fields.update(extract_template_pipe_fields(content))
    light_text = light_markup_to_text(content)
    fields.update({k: v for k, v in extract_inline_labeled_fields(light_text).items() if k not in fields})
    fields.update({k: v for k, v in extract_delimiterless_labeled_fields(light_text).items() if k not in fields})
    text = strip_markup(content)
    fields.update({k: v for k, v in extract_inline_labeled_fields(text).items() if k not in fields})
    fields.update({k: v for k, v in extract_delimiterless_labeled_fields(text).items() if k not in fields})
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        parsed = parse_field_line(line)
        if parsed:
            key, value = parsed
            fields.setdefault(key, value)
            continue
        header = normalize_field_name(line)
        canonical = field_alias(header)
        if canonical and index + 1 < len(lines):
            fields.setdefault(canonical, lines[index + 1])
    section_fields = extract_section_fields(content)
    for key, value in section_fields.items():
        if key not in fields or (key == "powers_and_abilities" and len(value) > len(fields.get(key, ""))):
            fields[key] = value
    return fields


def parse_field_line(line: str) -> tuple[str, str] | None:
    clean = clean_label_line(line)
    match = re.match(r"^\|?\s*(?P<key>[A-Za-z _&/&().-]+?)\s*(?:=|:|：)\s*(?P<value>.+)$", clean)
    if not match:
        return None
    key = normalize_field_name(match.group("key"))
    value = normalize_text(match.group("value"))
    canonical = field_alias(key)
    if not canonical or not value:
        return None
    return canonical, value


def extract_template_pipe_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^\s*\|\s*(?P<key>[^=|]+?)\s*=\s*(?P<value>.*)$", line)
        if match:
            flush_multiline_field(fields, current_key, current_value)
            current_key = field_alias(match.group("key"))
            current_value = [match.group("value").strip()] if current_key else []
            continue
        if current_key:
            if re.match(r"^\s*[|}]", line):
                flush_multiline_field(fields, current_key, current_value)
                current_key = None
                current_value = []
            else:
                current_value.append(line.strip())
    flush_multiline_field(fields, current_key, current_value)
    return fields


def flush_multiline_field(
    fields: dict[str, str],
    current_key: str | None,
    current_value: list[str],
) -> None:
    if not current_key:
        return
    value = normalize_text(strip_markup("\n".join(current_value)))
    if value:
        fields[current_key] = value


def extract_section_fields(content: str) -> dict[str, str]:
    text = strip_markup(content)
    section_pattern = re.compile(
        r"(?im)^\s*=+\s*(?P<title>[^=\n]+?)\s*=+\s*$"
    )
    matches = list(section_pattern.finditer(text))
    fields: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = normalize_field_name(match.group("title"))
        canonical = field_alias(title)
        if not canonical:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = first_useful_section_text(text[start:end])
        if value:
            fields[canonical] = value
    return fields


def extract_inline_labeled_fields(text: str) -> dict[str, str]:
    aliases = sorted(FIELD_ALIASES.keys(), key=len, reverse=True)
    label_pattern = "|".join(re.escape(alias) for alias in aliases)
    pattern = re.compile(
        rf"(?i)(?P<label>{label_pattern})\s*(?:=|:|：)"
    )
    matches = list(pattern.finditer(text))
    fields: dict[str, str] = {}
    for index, match in enumerate(matches):
        if inline_match_is_heading(text, match):
            continue
        label = normalize_field_name(match.group("label"))
        canonical = field_alias(label)
        if not canonical:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = normalize_extracted_value(text[start:end])
        if value and not fields.get(canonical):
            fields[canonical] = value
    return fields


def extract_delimiterless_labeled_fields(text: str) -> dict[str, str]:
    label_pattern = "|".join(re.escape(label) for label in sorted(DELIMITERLESS_FIELD_LABELS, key=len, reverse=True))
    pattern = re.compile(rf"\b(?P<label>{label_pattern})\b(?:(?:\s*(?:=|:|：)\s*)|\s+)")
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return {}

    accepted: list[tuple[re.Match[str], str]] = []
    for match in matches:
        canonical = field_alias(match.group("label"))
        if not canonical:
            continue
        if not accepted:
            prefix = text[max(0, match.start() - 3):match.start()].rstrip()
            if match.start() != 0 and not re.search(r"[\n|}=]$", prefix):
                continue
        elif canonical == accepted[-1][1]:
            continue
        accepted.append((match, canonical))

    fields: dict[str, str] = {}
    for index, (match, canonical) in enumerate(accepted):
        start = match.end()
        end = accepted[index + 1][0].start() if index + 1 < len(accepted) else len(text)
        value = normalize_extracted_value(text[start:end])
        if value and not fields.get(canonical):
            fields[canonical] = value
    return fields


def inline_match_is_heading(text: str, match: re.Match[str]) -> bool:
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    prefix = text[line_start:match.start()].strip()
    suffix = text[match.end():line_end].strip()
    return bool(prefix) and set(prefix) == {"="} and suffix.startswith("=")


def merge_extracted_fields(primary: dict[str, str], fallback: dict[str, str]) -> dict[str, str]:
    merged = dict(primary)
    for key, value in fallback.items():
        if value and not merged.get(key):
            merged[key] = value
    return merged


def count_core_fields(fields: dict[str, str]) -> int:
    return sum(1 for field_name in CORE_FIELDS if fields.get(field_name))


def clean_label_line(line: str) -> str:
    clean = line.strip()
    clean = re.sub(r"^\*+\s*", "", clean)
    clean = re.sub(r"^['=*#:\s]+|['=*#:\s]+$", "", clean)
    clean = clean.replace("'''", "").replace("''", "")
    return clean.strip()


def strip_markup(content: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|li|tr|div|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = text.replace("'''", "").replace("''", "")
    return text


def light_markup_to_text(content: str) -> str:
    text = re.sub(r"<ref[^/>]*/>", "", content, flags=re.IGNORECASE)
    text = re.sub(r"</?ref[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|li|tr|div|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[(?:https?://[^\s\]]+)\s+([^\]]+)\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    return text


def normalize_field_name(value: str) -> str:
    value = value.strip().lower().replace("_", " ")
    value = value.replace("&amp;", "&")
    value = re.sub(r"['*|=\[\]{}]", " ", value)
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\s*&\s*", " & ", value)
    return re.sub(r"\s+", " ", value).strip()


def field_alias(value: str) -> str | None:
    normalized = normalize_field_name(value)
    canonical = FIELD_ALIASES.get(normalized)
    if canonical:
        return canonical
    slash_spaced = normalized.replace("/", " / ")
    canonical = FIELD_ALIASES.get(re.sub(r"\s+", " ", slash_spaced).strip())
    if canonical:
        return canonical
    ampersand_expanded = normalized.replace(" & ", " and ")
    return FIELD_ALIASES.get(re.sub(r"\s+", " ", ampersand_expanded).strip())


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_extracted_value(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"^\s*(?:[-|=]+|▾)+\s*", "", value)
    value = re.sub(r"\s*(?:[-|=]+|▾)+\s*$", "", value)
    return value[:5000].strip()


def first_useful_section_text(value: str) -> str:
    text = normalize_extracted_value(value)
    if not text:
        return ""
    stop = re.search(r"(?i)\b(?:gallery|notable matchups|references|notes/explanations)\b", text)
    if stop:
        text = text[:stop.start()].strip()
    if text.casefold() in {"none", "n/a", "not applicable"}:
        return ""
    return text


def list_items_from_text(
    kind: str,
    text: str | None,
    *,
    source_ids: list[str],
    inherited_tags: list[str],
    inherited_dependencies: list[str],
    inherited_scope_limitations: list[str],
) -> list[dict[str, Any]]:
    if not text:
        return []
    pieces = split_listish(text)
    return [
        {
            "id": slugify(f"{kind}-{piece}")[:80],
            "name": piece[:120],
            "description": piece,
            "source_ids": source_ids,
            "source_claim_ids": [],
            "confidence": 0.85 if source_ids else 0.5,
            "tags": tags_for_text(piece, inherited_tags),
            "targets": [],
            "activation_requirements": [],
            "counters": [],
            "resource_dependencies": dependencies_for_text(piece, inherited_dependencies),
            "scope_limitations": scope_limitations_for_text(piece, inherited_scope_limitations),
            "enrichment": {
                "method": "deterministic_keyword_rules",
                "metadata_only": True,
            },
        }
        for piece in pieces[:40]
    ]


def split_listish(text: str | None) -> list[str]:
    if not text:
        return []
    parts = re.split(r"\s*(?:\||;|,|\n|\u2022)\s*", text)
    return [normalize_text(part) for part in parts if normalize_text(part)]


def tags_for_text(text: str, inherited_tags: list[str]) -> list[str]:
    lowered = text.lower()
    local_tags = [
        tag
        for tag, keywords in KEYWORD_RULES.items()
        if any(keyword in lowered for keyword in keywords)
    ]
    return sorted(set(local_tags) | set(inherited_tags))


def dependencies_for_text(text: str, inherited_dependencies: list[str]) -> list[str]:
    lowered = text.lower()
    local_dependencies = [
        dependency
        for dependency, keywords in SCOPE_DEPENDENCY_RULES.items()
        if dependency.startswith("requires_") and any(keyword in lowered for keyword in keywords)
    ]
    return sorted(set(local_dependencies) | set(inherited_dependencies))


def scope_limitations_for_text(text: str, inherited_scope_limitations: list[str]) -> list[str]:
    lowered = text.lower()
    local_scopes = [
        scope
        for scope, keywords in SCOPE_DEPENDENCY_RULES.items()
        if scope in {"native_realm_only", "dimensional_scope", "range_limit"}
        and any(keyword in lowered for keyword in keywords)
    ]
    return sorted(set(local_scopes) | set(inherited_scope_limitations))


def compute_confidence(
    *,
    required_power_count: int,
    has_abilities: bool,
    has_revision: bool,
) -> float:
    core_count = required_power_count + int(has_abilities)
    score = 0.1 + (0.15 * core_count)
    if has_revision:
        score += 0.25
    if core_count == 0:
        score = min(score, 0.35)
    return round(min(score, 0.95), 2)


def rendered_text_from_parse(parse_body: dict[str, Any]) -> str:
    parse_data = parse_body.get("parse", {})
    html = parse_data.get("text") or ""
    if isinstance(html, dict):
        html = html.get("*", "")
    return strip_markup(str(html))


def has_revision(wiki_source: dict[str, Any] | None) -> bool:
    return bool(wiki_source and wiki_source.get("revision_id") and wiki_source.get("revision_timestamp"))


def first_revision(page: dict[str, Any]) -> dict[str, Any]:
    revisions = page.get("revisions") or []
    return revisions[0] if revisions else {}


def revision_content(revision: dict[str, Any]) -> str:
    slots = revision.get("slots") or {}
    main = slots.get("main") or {}
    return (
        main.get("content")
        or main.get("*")
        or revision.get("content")
        or revision.get("*")
        or ""
    )


def source_id(source_type: str, stable_id: Any, fallback: Any) -> str:
    raw = f"{source_type}:{stable_id or fallback}"
    return slugify(raw)[:96]


def section_for_field(field_name: str) -> str:
    if field_name in {"standard_equipment"}:
        return "equipment"
    if field_name == "weaknesses":
        return "weaknesses"
    if field_name == "powers_and_abilities":
        return "abilities"
    return "power_scale"


def axis_for_field(field_name: str) -> str:
    return {
        "attack_potency": "attack",
        "speed": "speed",
        "durability": "durability",
        "standard_equipment": "equipment",
        "powers_and_abilities": "hax",
        "weaknesses": "weakness",
        "range": "range",
        "stamina": "stamina",
        "intelligence": "battle_iq",
    }.get(field_name, "other")


def mediawiki_api_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.path.endswith("/api.php"):
        return url
    if "api.php" in parsed.path:
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return None


def title_from_wiki_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "title" in params and params["title"]:
        return params["title"][0].replace("_", " ")
    last = parsed.path.rstrip("/").split("/")[-1]
    if not last or last == "api.php":
        return None
    return unquote(last).replace("_", " ")


def profile_output_path(base_dir: Path, row: RosterRow) -> Path:
    return (
        base_dir
        / slugify(row.category)
        / slugify(row.franchise)
        / f"{slugify(row.name)}.yaml"
    )


def character_row_id(row: RosterRow) -> str:
    return slugify(f"{row.category}-{row.franchise}-{row.name}")


def row_fingerprint(row: RosterRow) -> str:
    return stable_hash(
        {
            "category": row.category,
            "franchise": row.franchise,
            "name": row.name,
            "aliases": row.aliases,
            "wiki_title": row.wiki_title,
            "wiki_url": row.wiki_url,
        }
    )


def roster_state_key(input_path: Path | None, roster_id: str | None) -> str:
    path_key = input_path.resolve().as_posix() if input_path else "single-character"
    return f"{roster_id or 'default'}::{path_key}"


def empty_roster_state() -> dict[str, Any]:
    return {
        "cursor_index": 0,
        "completed": {},
        "needs_review": {},
        "failed": {},
        "last_processed_at": None,
    }


def load_json_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_state_atomic(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def get_roster_state(
    state: dict[str, Any],
    *,
    input_path: Path | None,
    roster_id: str | None,
) -> tuple[str, dict[str, Any]]:
    key = roster_state_key(input_path, roster_id)
    rosters = state.setdefault("rosters", {})
    roster_state = rosters.setdefault(key, empty_roster_state())
    for field_name, default in empty_roster_state().items():
        roster_state.setdefault(field_name, default)
    return key, roster_state


def reset_roster_state(
    state: dict[str, Any],
    *,
    input_path: Path | None,
    roster_id: str | None,
) -> None:
    state.setdefault("rosters", {}).pop(roster_state_key(input_path, roster_id), None)


def row_is_done(
    row: RosterRow,
    *,
    output_dir: Path,
    needs_review_dir: Path,
    roster_state: dict[str, Any],
    skip_needs_review_existing: bool,
) -> tuple[bool, str | None]:
    row_id = character_row_id(row)
    fingerprint = row_fingerprint(row)
    if profile_output_path(output_dir, row).exists():
        roster_state.setdefault("completed", {})[row_id] = fingerprint
        return True, "completed"
    if skip_needs_review_existing and profile_output_path(needs_review_dir, row).exists():
        roster_state.setdefault("needs_review", {})[row_id] = fingerprint
        return True, "needs_review"
    if roster_state.get("completed", {}).get(row_id) == fingerprint:
        return True, "completed"
    if (
        skip_needs_review_existing
        and roster_state.get("needs_review", {}).get(row_id) == fingerprint
    ):
        return True, "needs_review"
    return False, None


def queue_summary_for_rows(
    rows: list[RosterRow],
    *,
    output_dir: Path,
    needs_review_dir: Path,
    roster_state: dict[str, Any],
    skip_needs_review_existing: bool,
) -> QueueCycleSummary:
    summary = QueueCycleSummary(roster_rows=len(rows))
    for row in rows:
        done, done_type = row_is_done(
            row,
            output_dir=output_dir,
            needs_review_dir=needs_review_dir,
            roster_state=roster_state,
            skip_needs_review_existing=skip_needs_review_existing,
        )
        if done_type == "completed":
            summary.completed += 1
        elif done_type == "needs_review":
            summary.needs_review += 1
        if not done:
            summary.pending += 1
    return summary


def select_queue_rows(
    rows: list[RosterRow],
    *,
    output_dir: Path,
    needs_review_dir: Path,
    roster_state: dict[str, Any],
    skip_needs_review_existing: bool,
    max_per_cycle: int,
) -> tuple[list[tuple[int, RosterRow]], QueueCycleSummary]:
    selected: list[tuple[int, RosterRow]] = []
    start_index = min(int(roster_state.get("cursor_index", 0) or 0), len(rows))
    index = start_index
    limit = max_per_cycle if max_per_cycle and max_per_cycle > 0 else len(rows)

    while index < len(rows) and len(selected) < limit:
        row = rows[index]
        done, _done_type = row_is_done(
            row,
            output_dir=output_dir,
            needs_review_dir=needs_review_dir,
            roster_state=roster_state,
            skip_needs_review_existing=skip_needs_review_existing,
        )
        index += 1
        if done:
            continue
        selected.append((index - 1, row))

    roster_state["cursor_index"] = index
    summary = queue_summary_for_rows(
        rows,
        output_dir=output_dir,
        needs_review_dir=needs_review_dir,
        roster_state=roster_state,
        skip_needs_review_existing=skip_needs_review_existing,
    )
    return selected, summary


def mark_queue_result(
    roster_state: dict[str, Any],
    row: RosterRow,
    result: HarvestResult,
) -> None:
    row_id = character_row_id(row)
    fingerprint = row_fingerprint(row)
    if result.errors:
        failed = roster_state.setdefault("failed", {}).setdefault(row_id, {})
        failed["fingerprint"] = fingerprint
        failed["error_count"] = int(failed.get("error_count", 0)) + 1
        failed["last_error"] = "; ".join(result.errors)
    if result.status == "auto_generated":
        roster_state.setdefault("completed", {})[row_id] = fingerprint
        roster_state.setdefault("failed", {}).pop(row_id, None)
    elif result.status == "needs_review":
        roster_state.setdefault("needs_review", {})[row_id] = fingerprint
    roster_state["last_processed_at"] = now_iso()


def print_queue_summary(summary: QueueCycleSummary) -> None:
    print("QUEUE SUMMARY")
    print(f"  roster_rows: {summary.roster_rows}")
    print(f"  completed: {summary.completed}")
    print(f"  needs_review: {summary.needs_review}")
    print(f"  pending: {summary.pending}")
    print(f"  processed_this_cycle: {summary.processed_this_cycle}")
    print(f"  generated_this_cycle: {summary.generated_this_cycle}")
    print(f"  needs_review_this_cycle: {summary.needs_review_this_cycle}")
    print(f"  failed_this_cycle: {summary.failed_this_cycle}")


def read_roster_csv(path: Path) -> list[RosterRow]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            name = (raw.get("name") or "").strip()
            if not name:
                continue
            aliases = [
                alias.strip()
                for alias in (raw.get("aliases") or "").split("|")
                if alias.strip()
            ]
            rows.append(
                RosterRow(
                    category=(raw.get("category") or "unknown").strip(),
                    franchise=(raw.get("franchise") or "unknown").strip(),
                    name=name,
                    aliases=aliases,
                    wiki_title=(raw.get("wiki_title") or "").strip() or None,
                    wiki_url=(raw.get("wiki_url") or "").strip() or None,
                )
            )
    return rows


def single_row_from_args(args: argparse.Namespace) -> RosterRow:
    aliases = [alias.strip() for alias in (args.aliases or "").split("|") if alias.strip()]
    return RosterRow(
        category=args.category,
        franchise=args.franchise,
        name=args.character,
        aliases=aliases,
        wiki_title=args.wiki_title,
        wiki_url=args.wiki_url,
    )


async def safe_call(coro_factory, errors: list[str], message: str):
    try:
        return await coro_factory()
    except Exception as exc:
        errors.append(f"{message}: {exc}")
        return None


def parse_retry_after(value: str | None) -> float:
    if not value:
        return 60.0
    try:
        return max(float(value), 1.0)
    except ValueError:
        return 60.0


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
    ).hexdigest()


def stable_hash_without_profile_hash(profile: dict[str, Any]) -> str:
    clone = json.loads(json.dumps(profile, sort_keys=True, default=str))
    clone["profile_hash"] = ""
    return stable_hash(clone)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    validate = CharacterProfile.model_validate if data.get("battle_eligible") else None
    yaml_io.write_yaml(
        path,
        data,
        validate=validate,
        width=100,
    )


def print_extraction_debug(wiki_source: dict[str, Any] | None, profile: dict[str, Any]) -> None:
    print("[debug-extract]", flush=True)
    if not wiki_source:
        print("  selected_title: <none>", flush=True)
        print("  revision_id: <none>", flush=True)
        print("  extracted_fields: []", flush=True)
        print(f"  eligibility_reasons: {profile['generation']['ineligible_reasons']}", flush=True)
        return
    raw_content = wiki_source.get("raw_content") or ""
    print(f"  selected_title: {wiki_source.get('title')}", flush=True)
    print(f"  revision_id: {wiki_source.get('revision_id')}", flush=True)
    for needle in (
        "Tier",
        "Attack Potency",
        "Speed",
        "Durability",
        "Powers and Abilities",
        "Standard Equipment",
        "Weaknesses",
    ):
        print(f"  contains_{slugify(needle)}: {needle in raw_content}", flush=True)
    print(f"  extracted_fields: {sorted((wiki_source.get('fields') or {}).keys())}", flush=True)
    print(f"  eligibility_reasons: {profile['generation']['ineligible_reasons']}", flush=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate enriched character YAML profiles")
    parser.add_argument("--input", type=Path, help="Roster CSV path")
    parser.add_argument("--character", help="Single character name")
    parser.add_argument("--category", default="unknown", help="Single-character category")
    parser.add_argument("--franchise", default="unknown", help="Single-character franchise")
    parser.add_argument("--aliases", default="", help="Pipe-separated aliases for single-character mode")
    parser.add_argument("--wiki-title", help="MediaWiki page title for single-character mode")
    parser.add_argument("--wiki-url", help="MediaWiki page URL or api.php URL")
    parser.add_argument("--mediawiki-api", default=DEFAULT_MEDIAWIKI_API)
    parser.add_argument("--output", type=Path, default=Path("profiles/generated"))
    parser.add_argument("--needs-review", type=Path, default=Path("profiles/needs_review"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    parser.add_argument("--state-file", type=Path, default=Path("data/harvest_state.json"))
    parser.add_argument("--queue-mode", action="store_true", help="Process roster rows as a durable queue")
    parser.add_argument("--quiet-skips", action="store_true", help="Do not print skipped_existing rows")
    parser.add_argument(
        "--skip-needs-review-existing",
        action="store_true",
        help="Treat existing needs_review profiles as completed queue items",
    )
    parser.add_argument("--max-total", type=int, default=0, help="Stop after this many pending rows")
    parser.add_argument("--reset-state", action="store_true", help="Reset this roster queue state")
    parser.add_argument("--roster-id", help="Optional stable roster identifier for queue state")
    parser.add_argument("--force", action="store_true", help="Regenerate existing profiles")
    parser.add_argument("--no-cache", action="store_true", help="Ignore existing raw response cache")
    parser.add_argument("--debug-extract", action="store_true", help="Print MediaWiki extraction details")
    parser.add_argument("--loop", action="store_true", help="Keep processing the roster forever")
    parser.add_argument("--idle-sleep", type=float, default=120)
    parser.add_argument("--max-per-cycle", type=int, default=0)
    return parser


async def run_once(args: argparse.Namespace) -> list[HarvestResult]:
    if args.input:
        rows = read_roster_csv(args.input)
    elif args.character:
        rows = [single_row_from_args(args)]
    else:
        raise SystemExit("--input or --character is required")

    if args.max_per_cycle and args.max_per_cycle > 0:
        rows = rows[: args.max_per_cycle]

    cache = RawCache(args.cache_dir)
    http = HttpClient(
        cache=cache,
        user_agent=os.getenv("HARVEST_USER_AGENT", "ai-nerd-fight-bot/0.1"),
        min_interval_seconds=float(os.getenv("HARVEST_MIN_INTERVAL_SECONDS", "2")),
        use_cache=not args.no_cache,
    )
    harvester = ProfileHarvester(
        http=http,
        mediawiki_api=args.mediawiki_api,
        output_dir=args.output,
        needs_review_dir=args.needs_review,
        force=args.force,
        debug_extract=args.debug_extract,
    )
    results = []
    for row in rows:
        result = await harvester.harvest_row(row)
        results.append(result)
        where = result.output_path.as_posix() if result.output_path else "-"
        if not (args.quiet_skips and result.status == "skipped_existing"):
            print(f"{result.status}: {row.name} -> {where}", flush=True)
        for error in result.errors:
            print(f"  warning: {error}", flush=True)
    return results


async def run_queue_once(args: argparse.Namespace, processed_total: int) -> tuple[list[HarvestResult], int]:
    if not args.input:
        raise SystemExit("--queue-mode requires --input")

    rows = read_roster_csv(args.input)
    state = load_json_state(args.state_file)
    if args.reset_state:
        reset_roster_state(state, input_path=args.input, roster_id=args.roster_id)
        args.reset_state = False
    _key, roster_state = get_roster_state(state, input_path=args.input, roster_id=args.roster_id)

    if int(roster_state.get("cursor_index", 0) or 0) >= len(rows):
        summary = queue_summary_for_rows(
            rows,
            output_dir=args.output,
            needs_review_dir=args.needs_review,
            roster_state=roster_state,
            skip_needs_review_existing=args.skip_needs_review_existing,
        )
        print_queue_summary(summary)
        write_json_state_atomic(args.state_file, state)
        return [], processed_total

    selected, summary = select_queue_rows(
        rows,
        output_dir=args.output,
        needs_review_dir=args.needs_review,
        roster_state=roster_state,
        skip_needs_review_existing=args.skip_needs_review_existing,
        max_per_cycle=args.max_per_cycle,
    )
    if args.max_total and args.max_total > 0:
        remaining = max(args.max_total - processed_total, 0)
        selected = selected[:remaining]

    cache = RawCache(args.cache_dir)
    http = HttpClient(
        cache=cache,
        user_agent=os.getenv("HARVEST_USER_AGENT", "ai-nerd-fight-bot/0.1"),
        min_interval_seconds=float(os.getenv("HARVEST_MIN_INTERVAL_SECONDS", "2")),
        use_cache=not args.no_cache,
    )
    harvester = ProfileHarvester(
        http=http,
        mediawiki_api=args.mediawiki_api,
        output_dir=args.output,
        needs_review_dir=args.needs_review,
        force=args.force,
        debug_extract=args.debug_extract,
    )

    results = []
    for _index, row in selected:
        result = await harvester.harvest_row(row)
        results.append(result)
        mark_queue_result(roster_state, row, result)
        summary.processed_this_cycle += 1
        if result.status == "auto_generated":
            summary.generated_this_cycle += 1
        elif result.status == "needs_review":
            summary.needs_review_this_cycle += 1
        if result.errors:
            summary.failed_this_cycle += 1
        where = result.output_path.as_posix() if result.output_path else "-"
        if not (args.quiet_skips and result.status == "skipped_existing"):
            print(f"{result.status}: {row.name} -> {where}", flush=True)
        for error in result.errors:
            print(f"  warning: {error}", flush=True)

    processed_total += len(selected)
    final_summary = queue_summary_for_rows(
        rows,
        output_dir=args.output,
        needs_review_dir=args.needs_review,
        roster_state=roster_state,
        skip_needs_review_existing=args.skip_needs_review_existing,
    )
    final_summary.processed_this_cycle = summary.processed_this_cycle
    final_summary.generated_this_cycle = summary.generated_this_cycle
    final_summary.needs_review_this_cycle = summary.needs_review_this_cycle
    final_summary.failed_this_cycle = summary.failed_this_cycle
    print_queue_summary(final_summary)
    write_json_state_atomic(args.state_file, state)
    return results, processed_total


async def async_main(args: argparse.Namespace) -> None:
    processed_total = 0
    while True:
        if args.queue_mode:
            _results, processed_total = await run_queue_once(args, processed_total)
        else:
            results = await run_once(args)
            processed_total += len([result for result in results if result.status != "skipped_existing"])
        if args.max_total and args.max_total > 0 and processed_total >= args.max_total:
            return
        if not args.loop:
            return
        await asyncio.sleep(args.idle_sleep)


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
