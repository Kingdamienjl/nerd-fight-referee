"""Read-only audit of the most-fought profiles.

Fighters are ranked by how often they appear in discord_command_audit
(contender_a + contender_b mentions); the TOP N are audited, because
one bad profile poisons every duel it fights. Per profile:

- assess_readiness (the same gate the import uses) + missing core
  fields,
- a debris scan: crushed multi-ability names ("*" residue, the Luffy
  class), overlong ability names, and the H1/H2 wiki-footer / editor
  -note sentences filed as list items,
- a YAML parse check on the live profile file (the Trunks/Rimuru
  undefined-anchor class).

Nothing here writes to the database or any profile. Resolution uses
the same battlebot.profiles.store.resolve_character the fight path
uses, so "most-fought" means the fighters users actually fought.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from battlebot.profiles.readiness import assess_readiness
from battlebot.review.service import missing_core_fields

# H1/H2 debris patterns, verbatim from the frag-13 screens in
# battlebot/review/auto_repair.py (footer instruction + editor note
# filed as list items).
FOOTER_INSTRUCTION_RE = re.compile(r"(?i)you can judge a person['\u2019]s power by their feats")
EDITOR_NOTE_UNFINISHED_RE = re.compile(r"(?i)so far from done")
MAX_ABILITY_NAME_LEN = 120  # the item builder truncates at 120

FIGHT_COUNTS_SQL = "SELECT options_json FROM discord_command_audit"

PROFILE_PATH_SQL = """SELECT profile_path FROM character_profiles
    WHERE profile_id = $1 ORDER BY updated_at DESC LIMIT 1"""


def normalize_fighter_name(value: Any) -> str:
    """Lookup key: stripped, casefolded, whitespace collapsed."""
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def rank_fighters(
    options_rows: list[Any],
) -> list[dict[str, Any]]:
    """Count contender mentions across audit rows.

    options_rows are raw options_json values (dicts or JSON strings).
    Returns [{"name", "display", "fights"}] sorted by fights desc,
    then name asc -- deterministic for ties.
    """
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for raw in options_rows:
        if isinstance(raw, str):
            import json

            try:
                opts = json.loads(raw)
            except (ValueError, TypeError):
                continue
        else:
            opts = raw
        if not isinstance(opts, dict):
            continue
        for key in ("contender_a", "contender_b"):
            name = opts.get(key)
            if not name:
                continue
            norm = normalize_fighter_name(name)
            if not norm:
                continue
            counts[norm] = counts.get(norm, 0) + 1
            display.setdefault(norm, str(name).strip())
    return [
        {"name": name, "display": display[name], "fights": counts[name]}
        for name in sorted(counts, key=lambda n: (-counts[n], n))
    ]


async def fetch_fight_counts(conn: Any) -> list[dict[str, Any]]:
    """Ranked fighter list from discord_command_audit. Read-only."""
    rows = await conn.fetch(FIGHT_COUNTS_SQL)
    return rank_fighters([r["options_json"] for r in rows])


def debris_scan(profile: dict[str, Any]) -> list[str]:
    """Debris signals in abilities/weaknesses list items.

    - "*" inside an ability name: crushed multi-ability entry (the
      Luffy "Stealth Mastery ... *Supernatural Willpower" class).
    - names over 120 chars: the item builder truncates there, so a
      longer name is extraction debris, not a real ability.
    - H1 footer instruction / H2 editor note filed as an item.
    Bare short names ("Flight", "Magic") are legitimate and never
    flagged.
    """
    findings: list[str] = []
    for section in ("abilities", "weaknesses"):
        for item in profile.get(section) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            desc = str(item.get("description") or "")
            if "*" in name:
                findings.append(f"star_residue:{section}:{name[:100]}")
            if len(name) > MAX_ABILITY_NAME_LEN:
                findings.append(f"overlong_name:{section}:{len(name)}:{name[:60]}")
            for text in (name, desc):
                if FOOTER_INSTRUCTION_RE.search(text):
                    findings.append(f"h1_footer_instruction:{section}")
                    break
            for text in (name, desc):
                if EDITOR_NOTE_UNFINISHED_RE.search(text):
                    findings.append(f"h2_editor_note:{section}")
                    break
    return sorted(set(findings))


def _yaml_parse_check(path: Path | None) -> list[str]:
    """Parse the live profile file: unparseable YAML is a finding,
    a missing file is a finding, a clean parse is silence."""
    if path is None:
        return ["profile_path_unknown"]
    if not path.exists():
        return [f"profile_file_missing:{path}"]
    try:
        with open(path, encoding="utf-8") as handle:
            yaml.safe_load(handle)
    except Exception as exc:
        return [f"yaml_unparseable:{type(exc).__name__}:{str(exc)[:160]}"]
    return []


async def audit_one_profile(
    conn: Any,
    resolution: dict[str, Any],
    *,
    repo_root: Path,
    fight_count: int = 0,
    query: str = "",
) -> dict[str, Any]:
    """Audit a single resolved fighter. Read-only."""
    profile = resolution.get("profile") or {}
    profile_json = profile.get("profile_json") or {}
    finding: dict[str, Any] = {
        "query": query,
        "fights": fight_count,
        "character_id": profile.get("character_id"),
        "canonical_name": profile.get("canonical_name"),
        "matched_by": resolution.get("matched_by"),
        "battle_eligible": profile.get("battle_eligible"),
        "profile_hash": profile.get("profile_hash"),
        "profile_path": None,
        "battle_ready": None,
        "blockers": [],
        "missing_core_fields": [],
        "debris": [],
        "yaml": [],
    }
    readiness = assess_readiness(profile_json)
    finding["battle_ready"] = readiness.get("battle_ready")
    finding["blockers"] = list(readiness.get("blockers") or [])
    finding["missing_core_fields"] = missing_core_fields(profile_json)
    finding["debris"] = debris_scan(profile_json)
    profile_id = profile.get("profile_id")
    path: Path | None = None
    if profile_id:
        row = await conn.fetchrow(PROFILE_PATH_SQL, profile_id)
        if row and row.get("profile_path"):
            finding["profile_path"] = row["profile_path"]
            path = repo_root / str(row["profile_path"])
    finding["yaml"] = _yaml_parse_check(path)
    return finding


async def audit_top_profiles(
    conn: Any,
    *,
    top_n: int = 20,
    repo_root: Path,
) -> dict[str, Any]:
    """Rank fighters, resolve + audit the top N. Read-only."""
    from battlebot.profiles.store import resolve_character

    ranked = await fetch_fight_counts(conn)
    top = ranked[:top_n]
    audited: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for entry in top:
        try:
            resolution = await resolve_character(conn, entry["display"], battle_eligible_only=True)
        except Exception as exc:  # one bad name never kills the run
            unresolved.append(
                {
                    "query": entry["display"],
                    "fights": entry["fights"],
                    "status": f"error:{type(exc).__name__}",
                }
            )
            continue
        if resolution.get("status") != "resolved":
            unresolved.append(
                {
                    "query": entry["display"],
                    "fights": entry["fights"],
                    "status": str(resolution.get("status")),
                    "candidates": len(resolution.get("candidates") or []),
                }
            )
            continue
        audited.append(
            await audit_one_profile(
                conn,
                resolution,
                repo_root=repo_root,
                fight_count=entry["fights"],
                query=entry["display"],
            )
        )
    flagged = [
        f
        for f in audited
        if f["blockers"]
        or f["missing_core_fields"]
        or f["debris"]
        or f["yaml"]
        or f["battle_ready"] is not True
    ]
    return {
        "ranked_total": len(ranked),
        "top_n": top_n,
        "audited": audited,
        "unresolved": unresolved,
        "flagged": flagged,
        "clean": len(audited) - len(flagged),
    }
