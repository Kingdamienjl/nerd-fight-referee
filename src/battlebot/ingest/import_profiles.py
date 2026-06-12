"""Compile validated generated YAML profiles into Postgres."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from battlebot.common.db import apply_schema, connect_database
from battlebot.schemas.profile import CharacterProfile


@dataclass
class ImportOptions:
    include_needs_review: bool = False
    fail_fast: bool = False
    changed_only: bool = False
    import_state: dict[str, Any] | None = None


@dataclass
class ImportSummary:
    scanned: int = 0
    changed: int = 0
    imported: int = 0
    skipped_unchanged: int = 0
    skipped_invalid: int = 0
    skipped_not_battle_eligible: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class CompiledProfile:
    path: Path
    character: dict[str, Any]
    aliases: list[dict[str, Any]]
    profile: dict[str, Any]
    sources: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    power_scale: list[dict[str, Any]]
    abilities: list[dict[str, Any]]
    equipment: list[dict[str, Any]]
    weaknesses: list[dict[str, Any]]


def find_profile_paths(root: Path) -> list[Path]:
    if root.is_dir():
        return sorted(root.rglob("*.yaml"))
    return [root]


def load_profile_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("profile YAML root must be an object")
    return data


def validate_profile_path(path: Path) -> CharacterProfile:
    return CharacterProfile.model_validate(load_profile_yaml(path))


def load_import_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"profiles": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("profiles", {})
    return state


def write_import_state_atomic(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def reset_import_state(path: Path) -> dict[str, Any]:
    if path.exists():
        path.unlink()
    return {"profiles": {}}


def profile_file_fingerprint(path: Path, profile_hash: str | None = None) -> dict[str, Any]:
    stat = path.stat()
    if profile_hash is None:
        try:
            data = load_profile_yaml(path)
            profile_hash = str(data.get("profile_hash") or "")
        except Exception:
            profile_hash = ""
    return {
        "path": path.as_posix(),
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "profile_hash": profile_hash,
    }


def profile_fingerprint_changed(
    path: Path,
    state: dict[str, Any],
    fingerprint: dict[str, Any] | None = None,
) -> bool:
    fingerprint = fingerprint or profile_file_fingerprint(path)
    previous = state.setdefault("profiles", {}).get(path.as_posix())
    return previous != fingerprint


def compile_profile(profile: CharacterProfile, path: Path) -> CompiledProfile:
    profile_json = profile.model_dump(mode="json")
    character_id = profile.id
    profile_id = profile.id
    return CompiledProfile(
        path=path,
        character={
            "id": character_id,
            "canonical_name": profile.name,
            "franchise": profile.franchise,
            "category": profile.category,
        },
        aliases=compile_aliases(profile),
        profile={
            "profile_id": profile_id,
            "character_id": character_id,
            "profile_type": str(profile.profile_type),
            "status": profile.status,
            "battle_eligible": profile.battle_eligible,
            "profile_hash": profile.profile_hash,
            "profile_path": path.as_posix(),
            "profile_json": profile_json,
            "generated_at": parse_timestamp(getattr(profile.generation, "generated_at", None)),
        },
        sources=compile_sources(profile, profile_id),
        claims=compile_claims(profile, profile_id),
        power_scale=compile_power_scale(profile, profile_id),
        abilities=compile_items(profile.abilities, profile_id, "ability_id"),
        equipment=compile_items(profile.equipment, profile_id, "equipment_id"),
        weaknesses=compile_items(profile.weaknesses, profile_id, "weakness_id"),
    )


def compile_aliases(profile: CharacterProfile) -> list[dict[str, Any]]:
    seen = set()
    aliases = [profile.name, *profile.aliases]
    rows = []
    for alias in aliases:
        normalized = normalize_alias(alias)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(
            {
                "character_id": profile.id,
                "alias": alias,
                "normalized_alias": normalized,
            }
        )
    return rows


def compile_sources(profile: CharacterProfile, profile_id: str) -> list[dict[str, Any]]:
    """Compile sources while preserving one row per stable source ID."""
    rows_by_id: dict[str, dict[str, Any]] = {}
    source_order: list[str] = []

    for source in profile.sources:
        source_id = str(source.id or "").strip()
        if not source_id:
            continue

        source_data = source.model_dump(mode="json")
        row = {
            "source_id": source_id,
            "profile_id": profile_id,
            "title": source.title,
            "url": source.url,
            "source_type": source.source_type,
            "license": source_data.get("license"),
            "page_id": source.page_id,
            "revision_id": source.revision_id,
            "revision_timestamp": source.revision_timestamp,
            "retrieved_at": source.retrieved_at,
            "admissible": source_data.get("admissible", True),
        }

        existing = rows_by_id.get(source_id)
        if existing is None:
            rows_by_id[source_id] = row
            source_order.append(source_id)
            continue

        # Merge later populated metadata into the existing stable source.
        for key, value in row.items():
            if value not in (None, "", [], {}):
                existing[key] = value

    return [rows_by_id[source_id] for source_id in source_order]


def compile_claims(profile: CharacterProfile, profile_id: str) -> list[dict[str, Any]]:
    rows = []
    for claim in profile.claims:
        claim_id = claim.get("id")
        claim_text = claim.get("text")
        axis = claim.get("axis") or "other"
        if not claim_id or not claim_text:
            continue
        rows.append(
            {
                "claim_id": claim_id,
                "profile_id": profile_id,
                "axis": axis,
                "claim_text": claim_text,
                "source_ids": claim.get("source_ids") or [],
                "decisive": bool(claim.get("decisive", False)),
                "confidence": float(claim.get("confidence") or 0),
                "policy_flags": claim.get("policy_flags") or [],
            }
        )
    return rows


def compile_power_scale(profile: CharacterProfile, profile_id: str) -> list[dict[str, Any]]:
    power_scale = profile.power_scale.model_dump(mode="json")
    return [
        {
            "profile_id": profile_id,
            "axis": axis,
            "text": value.get("text"),
            "source_ids": value.get("source_ids") or [],
            "confidence": float(value.get("confidence") or 0),
        }
        for axis, value in power_scale.items()
    ]


def compile_items(
    items: list[Any],
    profile_id: str,
    id_column: str,
) -> list[dict[str, Any]]:
    rows = []
    used_ids: set[str] = set()
    for item in items:
        data = item.model_dump(mode="json")
        item_id = unique_row_id(data.get("id") or id_column, used_ids)
        rows.append(
            {
                id_column: item_id,
                "profile_id": profile_id,
                "name": data.get("name"),
                "description": data.get("description"),
                "function": data.get("function"),
                "source_ids": data.get("source_ids") or [],
                "tags": data.get("tags") or [],
                "targets": data.get("targets") or [],
                "activation_requirements": data.get("activation_requirements") or [],
                "counters": data.get("counters") or [],
                "resource_dependencies": data.get("resource_dependencies") or [],
                "scope_limitations": data.get("scope_limitations") or [],
                "enrichment": data.get("enrichment") or {},
                "confidence": float(data.get("confidence") or 0),
            }
        )
    return rows


def build_import_plan(
    root: Path,
    options: ImportOptions | None = None,
) -> tuple[list[CompiledProfile], ImportSummary]:
    options = options or ImportOptions()
    import_state = options.import_state or {"profiles": {}}
    summary = ImportSummary()
    compiled = []
    for path in find_profile_paths(root):
        summary.scanned += 1
        if options.changed_only:
            fingerprint = profile_file_fingerprint(path)
            if not profile_fingerprint_changed(path, import_state, fingerprint):
                summary.skipped_unchanged += 1
                continue
            summary.changed += 1
        try:
            profile = validate_profile_path(path)
        except (ValidationError, ValueError, OSError) as exc:
            summary.skipped_invalid += 1
            summary.errors.append(f"{path}: {exc}")
            if options.fail_fast:
                raise
            continue
        if not profile.battle_eligible and not options.include_needs_review:
            summary.skipped_not_battle_eligible += 1
            continue
        compiled.append(compile_profile(profile, path))
        summary.imported += 1
    return compiled, summary


async def import_compiled_profiles(
    compiled_profiles: list[CompiledProfile],
    *,
    database_url: str | None,
    wipe_profiles: bool,
) -> None:
    async with connect_database(database_url) as connection:
        await apply_schema(connection)
        async with connection.transaction():
            if wipe_profiles:
                await wipe_imported_tables(connection)
            for compiled in compiled_profiles:
                await upsert_compiled_profile(connection, compiled)


def update_import_state_for_compiled(
    state: dict[str, Any],
    compiled_profiles: list[CompiledProfile],
) -> None:
    profiles = state.setdefault("profiles", {})
    for compiled in compiled_profiles:
        profile_hash = str(compiled.profile.get("profile_hash") or "")
        profiles[compiled.path.as_posix()] = profile_file_fingerprint(compiled.path, profile_hash)


async def wipe_imported_tables(connection: Any) -> None:
    await connection.execute(
        """
        TRUNCATE TABLE
            profile_weaknesses,
            profile_equipment,
            profile_abilities,
            profile_power_scale,
            profile_claims,
            profile_sources,
            character_profiles,
            character_aliases,
            characters
        RESTART IDENTITY CASCADE
        """
    )


async def upsert_compiled_profile(connection: Any, compiled: CompiledProfile) -> None:
    await connection.execute(
        """
        INSERT INTO characters (id, canonical_name, franchise, category, updated_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (id) DO UPDATE SET
            canonical_name = EXCLUDED.canonical_name,
            franchise = EXCLUDED.franchise,
            category = EXCLUDED.category,
            updated_at = now()
        """,
        compiled.character["id"],
        compiled.character["canonical_name"],
        compiled.character["franchise"],
        compiled.character["category"],
    )
    await connection.execute(
        "DELETE FROM character_aliases WHERE character_id = $1",
        compiled.character["id"],
    )
    for alias in compiled.aliases:
        await connection.execute(
            """
            INSERT INTO character_aliases (character_id, alias, normalized_alias)
            VALUES ($1, $2, $3)
            ON CONFLICT (character_id, normalized_alias) DO UPDATE SET
                alias = EXCLUDED.alias
            """,
            alias["character_id"],
            alias["alias"],
            alias["normalized_alias"],
        )

    await connection.execute(
        """
        INSERT INTO character_profiles (
            profile_id, character_id, profile_type, status, battle_eligible, profile_hash,
            profile_path, profile_json, generated_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, now())
        ON CONFLICT (profile_id) DO UPDATE SET
            character_id = EXCLUDED.character_id,
            profile_type = EXCLUDED.profile_type,
            status = EXCLUDED.status,
            battle_eligible = EXCLUDED.battle_eligible,
            profile_hash = EXCLUDED.profile_hash,
            profile_path = EXCLUDED.profile_path,
            profile_json = EXCLUDED.profile_json,
            generated_at = EXCLUDED.generated_at,
            updated_at = now()
        """,
        compiled.profile["profile_id"],
        compiled.profile["character_id"],
        compiled.profile["profile_type"],
        compiled.profile["status"],
        compiled.profile["battle_eligible"],
        compiled.profile["profile_hash"],
        compiled.profile["profile_path"],
        json.dumps(compiled.profile["profile_json"], sort_keys=True),
        compiled.profile["generated_at"],
    )

    await replace_profile_children(connection, compiled)


async def replace_profile_children(connection: Any, compiled: CompiledProfile) -> None:
    profile_id = compiled.profile["profile_id"]
    for table in (
        "profile_sources",
        "profile_claims",
        "profile_power_scale",
        "profile_abilities",
        "profile_equipment",
        "profile_weaknesses",
    ):
        await connection.execute(f"DELETE FROM {table} WHERE profile_id = $1", profile_id)

    for row in compiled.sources:
        await connection.execute(
            """
            INSERT INTO profile_sources (
                source_id, profile_id, title, url, source_type, license, page_id,
                revision_id, revision_timestamp, retrieved_at, admissible
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            row["source_id"],
            row["profile_id"],
            row["title"],
            row["url"],
            row["source_type"],
            row["license"],
            row["page_id"],
            row["revision_id"],
            row["revision_timestamp"],
            row["retrieved_at"],
            row["admissible"],
        )

    for row in compiled.claims:
        await connection.execute(
            """
            INSERT INTO profile_claims (
                claim_id, profile_id, axis, claim_text, source_ids, decisive,
                confidence, policy_flags
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8::jsonb)
            """,
            row["claim_id"],
            row["profile_id"],
            row["axis"],
            row["claim_text"],
            json.dumps(row["source_ids"]),
            row["decisive"],
            row["confidence"],
            json.dumps(row["policy_flags"]),
        )

    for row in compiled.power_scale:
        await connection.execute(
            """
            INSERT INTO profile_power_scale (profile_id, axis, text, source_ids, confidence)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            row["profile_id"],
            row["axis"],
            row["text"],
            json.dumps(row["source_ids"]),
            row["confidence"],
        )

    for row in compiled.abilities:
        await insert_item(connection, "profile_abilities", "ability_id", row)
    for row in compiled.equipment:
        await insert_item(connection, "profile_equipment", "equipment_id", row)
    for row in compiled.weaknesses:
        await insert_weakness(connection, row)


async def insert_item(connection: Any, table: str, id_column: str, row: dict[str, Any]) -> None:
    await connection.execute(
        f"""
        INSERT INTO {table} (
            {id_column}, profile_id, name, description, source_ids, tags, targets,
            activation_requirements, counters, resource_dependencies, scope_limitations,
            enrichment, confidence
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb, $8::jsonb,
            $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13)
        """,
        row[id_column],
        row["profile_id"],
        row["name"],
        row["description"],
        json.dumps(row["source_ids"]),
        json.dumps(row["tags"]),
        json.dumps(row["targets"]),
        json.dumps(row["activation_requirements"]),
        json.dumps(row["counters"]),
        json.dumps(row["resource_dependencies"]),
        json.dumps(row["scope_limitations"]),
        json.dumps(row["enrichment"]),
        row["confidence"],
    )


async def insert_weakness(connection: Any, row: dict[str, Any]) -> None:
    await connection.execute(
        """
        INSERT INTO profile_weaknesses (
            weakness_id, profile_id, description, source_ids, tags, counters,
            resource_dependencies, scope_limitations, enrichment, confidence
        )
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb,
            $8::jsonb, $9::jsonb, $10)
        """,
        row["weakness_id"],
        row["profile_id"],
        row["description"],
        json.dumps(row["source_ids"]),
        json.dumps(row["tags"]),
        json.dumps(row["counters"]),
        json.dumps(row["resource_dependencies"]),
        json.dumps(row["scope_limitations"]),
        json.dumps(row["enrichment"]),
        row["confidence"],
    )


def normalize_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def normalize_compiled_row_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "item"


def unique_row_id(value: str, used_ids: set[str]) -> str:
    base = normalize_compiled_row_id(value or "item")
    candidate = base
    counter = 2
    while candidate in used_ids:
        candidate = f"{base}-{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def print_summary(summary: ImportSummary, *, dry_run: bool) -> None:
    prefix = "DRY RUN " if dry_run else ""
    print(f"{prefix}SUMMARY")
    print(f"  scanned: {summary.scanned}")
    print(f"  changed: {summary.changed}")
    print(f"  imported: {summary.imported}")
    print(f"  skipped_unchanged: {summary.skipped_unchanged}")
    print(f"  skipped_invalid: {summary.skipped_invalid}")
    print(f"  skipped_not_battle_eligible: {summary.skipped_not_battle_eligible}")
    print(f"  failed: {summary.failed}")
    for error in summary.errors:
        print(f"  error: {error}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile validated YAML profiles into Postgres")
    parser.add_argument("path", type=Path, help="Profile YAML file or directory")
    parser.add_argument("--dry-run", action="store_true", help="Validate and compile without DB writes")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first invalid profile")
    parser.add_argument("--database-url", help="Override DATABASE_URL")
    parser.add_argument(
        "--import-state-file",
        type=Path,
        default=Path("data/import_state.json"),
        help="Changed-only import state path",
    )
    parser.add_argument("--changed-only", action="store_true", help="Import only changed profiles")
    parser.add_argument(
        "--reset-import-state",
        action="store_true",
        help="Reset changed-only import state before planning",
    )
    parser.add_argument(
        "--include-needs-review",
        action="store_true",
        help="Import profiles that are not battle eligible",
    )
    parser.add_argument(
        "--wipe-profiles",
        action="store_true",
        help="Dev-only: truncate imported profile tables before import",
    )
    return parser


async def async_main(args: argparse.Namespace) -> int:
    import_state = None
    if args.changed_only:
        import_state = (
            reset_import_state(args.import_state_file)
            if args.reset_import_state
            else load_import_state(args.import_state_file)
        )
    try:
        compiled, summary = build_import_plan(
            args.path,
            ImportOptions(
                include_needs_review=args.include_needs_review,
                fail_fast=args.fail_fast,
                changed_only=args.changed_only,
                import_state=import_state,
            ),
        )
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1

    if not args.dry_run:
        try:
            await import_compiled_profiles(
                compiled,
                database_url=args.database_url or os.getenv("DATABASE_URL"),
                wipe_profiles=args.wipe_profiles,
            )
            if args.changed_only and import_state is not None:
                update_import_state_for_compiled(import_state, compiled)
                write_import_state_atomic(args.import_state_file, import_state)
        except Exception as exc:
            summary.failed += 1
            summary.errors.append(f"database import failed: {exc}")

    print_summary(summary, dry_run=args.dry_run)
    return 1 if summary.failed else 0


def main() -> None:
    parser = build_arg_parser()
    raise SystemExit(asyncio.run(async_main(parser.parse_args())))


if __name__ == "__main__":
    main()
