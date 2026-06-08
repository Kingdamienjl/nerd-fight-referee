"""Local src-layout import shim for `python3 -m battlebot...` from the repo root."""

from pathlib import Path

_src_package = Path(__file__).resolve().parent.parent / "src" / "battlebot"
if _src_package.is_dir():
    __path__.append(str(_src_package))
