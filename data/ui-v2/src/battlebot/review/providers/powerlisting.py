"""Powerlisting adapter for ability taxonomy pages."""

from __future__ import annotations

import re


def parse_ability_taxonomy(content: str) -> dict[str, str]:
    text = re.sub(r"<[^>]+>", " ", content)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return {}
    return {"ability_definitions": text[:2000]}
