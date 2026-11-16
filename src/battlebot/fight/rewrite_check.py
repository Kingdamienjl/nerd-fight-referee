"""Mechanical SB rewrite checker (production port).

Port of the judgments in check_rewrite.py and the structured
check_rewrite() from the Wave 1 worker (wave1_populate.py), which gated
the 18 cached Wave 1 rows:
- one-fact: flags but/and/while joins ("before" is timing, not a join --
  Chris ruling 2026-11-09); the last sentence of each phase (the analogy)
  is one rhetorical unit and is excluded from join checks.
- banned words, tier regex, and leak list identical to the prototype
  scripts.
- JOIN/semicolon hits are FLAGS for adjudication (usually compound-noun
  artifacts), NOT retry-worthy failures. Missing keys, winner/difficulty
  changes, banned/tier/leak hits, and empty phases ARE failures.
"""

from __future__ import annotations

import re
from typing import Any

BANNED = ["counterplay", "leverage", "thresholds", "deployment", "tempo"]
TIER_PAT = re.compile(r"\b\d+-[A-Z]\b|level\b|Universe\b|Multiverse\b|"
                      r"Planet\b|FTL\b|hypersonic|subsonic|relativistic|"
                      r"city block|country level|tier\b", re.IGNORECASE)
LEAK = ["Fighter A", "Fighter B", "Fighter C", "Fighter D",
        "rowboat racing a speedboat", "pebbles at a fortress",
        "running uphill", "feeling-out round", "two runners",
        "candle", "lighthouse"]
JOIN = re.compile(r"\b(but|and|while)\b", re.IGNORECASE)
REQUIRED_KEYS = ["quick_verdict", "phase_1", "phase_2", "phase_3",
                 "difficulty", "confidence", "predicted_winner"]


def sentences(text: Any) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (str(text) if text else "").strip())
    return [p.strip() for p in parts if p.strip()]


def check_rewrite(
    draft_rs: dict[str, Any], rw: Any
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Mechanical checks. Returns (unambiguous_fail, flags, detail).

    unambiguous_fail: hard failures (retry-worthy).
    flags: JOIN/semicolon hits for operator adjudication (often artifacts).
    """
    fail: list[str] = []
    flags: list[str] = []
    detail: dict[str, Any] = {}
    if not isinstance(rw, dict):
        return ["rewritten_not_object"], flags, detail
    missing = [k for k in REQUIRED_KEYS if not rw.get(k)]
    if missing:
        fail.append(f"missing_keys:{','.join(missing)}")
    if rw.get("predicted_winner") != draft_rs.get("predicted_winner"):
        fail.append("winner_changed")
    if rw.get("difficulty") != draft_rs.get("difficulty"):
        fail.append("difficulty_changed")
    narr = "\n".join([str(rw.get("quick_verdict") or ""),
                      str(rw.get("phase_1") or ""),
                      str(rw.get("phase_2") or ""),
                      str(rw.get("phase_3") or "")])
    banned = []
    for line in narr.split("\n"):
        for w in BANNED:
            if re.search(r"\b" + w + r"\b", line, re.IGNORECASE):
                banned.append(f"{w}: {line.strip()[:160]}")
                break
    if banned:
        fail.append("banned")
    detail["banned"] = banned
    tier = []
    for line in narr.split("\n"):
        # "Ornitier" is a known false positive: re-test without the name.
        if TIER_PAT.search(line) and TIER_PAT.search(line.replace("Ornitier", "")):
            tier.append(line.strip()[:160])
    if tier:
        fail.append("tier")
    detail["tier"] = tier
    leak = [l.strip()[:160] for l in narr.split("\n")
            for p in LEAK if p.lower() in l.lower()]
    if leak:
        fail.append("leak")
    detail["leak"] = leak
    for key in ["quick_verdict", "phase_1", "phase_2", "phase_3"]:
        ss = sentences(rw.get(key) or "")
        for i, s in enumerate(ss):
            last = (key != "quick_verdict" and i == len(ss) - 1)
            if last:
                continue
            m = JOIN.search(s)
            if m:
                flags.append(f"{key} S{i+1} join:{m.group(1)}: {s[:160]}")
            if ";" in s:
                flags.append(f"{key} S{i+1} semicolon: {s[:160]}")
    detail["join_flags"] = flags
    # Analogy last-sentence presence (mechanical: phase has >=1 sentence).
    for key in ["phase_1", "phase_2", "phase_3"]:
        if not sentences(rw.get(key) or ""):
            fail.append(f"empty_{key}")
    return fail, flags, detail
