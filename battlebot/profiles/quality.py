"""Profile quality diagnostics and preferred-profile checks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PREFERRED_PROFILES_PATH = Path("profiles/overrides/preferred_profiles.yaml")


KNOWN_HIGH_TIER_LOW_POWER_RULES = {
    "son-goku": ("Building level",),
    "superman": ("Street level", "Building level"),
    "darkseid": ("Street level", "Building level"),
}


def profile_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def load_preferred_profiles(path: Path | str = DEFAULT_PREFERRED_PROFILES_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    preferred = data.get("preferred_profiles") or {}
    return preferred if isinstance(preferred, dict) else {}


def profile_json_from_row(profile: dict[str, Any]) -> dict[str, Any]:
    profile_json = profile.get("profile_json")
    return profile_json if isinstance(profile_json, dict) else profile


def power_text(profile: dict[str, Any], axis: str) -> str | None:
    profile_json = profile_json_from_row(profile)
    power_scale = profile_json.get("power_scale") or {}
    entry = power_scale.get(axis)
    if isinstance(entry, dict):
        text = entry.get("text")
        return str(text) if text else None
    return str(entry) if entry else None


def source_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    profile_json = profile_json_from_row(profile)
    sources = profile_json.get("sources") or []
    return [source for source in sources if isinstance(source, dict)]


def ability_count(profile: dict[str, Any]) -> int:
    profile_json = profile_json_from_row(profile)
    abilities = profile_json.get("abilities") or []
    return len(abilities) if isinstance(abilities, list) else 0


def weakness_count(profile: dict[str, Any]) -> int:
    profile_json = profile_json_from_row(profile)
    weaknesses = profile_json.get("weaknesses") or []
    return len(weaknesses) if isinstance(weaknesses, list) else 0


def warning(flag: str, **details: Any) -> dict[str, Any]:
    return {"flag": flag, **{key: value for key, value in details.items() if value is not None}}


def contains_phrase(value: str | None, phrases: tuple[str, ...] | list[str]) -> str | None:
    if not value:
        return None
    lowered = value.casefold()
    for phrase in phrases:
        if phrase.casefold() in lowered:
            return phrase
    return None


def preferred_override_warning(
    profile: dict[str, Any],
    preferred_profiles: dict[str, Any],
) -> list[dict[str, Any]]:
    name = str(profile.get("canonical_name") or profile.get("name") or "")
    franchise = str(profile.get("franchise") or "")
    override = preferred_profiles.get(profile_key(name))
    if not isinstance(override, dict):
        return []
    required_franchise = override.get("required_franchise")
    if required_franchise and required_franchise != franchise:
        return []

    blocked_phrases = override.get("blocked_power_phrases") or []
    combined_power_text = " ".join(
        text
        for text in (
            power_text(profile, "tier"),
            power_text(profile, "attack_potency"),
            power_text(profile, "speed"),
            power_text(profile, "durability"),
        )
        if text
    )
    matched_phrase = contains_phrase(combined_power_text, blocked_phrases)
    if not matched_phrase:
        return []
    return [
        warning(
            "preferred_profile_blocked_phrase",
            phrase=matched_phrase,
            status=override.get("status"),
            notes=override.get("notes"),
        ),
        warning("needs_manual_review", reason="preferred_profile_override"),
    ]


def profile_warning_flags(
    profile: dict[str, Any],
    *,
    preferred_profiles: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    attack_text = power_text(profile, "attack_potency")
    speed_text = power_text(profile, "speed")
    durability_text = power_text(profile, "durability")
    sources = source_rows(profile)
    abilities = ability_count(profile)

    if not attack_text:
        warnings.append(warning("missing_attack"))
    if not speed_text:
        warnings.append(warning("missing_speed"))
    if not durability_text:
        warnings.append(warning("missing_durability"))
    if abilities < 1:
        warnings.append(warning("low_ability_count", count=abilities))
    if not sources:
        warnings.append(warning("missing_sources"))

    name_key = profile_key(str(profile.get("canonical_name") or profile.get("name") or ""))
    low_power_phrases = KNOWN_HIGH_TIER_LOW_POWER_RULES.get(name_key)
    if low_power_phrases:
        matched_phrase = contains_phrase(attack_text, low_power_phrases)
        if matched_phrase:
            warnings.append(
                warning(
                    "suspicious_low_power_for_known_high_tier",
                    phrase=matched_phrase,
                )
            )

    warnings.extend(
        preferred_override_warning(
            profile,
            preferred_profiles
            if preferred_profiles is not None
            else load_preferred_profiles(),
        )
    )
    return warnings


def warning_flags_only(warnings: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("flag")) for item in warnings if item.get("flag")]
