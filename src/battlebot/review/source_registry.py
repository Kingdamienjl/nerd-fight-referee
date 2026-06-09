"""Source provider registry for review auto-repair."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import yaml

from battlebot.review import service


DEFAULT_REGISTRY_PATH = Path("profiles/overrides/source_registry.yaml")


@dataclass(frozen=True)
class SourceProvider:
    provider_id: str
    enabled: bool
    authority: str
    parser: str
    domains: tuple[str, ...] = ()
    allowed_fields: tuple[str, ...] = ()
    promotion_allowed: bool = False
    notes: str = ""
    local_path: str = ""
    requires_api_key_env: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def primary_domain(self) -> str:
        return self.domains[0] if self.domains else ""

    @property
    def is_high_authority_promotion_source(self) -> bool:
        return self.enabled and self.authority == "high" and self.promotion_allowed


def load_registry(path: Path | str = DEFAULT_REGISTRY_PATH) -> dict[str, SourceProvider]:
    registry_path = Path(path)
    if not registry_path.exists():
        return {}
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    providers = data.get("providers") or {}
    loaded: dict[str, SourceProvider] = {}
    for provider_id, raw in providers.items():
        if not isinstance(raw, dict):
            continue
        loaded[str(provider_id)] = SourceProvider(
            provider_id=str(provider_id),
            enabled=bool(raw.get("enabled")),
            authority=str(raw.get("authority") or "low"),
            parser=str(raw.get("parser") or "stub"),
            domains=tuple(str(domain) for domain in raw.get("domains") or []),
            allowed_fields=tuple(str(field) for field in raw.get("allowed_fields") or []),
            promotion_allowed=bool(raw.get("promotion_allowed")),
            notes=str(raw.get("notes") or ""),
            local_path=str(raw.get("local_path") or ""),
            requires_api_key_env=str(raw.get("requires_api_key_env") or ""),
            raw=dict(raw),
        )
    return loaded


def enabled_providers(
    provider_ids: list[str] | None = None,
    *,
    registry_path: Path | str = DEFAULT_REGISTRY_PATH,
) -> dict[str, SourceProvider]:
    providers = load_registry(registry_path)
    if provider_ids:
        requested = {provider_id.strip() for provider_id in provider_ids if provider_id.strip()}
        providers = {key: provider for key, provider in providers.items() if key in requested}
    return {key: provider for key, provider in providers.items() if provider.enabled}


def provider_for_url(
    url: str,
    providers: dict[str, SourceProvider] | None = None,
) -> SourceProvider | None:
    parsed = urlparse(url)
    netloc = parsed.netloc.casefold()
    for provider in (providers or enabled_providers()).values():
        if any(domain.casefold() in netloc for domain in provider.domains):
            return provider
    return None


def mediawiki_candidate_for_provider(
    provider: SourceProvider,
    title: str,
    *,
    notes: str,
) -> dict[str, Any]:
    url_title = quote(title.replace(" ", "_"))
    return {
        "id": service.slugify(f"{provider.provider_id}-{title}"),
        "title": title,
        "url": f"https://{provider.primary_domain}/wiki/{url_title}",
        "source_type": "mediawiki",
        "notes": notes,
        "provider_id": provider.provider_id,
        "authority": provider.authority,
        "promotion_allowed": provider.promotion_allowed,
        "allowed_fields": list(provider.allowed_fields),
        "parser": provider.parser,
    }


def candidate_titles_for_profile(profile: dict[str, Any]) -> list[str]:
    name = str(profile.get("name") or "")
    franchise = str(profile.get("franchise") or "")
    category = str(profile.get("category") or "")
    titles: list[str] = []
    if name:
        titles.append(name)
        if franchise:
            titles.append(f"{name} ({franchise})")
        if category:
            titles.append(f"{name} ({category})")
    seen = set()
    unique = []
    for title in titles:
        key = title.casefold()
        if key not in seen:
            unique.append(title)
            seen.add(key)
    return unique


def provider_candidates(
    profile: dict[str, Any],
    providers: dict[str, SourceProvider],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    titles = candidate_titles_for_profile(profile)
    for provider in providers.values():
        if provider.parser in {"mediawiki_battle_stats", "mediawiki_ability_taxonomy"} and provider.primary_domain:
            for title in titles:
                candidates.append(
                    mediawiki_candidate_for_provider(
                        provider,
                        title,
                        notes=f"{provider.provider_id}_candidate",
                    )
                )
    return candidates


def field_permission_name(field_name: str) -> str:
    if field_name == "powers_and_abilities":
        return "abilities"
    if field_name == "standard_equipment":
        return "equipment"
    return field_name


def filter_allowed_fields(fields: dict[str, str], provider: SourceProvider | None) -> dict[str, str]:
    if provider is None:
        return fields
    allowed = set(provider.allowed_fields)
    return {
        field_name: value
        for field_name, value in fields.items()
        if field_permission_name(field_name) in allowed
    }


def format_provider_list(providers: dict[str, SourceProvider]) -> str:
    if not providers:
        return "No enabled providers found."
    return "\n".join(
        f"{provider.provider_id} | enabled={provider.enabled} | authority={provider.authority} | "
        f"parser={provider.parser} | promotion_allowed={provider.promotion_allowed}"
        for provider in providers.values()
    )


def format_provider_explanation(provider: SourceProvider | None) -> str:
    if provider is None:
        return "Provider not found."
    return yaml.safe_dump(
        {
            "provider_id": provider.provider_id,
            "enabled": provider.enabled,
            "authority": provider.authority,
            "parser": provider.parser,
            "domains": list(provider.domains),
            "allowed_fields": list(provider.allowed_fields),
            "promotion_allowed": provider.promotion_allowed,
            "notes": provider.notes,
        },
        sort_keys=False,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect source repair providers")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    explain = subparsers.add_parser("explain")
    explain.add_argument("provider_id")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    providers = load_registry(args.registry_path)
    if args.command == "list":
        print(format_provider_list({key: provider for key, provider in providers.items() if provider.enabled}))
    elif args.command == "explain":
        print(format_provider_explanation(providers.get(args.provider_id)))


if __name__ == "__main__":
    main()
