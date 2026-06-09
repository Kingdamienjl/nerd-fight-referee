"""File-backed profile review service and CLI."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from battlebot.profiles.quality import profile_warning_flags


DEFAULT_GENERATED_DIR = Path("profiles/generated")
DEFAULT_NEEDS_REVIEW_DIR = Path("profiles/needs_review")
DEFAULT_REJECTED_DIR = Path("profiles/rejected")
DEFAULT_OVERRIDES_DIR = Path("profiles/overrides")
DEFAULT_REVIEW_NOTES_PATH = Path("profiles/review_notes.yaml")
DEFAULT_REPAIR_DEBUG_DIR = Path("data/repair_debug")

POWER_CORE_FIELDS = ("attack_potency", "speed", "durability")
EDITABLE_POWER_FIELDS = (
    "tier",
    "attack_potency",
    "speed",
    "durability",
    "range",
    "stamina",
    "intelligence",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path | str) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def write_yaml(path: Path | str, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.tmp")
    temp_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    temp_path.replace(target)


def profile_path_kind(path: Path) -> str:
    parts = path.parts
    if "needs_review" in parts:
        return "needs_review"
    if "generated" in parts:
        return "generated"
    if "rejected" in parts:
        return "rejected"
    return "unknown"


def relative_profile_tail(path: Path, source_root: Path) -> Path:
    try:
        return path.relative_to(source_root)
    except ValueError:
        parts = path.parts
        for marker in ("needs_review", "generated", "rejected"):
            if marker in parts:
                return Path(*parts[parts.index(marker) + 1 :])
    return Path(path.name)


def destination_for(path: Path, source_root: Path, destination_root: Path) -> Path:
    return destination_root / relative_profile_tail(path, source_root)


def power_text(profile: dict[str, Any], field: str) -> str | None:
    entry = (profile.get("power_scale") or {}).get(field)
    if isinstance(entry, dict):
        value = entry.get("text")
        return str(value) if value else None
    return str(entry) if entry else None


def source_has_revision(profile: dict[str, Any]) -> bool:
    return any(bool(source.get("revision_id")) for source in profile.get("sources") or [])


def missing_core_fields(profile: dict[str, Any]) -> list[str]:
    return [field for field in POWER_CORE_FIELDS if not power_text(profile, field)]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "item"


def safe_unique_id(value: str, existing_ids: set[str], *, fallback: str) -> str:
    base = slugify(value or fallback)
    candidate = base
    counter = 2
    while candidate in existing_ids:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def normalize_tags(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    return [tag.strip() for tag in str(value).replace("|", ",").split(",") if tag.strip()]


def collect_source_usage(profile: dict[str, Any]) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {}
    power_scale = profile.get("power_scale") or {}
    for axis, entry in power_scale.items():
        if isinstance(entry, dict):
            for source_id in entry.get("source_ids") or []:
                usage.setdefault(str(source_id), []).append(f"power_scale.{axis}")
    for section in ("abilities", "equipment", "weaknesses"):
        for item in profile.get(section) or []:
            item_id = item.get("id") or item.get("name") or "item"
            for source_id in item.get("source_ids") or []:
                usage.setdefault(str(source_id), []).append(f"{section}.{item_id}")
    return usage


def source_details(profile: dict[str, Any]) -> list[dict[str, Any]]:
    usage = collect_source_usage(profile)
    details = []
    for source in profile.get("sources") or []:
        source_id = str(source.get("id") or "")
        used_by = usage.get(source_id, [])
        details.append(
            {
                "id": source_id,
                "title": source.get("title"),
                "url": source.get("url"),
                "revision_id": source.get("revision_id"),
                "source_type": source.get("source_type"),
                "has_revision_id": bool(source.get("revision_id")),
                "used_by": used_by,
                "used": bool(used_by),
                "notes": source.get("notes"),
            }
        )
    return details


def approval_blockers(profile: dict[str, Any]) -> list[str]:
    blockers = [f"missing_{field}" for field in missing_core_fields(profile)]
    if not profile.get("sources"):
        blockers.append("missing_sources")
    if not profile.get("abilities"):
        blockers.append("missing_ability")
    power_scale = profile.get("power_scale") or {}
    for field in POWER_CORE_FIELDS:
        entry = power_scale.get(field)
        if isinstance(entry, dict) and entry.get("text") and not entry.get("source_ids"):
            blockers.append(f"missing_source_ids_for_{field}")
    return sorted(set(blockers))


def source_title_mismatch_likely(profile: dict[str, Any]) -> bool:
    name = str(profile.get("name") or "").casefold()
    if not name:
        return False
    titles = [
        str(source.get("title") or "").casefold()
        for source in profile.get("sources") or []
        if source.get("title")
    ]
    if not titles:
        return False
    name_tokens = [token for token in name.replace("-", " ").split() if len(token) > 2]
    return not any(any(token in title for token in name_tokens) for title in titles)


def review_reasons(profile: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    missing = missing_core_fields(profile)
    reasons.extend(f"missing_{field.removesuffix('_potency')}" for field in missing)
    abilities = profile.get("abilities") or []
    if len(abilities) < 1:
        reasons.append("low_ability_count")
    if not profile.get("sources"):
        reasons.append("missing_sources")
    generation = profile.get("generation") or {}
    if float(generation.get("confidence") or 0) < 0.55:
        reasons.append("confidence_too_low")
    if not source_has_revision(profile):
        reasons.append("no_revision_id")
    if source_title_mismatch_likely(profile):
        reasons.append("ambiguous_or_wrong_page")
    return sorted(set(reasons))


def profile_summary(path: Path, root_kind: str) -> dict[str, Any]:
    profile = load_yaml(path)
    warnings = profile_warning_flags(profile)
    return {
        "path": str(path),
        "kind": root_kind,
        "name": profile.get("name") or path.stem,
        "franchise": profile.get("franchise"),
        "category": profile.get("category"),
        "battle_eligible": bool(profile.get("battle_eligible")),
        "status": profile.get("status"),
        "profile_type": profile.get("profile_type"),
        "confidence": (profile.get("generation") or {}).get("confidence"),
        "warning_flags": [warning["flag"] for warning in warnings],
        "review_reasons": review_reasons(profile),
    }


def iter_profile_paths(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.yaml") if path.is_file())


def list_profiles(
    *,
    generated_dir: Path | str = DEFAULT_GENERATED_DIR,
    needs_review_dir: Path | str = DEFAULT_NEEDS_REVIEW_DIR,
    rejected_dir: Path | str = DEFAULT_REJECTED_DIR,
    kind: str = "needs_review",
    franchise: str | None = None,
    category: str | None = None,
    warning_flag: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    roots = {
        "generated": Path(generated_dir),
        "needs_review": Path(needs_review_dir),
        "rejected": Path(rejected_dir),
    }
    selected = roots if kind == "all" else {kind: roots[kind]}
    profiles: list[dict[str, Any]] = []
    for root_kind, root in selected.items():
        for path in iter_profile_paths(root):
            summary = profile_summary(path, root_kind)
            if franchise and str(summary.get("franchise") or "").casefold() != franchise.casefold():
                continue
            if category and str(summary.get("category") or "").casefold() != category.casefold():
                continue
            if warning_flag and warning_flag not in summary["warning_flags"]:
                continue
            profiles.append(summary)
            if limit and len(profiles) >= limit:
                return profiles
    return profiles


def inspect_profile(path: Path | str) -> dict[str, Any]:
    profile_path = Path(path)
    profile = load_yaml(profile_path)
    abilities = profile.get("abilities") or []
    weaknesses = profile.get("weaknesses") or []
    sources = source_details(profile)
    generation = profile.get("generation") or {}
    repair_debug = load_repair_debug(profile_path)
    return {
        "path": str(profile_path),
        "kind": profile_path_kind(profile_path),
        "name": profile.get("name"),
        "franchise": profile.get("franchise"),
        "category": profile.get("category"),
        "battle_eligible": bool(profile.get("battle_eligible")),
        "status": profile.get("status"),
        "profile_type": profile.get("profile_type"),
        "confidence": generation.get("confidence"),
        "ineligible_reasons": generation.get("ineligible_reasons") or [],
        "missing_core_fields": missing_core_fields(profile),
        "approval_blockers": approval_blockers(profile),
        "review_reasons": review_reasons(profile),
        "attack_potency": power_text(profile, "attack_potency"),
        "speed": power_text(profile, "speed"),
        "durability": power_text(profile, "durability"),
        "abilities_count": len(abilities),
        "abilities": abilities[:20],
        "weaknesses_count": len(weaknesses),
        "weaknesses": weaknesses[:20],
        "sources": sources,
        "editable_power_fields": [
            {
                "field": field,
                "text": power_text(profile, field),
                "source_ids": ((profile.get("power_scale") or {}).get(field) or {}).get("source_ids", [])
                if isinstance((profile.get("power_scale") or {}).get(field), dict)
                else [],
                "confidence": ((profile.get("power_scale") or {}).get(field) or {}).get("confidence")
                if isinstance((profile.get("power_scale") or {}).get(field), dict)
                else None,
            }
            for field in EDITABLE_POWER_FIELDS
        ],
        "quality_warnings": profile_warning_flags(profile),
        "repair": profile.get("repair") or {},
        "repair_debug": repair_debug,
        "repair_attempts": repair_debug.get("source_attempts")
        or (profile.get("repair") or {}).get("source_attempts")
        or [],
        "raw": profile,
    }


async def selected_auto_repair(
    profile_path: Path | str,
    source_id: str,
    *,
    promote_if_valid: bool = True,
    debug_dir: Path | str = DEFAULT_REPAIR_DEBUG_DIR,
) -> Any:
    from battlebot.review import auto_repair

    return await auto_repair.repair_profile(
        Path(profile_path),
        choose_source_id=source_id,
        promote_if_valid=promote_if_valid,
        debug_dir=Path(debug_dir),
        fetch_sources=True,
    )


def load_repair_debug(profile_path: Path, debug_dir: Path | None = None) -> dict[str, Any]:
    report_path = (debug_dir or DEFAULT_REPAIR_DEBUG_DIR) / f"{slugify(profile_path.stem)}.json"
    if not report_path.exists():
        return {}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def atomic_append_note(notes_path: Path, note: dict[str, Any]) -> None:
    current = load_yaml(notes_path) if notes_path.exists() else {}
    notes = current.get("notes") or []
    notes.append(note)
    write_yaml(notes_path, {"notes": notes})


def add_review_note(
    profile_path: Path | str,
    *,
    field_path: str = "",
    issue_type: str = "review_note",
    note: str = "",
    suggested_value: str = "",
    source_id: str = "",
    notes_path: Path | str = DEFAULT_REVIEW_NOTES_PATH,
) -> dict[str, Any]:
    entry = {
        "profile_path": str(profile_path),
        "field_path": field_path,
        "issue_type": issue_type,
        "note": note,
        "suggested_value": suggested_value,
        "source_id": source_id,
        "timestamp": utc_now(),
        "created_at": utc_now(),
    }
    atomic_append_note(Path(notes_path), entry)
    return entry


def add_source(
    profile_path: Path | str,
    *,
    source_id: str = "",
    title: str = "",
    url: str = "",
    source_type: str = "manual",
    revision_id: str = "",
    notes: str = "",
    notes_path: Path | str = DEFAULT_REVIEW_NOTES_PATH,
) -> dict[str, Any]:
    path = Path(profile_path)
    profile = load_yaml(path)
    sources = profile.setdefault("sources", [])
    existing_ids = {str(source.get("id")) for source in sources if source.get("id")}
    new_id = safe_unique_id(source_id or title or url, existing_ids, fallback="source")
    source = {
        "id": new_id,
        "title": title or None,
        "url": url or None,
        "source_type": source_type or "manual",
        "revision_id": revision_id or None,
        "notes": notes or None,
    }
    sources.append(source)
    write_yaml(path, profile)
    add_review_note(
        path,
        field_path="sources",
        issue_type="manual_repair",
        note=notes or "Added source",
        suggested_value=title or url or new_id,
        source_id=new_id,
        notes_path=notes_path,
    )
    return {"ok": True, "source": source}


def set_core_field(
    profile_path: Path | str,
    *,
    field: str,
    text: str,
    source_id: str,
    confidence: float,
    note: str = "",
    notes_path: Path | str = DEFAULT_REVIEW_NOTES_PATH,
) -> dict[str, Any]:
    if field not in EDITABLE_POWER_FIELDS:
        return {"ok": False, "error": "unknown_core_field", "field": field}
    if not source_id:
        return {"ok": False, "error": "missing_source_id", "field": field}
    path = Path(profile_path)
    profile = load_yaml(path)
    power_scale = profile.setdefault("power_scale", {})
    power_scale[field] = {
        "text": text,
        "source_ids": [source_id],
        "confidence": float(confidence),
        "notes": note,
    }
    write_yaml(path, profile)
    add_review_note(
        path,
        field_path=f"power_scale.{field}.text",
        issue_type="manual_repair",
        note=note,
        suggested_value=text,
        source_id=source_id,
        notes_path=notes_path,
    )
    return {"ok": True, "field": field, "source_id": source_id}


def enriched_manual_item(
    *,
    item_id: str,
    name: str,
    description: str,
    source_id: str,
    confidence: float,
    tags: str | list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name or item_id,
        "description": description,
        "source_ids": [source_id] if source_id else [],
        "confidence": float(confidence),
        "tags": normalize_tags(tags),
        "targets": [],
        "activation_requirements": [],
        "counters": [],
        "resource_dependencies": [],
        "scope_limitations": [],
        "enrichment": {"manual_review": True},
    }


def add_enriched_item(
    profile_path: Path | str,
    *,
    section: str,
    item_id: str = "",
    name: str = "",
    description: str,
    source_id: str,
    confidence: float,
    tags: str | list[str] | None = None,
    notes_path: Path | str = DEFAULT_REVIEW_NOTES_PATH,
) -> dict[str, Any]:
    if section not in {"abilities", "weaknesses"}:
        return {"ok": False, "error": "unknown_item_section", "section": section}
    path = Path(profile_path)
    profile = load_yaml(path)
    items = profile.setdefault(section, [])
    existing_ids = {str(item.get("id")) for item in items if item.get("id")}
    new_id = safe_unique_id(item_id or name, existing_ids, fallback=section.removesuffix("s"))
    item = enriched_manual_item(
        item_id=new_id,
        name=name,
        description=description,
        source_id=source_id,
        confidence=confidence,
        tags=tags,
    )
    items.append(item)
    write_yaml(path, profile)
    add_review_note(
        path,
        field_path=f"{section}.{new_id}",
        issue_type="manual_repair",
        note=f"Added {section.removesuffix('s')}: {name or new_id}",
        suggested_value=description,
        source_id=source_id,
        notes_path=notes_path,
    )
    return {"ok": True, section.removesuffix("s"): item}


def add_ability(profile_path: Path | str, **kwargs: Any) -> dict[str, Any]:
    return add_enriched_item(profile_path, section="abilities", **kwargs)


def add_weakness(profile_path: Path | str, **kwargs: Any) -> dict[str, Any]:
    return add_enriched_item(profile_path, section="weaknesses", **kwargs)


def approved_profile_data(
    profile: dict[str, Any],
    *,
    force: bool,
    missing: list[str],
    blockers: list[str],
) -> dict[str, Any]:
    data = sanitize_generated_profile(profile)
    data["battle_eligible"] = not blockers
    data["profile_type"] = "approved_override"
    data["status"] = "needs_manual_review_approved" if force else "approved_override"
    review = data.get("review") if isinstance(data.get("review"), dict) else {}
    review["approved_at"] = utc_now()
    review["approved_by"] = "local_review_ui"
    data["review"] = review
    generation = data.get("generation") if isinstance(data.get("generation"), dict) else {}
    generation["ineligible_reasons"] = [] if not blockers else blockers
    if not blockers:
        generation["confidence"] = max(float(generation.get("confidence") or 0), 0.55)
    data["generation"] = generation
    return data


def sanitize_generated_profile(data: dict[str, Any]) -> dict[str, Any]:
    profile = deepcopy(data)
    profile.pop("repair", None)
    return profile


def approve_profile(
    profile_path: Path | str,
    *,
    force: bool = False,
    needs_review_dir: Path | str = DEFAULT_NEEDS_REVIEW_DIR,
    generated_dir: Path | str = DEFAULT_GENERATED_DIR,
    notes_path: Path | str = DEFAULT_REVIEW_NOTES_PATH,
) -> dict[str, Any]:
    source = Path(profile_path)
    profile = load_yaml(source)
    blockers = approval_blockers(profile)
    if blockers and not force:
        return {
            "ok": False,
            "error": "approval_blockers",
            "approval_blockers": blockers,
            "missing_core_fields": missing_core_fields(profile),
            "destination": None,
        }
    destination = destination_for(source, Path(needs_review_dir), Path(generated_dir))
    write_yaml(
        destination,
        approved_profile_data(
            profile,
            force=force,
            missing=missing_core_fields(profile),
            blockers=blockers,
        ),
    )
    add_review_note(
        source,
        issue_type="approved",
        note=f"Approved into {destination}",
        notes_path=notes_path,
    )
    return {
        "ok": True,
        "source": str(source),
        "destination": str(destination),
        "missing_core_fields": missing_core_fields(profile),
        "approval_blockers": blockers,
    }


def reject_profile(
    profile_path: Path | str,
    *,
    note: str = "",
    needs_review_dir: Path | str = DEFAULT_NEEDS_REVIEW_DIR,
    rejected_dir: Path | str = DEFAULT_REJECTED_DIR,
    notes_path: Path | str = DEFAULT_REVIEW_NOTES_PATH,
) -> dict[str, Any]:
    source = Path(profile_path)
    destination = destination_for(source, Path(needs_review_dir), Path(rejected_dir))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    add_review_note(
        source,
        issue_type="rejected",
        note=note,
        notes_path=notes_path,
    )
    return {"ok": True, "source": str(source), "destination": str(destination)}


def requeue_profile(
    profile_path: Path | str,
    *,
    note: str,
    notes_path: Path | str = DEFAULT_REVIEW_NOTES_PATH,
) -> dict[str, Any]:
    entry = add_review_note(
        profile_path,
        issue_type="requeue",
        note=note,
        notes_path=notes_path,
    )
    return {"ok": True, "note": entry}


def format_profile_list(profiles: list[dict[str, Any]]) -> str:
    if not profiles:
        return "No profiles found."
    return "\n".join(
        f"{profile['path']} | {profile['name']} | {profile['status']} | "
        f"warnings={','.join(profile['warning_flags']) or 'none'}"
        for profile in profiles
    )


def format_inspection(inspection: dict[str, Any]) -> str:
    lines = [
        f"{inspection['name']} ({inspection['franchise']}, {inspection['category']})",
        f"path: {inspection['path']}",
        f"battle_eligible: {inspection['battle_eligible']}",
        f"status: {inspection['status']}",
        f"profile_type: {inspection['profile_type']}",
        f"confidence: {inspection['confidence']}",
        f"ineligible_reasons: {inspection['ineligible_reasons']}",
        f"missing_core_fields: {inspection['missing_core_fields']}",
        f"approval_blockers: {inspection['approval_blockers']}",
        f"review_reasons: {inspection['review_reasons']}",
        f"attack_potency: {inspection['attack_potency'] or 'n/a'}",
        f"speed: {inspection['speed'] or 'n/a'}",
        f"durability: {inspection['durability'] or 'n/a'}",
        f"abilities: {inspection['abilities_count']}",
        f"weaknesses: {inspection['weaknesses_count']}",
        "sources:",
    ]
    for source in inspection["sources"][:10]:
        lines.append(
            f"- {source.get('title') or 'n/a'} rev={source.get('revision_id') or 'n/a'} "
            f"type={source.get('source_type') or 'n/a'} used={source.get('used')} "
            f"url={source.get('url') or 'n/a'}"
        )
    warning_flags = [warning["flag"] for warning in inspection["quality_warnings"]]
    lines.append(f"quality_warnings: {warning_flags}")
    if inspection.get("repair_attempts"):
        lines.append("repair_attempts:")
        for attempt in inspection["repair_attempts"][:10]:
            lines.append(
                f"- {attempt.get('source_id')} status={attempt.get('fetch_status') or attempt.get('note')} "
                f"fields={attempt.get('extracted_fields') or []} "
                f"failure={attempt.get('extraction_failure_reason') or 'none'}"
            )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review generated battle profiles")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--kind", default="needs_review", choices=["needs_review", "generated", "rejected", "all"])
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.add_argument("--franchise")
    list_parser.add_argument("--category")
    list_parser.add_argument("--warning-flag")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("profile_path")

    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("profile_path")
    approve_parser.add_argument("--force", action="store_true")

    reject_parser = subparsers.add_parser("reject")
    reject_parser.add_argument("profile_path")
    reject_parser.add_argument("--note", default="")

    note_parser = subparsers.add_parser("note")
    note_parser.add_argument("profile_path")
    note_parser.add_argument("--field-path", default="")
    note_parser.add_argument("--issue-type", default="review_note")
    note_parser.add_argument("--note", default="")
    note_parser.add_argument("--suggested-value", default="")

    add_source_parser = subparsers.add_parser("add-source")
    add_source_parser.add_argument("profile_path")
    add_source_parser.add_argument("--id", dest="source_id", default="")
    add_source_parser.add_argument("--title", default="")
    add_source_parser.add_argument("--url", default="")
    add_source_parser.add_argument("--source-type", default="manual")
    add_source_parser.add_argument("--revision-id", default="")
    add_source_parser.add_argument("--notes", default="")

    set_core_parser = subparsers.add_parser("set-core")
    set_core_parser.add_argument("profile_path")
    set_core_parser.add_argument("--field", required=True)
    set_core_parser.add_argument("--text", required=True)
    set_core_parser.add_argument("--source-id", required=True)
    set_core_parser.add_argument("--confidence", type=float, required=True)
    set_core_parser.add_argument("--note", default="")

    add_ability_parser = subparsers.add_parser("add-ability")
    add_ability_parser.add_argument("profile_path")
    add_ability_parser.add_argument("--id", dest="item_id", default="")
    add_ability_parser.add_argument("--name", default="")
    add_ability_parser.add_argument("--description", required=True)
    add_ability_parser.add_argument("--source-id", required=True)
    add_ability_parser.add_argument("--confidence", type=float, required=True)
    add_ability_parser.add_argument("--tags", default="")

    add_weakness_parser = subparsers.add_parser("add-weakness")
    add_weakness_parser.add_argument("profile_path")
    add_weakness_parser.add_argument("--id", dest="item_id", default="")
    add_weakness_parser.add_argument("--name", default="")
    add_weakness_parser.add_argument("--description", required=True)
    add_weakness_parser.add_argument("--source-id", required=True)
    add_weakness_parser.add_argument("--confidence", type=float, required=True)
    add_weakness_parser.add_argument("--tags", default="")

    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.command == "list":
        print(
            format_profile_list(
                list_profiles(
                    kind=args.kind,
                    limit=args.limit,
                    franchise=args.franchise,
                    category=args.category,
                    warning_flag=args.warning_flag,
                )
            )
        )
    elif args.command == "inspect":
        print(format_inspection(inspect_profile(args.profile_path)))
    elif args.command == "approve":
        print(yaml.safe_dump(approve_profile(args.profile_path, force=args.force), sort_keys=False))
    elif args.command == "reject":
        print(yaml.safe_dump(reject_profile(args.profile_path, note=args.note), sort_keys=False))
    elif args.command == "note":
        print(
            yaml.safe_dump(
                add_review_note(
                    args.profile_path,
                    field_path=args.field_path,
                    issue_type=args.issue_type,
                    note=args.note,
                    suggested_value=args.suggested_value,
                ),
                sort_keys=False,
            )
        )
    elif args.command == "add-source":
        print(
            yaml.safe_dump(
                add_source(
                    args.profile_path,
                    source_id=args.source_id,
                    title=args.title,
                    url=args.url,
                    source_type=args.source_type,
                    revision_id=args.revision_id,
                    notes=args.notes,
                ),
                sort_keys=False,
            )
        )
    elif args.command == "set-core":
        print(
            yaml.safe_dump(
                set_core_field(
                    args.profile_path,
                    field=args.field,
                    text=args.text,
                    source_id=args.source_id,
                    confidence=args.confidence,
                    note=args.note,
                ),
                sort_keys=False,
            )
        )
    elif args.command == "add-ability":
        print(
            yaml.safe_dump(
                add_ability(
                    args.profile_path,
                    item_id=args.item_id,
                    name=args.name,
                    description=args.description,
                    source_id=args.source_id,
                    confidence=args.confidence,
                    tags=args.tags,
                ),
                sort_keys=False,
            )
        )
    elif args.command == "add-weakness":
        print(
            yaml.safe_dump(
                add_weakness(
                    args.profile_path,
                    item_id=args.item_id,
                    name=args.name,
                    description=args.description,
                    source_id=args.source_id,
                    confidence=args.confidence,
                    tags=args.tags,
                ),
                sort_keys=False,
            )
        )


if __name__ == "__main__":
    main()
