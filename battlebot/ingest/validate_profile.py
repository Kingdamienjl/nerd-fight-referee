"""Validate generated character profile YAML files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from battlebot.schemas.profile import CharacterProfile


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("profile YAML root must be an object")
    return data


def validate_file(path: Path) -> list[str]:
    try:
        CharacterProfile.model_validate(load_yaml(path))
    except ValidationError as exc:
        return [f"{error['loc']}: {error['msg']}" for error in exc.errors()]
    except Exception as exc:
        return [str(exc)]
    return []


def profile_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.rglob("*.yaml"))
    return [path]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate enriched profile YAML")
    parser.add_argument("path", type=Path, help="Profile YAML file or directory")
    args = parser.parse_args()

    paths = profile_paths(args.path)
    if not paths:
        print(f"INVALID {args.path}: no YAML files found")
        raise SystemExit(1)

    invalid_count = 0
    for path in paths:
        errors = validate_file(path)
        if errors:
            invalid_count += 1
            print(f"INVALID {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"VALID {path}")

    if invalid_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
