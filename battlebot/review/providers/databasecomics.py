"""DatabaseComics HTML adapter scaffold."""

from __future__ import annotations

import re


def parse_databasecomics_html(content: str) -> dict[str, str]:
    text = re.sub(r"<[^>]+>", " ", content)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return {}
    return {"identity_notes": text[:1200]}
