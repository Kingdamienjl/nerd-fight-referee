"""File-backed character alias overrides."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_ALIAS_PATH = Path("profiles/overrides/character_aliases.yaml")


@dataclass(frozen=True)
class AliasMatch:
    query: str
    canonical: str
    matched_key: str
    notes: str = ""


def normalize_alias(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def compact_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def alias_keys(value: str) -> set[str]:
    normalized = normalize_alias(value)
    no_punctuation = re.sub(r"[^a-z0-9\s-]+", "", normalized)
    hyphen_as_space = no_punctuation.replace("-", " ")
    collapsed = normalize_alias(hyphen_as_space)
    return {
        normalized,
        no_punctuation,
        collapsed,
        compact_alias_key(normalized),
        compact_alias_key(collapsed),
    }


def load_aliases(path: Path | str = DEFAULT_ALIAS_PATH) -> dict[str, dict[str, Any]]:
    alias_path = Path(path)
    if not alias_path.exists():
        return {}
    data = yaml.safe_load(alias_path.read_text(encoding="utf-8")) or {}
    aliases = data.get("aliases") or {}
    return aliases if isinstance(aliases, dict) else {}


def alias_index(path: Path | str = DEFAULT_ALIAS_PATH) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for raw_key, value in load_aliases(path).items():
        entry = value if isinstance(value, dict) else {"canonical": str(value)}
        canonical = str(entry.get("canonical") or "").strip()
        if not canonical:
            continue
        notes = str(entry.get("notes") or "")
        for key in alias_keys(str(raw_key)):
            index[key] = {"canonical": canonical, "matched_key": str(raw_key), "notes": notes}
    return index


def resolve_alias(query: str, path: Path | str = DEFAULT_ALIAS_PATH) -> AliasMatch | None:
    index = alias_index(path)
    for key in alias_keys(query):
        entry = index.get(key)
        if entry:
            return AliasMatch(query=query, canonical=entry["canonical"], matched_key=entry["matched_key"], notes=entry["notes"])
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve character alias overrides")
    parser.add_argument("query")
    parser.add_argument("--alias-path", type=Path, default=DEFAULT_ALIAS_PATH)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    match = resolve_alias(args.query, args.alias_path)
    if match:
        print(f"{args.query} -> {match.canonical} ({match.matched_key})")
    else:
        print(f"{args.query}: no alias override")


if __name__ == "__main__":
    main()
