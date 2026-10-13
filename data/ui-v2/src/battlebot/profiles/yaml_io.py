"""Safe YAML read/write helpers for generated profile files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import yaml


DEFAULT_MALFORMED_QUARANTINE_DIR = Path("profiles/quarantined/malformed_yaml")
PROFILE_ROOT_MARKERS = ("generated", "needs_review")


class YAMLProfileWriteError(RuntimeError):
    """Raised when a profile YAML write cannot be safely reloaded or validated."""


@dataclass(frozen=True)
class QuarantineResult:
    source_path: Path
    quarantine_path: Path
    report_path: Path
    error: str


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path | str) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def is_yaml_parse_error(exc: BaseException) -> bool:
    return isinstance(exc, yaml.YAMLError)


def quarantine_tail(source_path: Path) -> Path:
    parts = source_path.parts
    for marker in PROFILE_ROOT_MARKERS:
        if marker in parts:
            return Path(marker, *parts[parts.index(marker) + 1 :])
    return Path(source_path.name)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def write_quarantine_report(
    quarantine_path: Path,
    *,
    source_path: Path,
    error: BaseException | str,
) -> Path:
    report_path = unique_path(quarantine_path.with_suffix(quarantine_path.suffix + ".json"))
    report = {
        "source_path": str(source_path),
        "quarantine_path": str(quarantine_path),
        "error": str(error),
        "error_type": type(error).__name__ if isinstance(error, BaseException) else "Error",
        "quarantined_at": utc_now(),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report_path


def quarantine_file(
    source_path: Path | str,
    *,
    error: BaseException | str,
    quarantine_dir: Path | str = DEFAULT_MALFORMED_QUARANTINE_DIR,
) -> QuarantineResult:
    source = Path(source_path)
    destination = unique_path(Path(quarantine_dir) / quarantine_tail(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.replace(destination)
    report_path = write_quarantine_report(destination, source_path=source, error=error)
    return QuarantineResult(
        source_path=source,
        quarantine_path=destination,
        report_path=report_path,
        error=str(error),
    )


def write_yaml(
    path: Path | str,
    data: dict[str, Any],
    *,
    validate: Callable[[dict[str, Any]], Any] | None = None,
    quarantine_dir: Path | str = DEFAULT_MALFORMED_QUARANTINE_DIR,
    width: int | None = None,
) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.tmp")
    dump_kwargs: dict[str, Any] = {"sort_keys": False, "allow_unicode": False}
    if width is not None:
        dump_kwargs["width"] = width
    try:
        temp_path.write_text(
            yaml.safe_dump(data, **dump_kwargs),
            encoding="utf-8",
        )
        loaded = load_yaml(temp_path)
        if validate is not None:
            validate(loaded)
        temp_path.replace(target)
        return loaded
    except Exception as exc:
        if temp_path.exists():
            quarantine_file(temp_path, error=exc, quarantine_dir=quarantine_dir)
        raise YAMLProfileWriteError(f"{target}: YAML write validation failed: {exc}") from exc
