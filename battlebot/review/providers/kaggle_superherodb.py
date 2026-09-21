"""Local Kaggle SuperHeroDB dataset adapter."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET_PATH = Path("data/external/superherodb")


def find_dataset_files(root: Path = DEFAULT_DATASET_PATH) -> list[Path]:
    if not root.exists():
        return []
    return sorted([*root.glob("*.csv"), *root.glob("*.json")])


def row_matches(row: dict[str, Any], name: str) -> bool:
    wanted = name.casefold()
    candidates = [row.get("name"), row.get("full-name"), row.get("full_name")]
    return any(str(candidate or "").casefold() == wanted for candidate in candidates)


def fields_from_row(row: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    aliases = row.get("aliases") or row.get("alter-egos") or row.get("alter_egos")
    if aliases:
        fields["aliases"] = str(aliases)
    identity = []
    for key in ("publisher", "alignment", "place-of-birth", "first-appearance"):
        if row.get(key):
            identity.append(f"{key}: {row[key]}")
    if identity:
        fields["identity_notes"] = "; ".join(identity)
    stats = []
    for key in ("intelligence", "strength", "speed", "durability", "power", "combat"):
        if row.get(key) not in (None, ""):
            stats.append(f"{key}: {row[key]}")
    if stats:
        fields["stat_notes"] = "; ".join(stats)
    return fields


def load_local_fields(name: str, root: Path = DEFAULT_DATASET_PATH) -> tuple[dict[str, str], dict[str, Any]]:
    files = find_dataset_files(root)
    if not files:
        return {}, {"note": "local_dataset_missing", "fetch_status": "skipped"}
    for path in files:
        if path.suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if row_matches(row, name):
                        return fields_from_row(row), {"note": "ok", "fetch_status": "local", "url": str(path)}
        elif path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("rows", [])
            for row in rows:
                if isinstance(row, dict) and row_matches(row, name):
                    return fields_from_row(row), {"note": "ok", "fetch_status": "local", "url": str(path)}
    return {}, {"note": "local_dataset_no_match", "fetch_status": "local"}
