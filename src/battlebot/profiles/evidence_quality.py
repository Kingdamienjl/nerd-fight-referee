"""Syntactic evidence checks shared by repair and promotion.

Passing these checks does not verify a claim or assign it to a fighter version.
They prevent known extraction debris from satisfying evidence requirements.
"""
import re


_LAYOUT = re.compile(r"\{\{|\}\}|#tag:|\btabber\b|\b(?:scroll|visible|padding|content|border)\s*=", re.I)


def usable_text(value):
    return isinstance(value, str) and bool(re.search(r"\w", value)) and not _LAYOUT.search(value)


def usable_item(item):
    if isinstance(item, str):
        return bool(usable_text(item))
    if not isinstance(item, dict):
        return False
    def has_layout(value):
        if isinstance(value, str):
            return bool(_LAYOUT.search(value))
        if isinstance(value, dict):
            return any(has_layout(child) for child in value.values())
        if isinstance(value, (list, tuple)):
            return any(has_layout(child) for child in value)
        return False
    if any(has_layout(item.get(key)) for key in ("activation_requirements", "counters",
                                                "resource_dependencies", "scope_limitations")):
        return False
    texts = [item.get(key) for key in ("name", "description", "effect") if item.get(key)]
    return bool(texts) and all(usable_text(value) for value in texts)


def has_usable_ability(profile):
    return any(usable_item(item) for item in profile.get("abilities") or [])


def evidence_quality_blockers(profile):
    blockers = []
    for axis in ("attack_potency", "speed", "durability"):
        entry = (profile.get("power_scale") or {}).get(axis)
        value = entry.get("text") if isinstance(entry, dict) else entry
        if value and not usable_text(value):
            blockers.append(f"invalid_evidence_text:power_scale.{axis}")
    for section in ("abilities", "equipment", "summons", "resistances", "weaknesses"):
        if any(not usable_item(item) for item in profile.get(section) or []):
            blockers.append(f"invalid_evidence_entries:{section}")
    return blockers
