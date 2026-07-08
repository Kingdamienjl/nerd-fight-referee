from __future__ import annotations

import re
from typing import Iterable

_BAD_EXACT = {
    "",
    "standard",
    "base",
    "same as before",
    "no named tools supplied",
    "powers &",
    "padding=yes",
    "= victories",
}

_BAD_PATTERNS = [
    re.compile(r"\bpadding\s*=\s*yes\b", re.I),
    re.compile(r"\bcategory\s*:\s*characters\b", re.I),
    re.compile(r"\bch\s*=\s*\d+\b", re.I),
    re.compile(r"\b\d+\s*&\s*\d+\b", re.I),
    re.compile(r"\b\d+\s+category\b", re.I),
    re.compile(r"^[=\-\s]*victories[=\-\s]*$", re.I),
    re.compile(r"^[a-z ]*▼$", re.I),
    re.compile(r"^base\s*▼$", re.I),
    re.compile(r"^pre\s*/?\s*during training\s*▼$", re.I),
    re.compile(r"^powers\s*&$", re.I),
]

_SOURCE_NOISE = [
    re.compile(r"\bchapter\s*\d+\b", re.I),
    re.compile(r"\bvol\.?\s*\d+\b", re.I),
    re.compile(r"\bissue\s*#?\d+\b", re.I),
    re.compile(r"\bpage\s*\d+\b", re.I),
    re.compile(r"\b\d+(\.\d+)?\s*(tons|kilotons|megatons|gigatons|teratons|petatons|zettatons|yottatons)\b", re.I),
    re.compile(r"\bmach\s*\d+(\.\d+)?\b", re.I),
    re.compile(r"\b\d+(\.\d+)?\s*c\b", re.I),
]

def clean_public_text(value: object, *, max_len: int = 120) -> str:
    text = "" if value is None else str(value)
    text = text.replace("▾", "").replace("▼", "")
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")

    if not text:
        return ""

    lower = text.lower().strip(" ,.;:-")
    if lower in _BAD_EXACT:
        return ""

    for pat in _BAD_PATTERNS:
        if pat.search(text):
            return ""

    # Remove obvious wiki/category/source fragments.
    text = re.sub(r"\bCategory:[A-Za-z0-9_ /-]+", "", text)
    text = re.sub(r"\b\d+\s*Category:[^,.;]+", "", text)
    text = re.sub(r"\bch\s*=\s*\d+\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")

    if not text:
        return ""

    # Drop source-dump sentences unless they are short enough to be readable.
    noisy_hits = sum(1 for pat in _SOURCE_NOISE if pat.search(text))
    if noisy_hits >= 2 and len(text) > 90:
        return ""

    if len(text) > max_len:
        text = text[: max_len - 3].rstrip(" ,.;:-") + "..."

    return text

def clean_public_list(values: Iterable[object], *, max_items: int = 3, max_len: int = 80) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in values or []:
        text = clean_public_text(value, max_len=max_len)
        if not text:
            continue

        key = text.lower()
        if key in seen:
            continue

        seen.add(key)
        cleaned.append(text)

        if len(cleaned) >= max_items:
            break

    return cleaned

def fallback_public_list(values: Iterable[object], fallback: str, *, max_items: int = 3, max_len: int = 80) -> list[str]:
    cleaned = clean_public_list(values, max_items=max_items, max_len=max_len)
    return cleaned or [fallback]
