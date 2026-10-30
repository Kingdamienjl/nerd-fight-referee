"""Enumerate vsbattles verse-category members into roster rows.

Read-only network use (MediaWiki categorymembers API) + pure filtering.
This module never touches the DB and never writes files; the data/ runner
owns dedupe-against-DB and CSV writing.

Every VERSE_CATEGORIES entry was verified against the live API
(categoryinfo existence + member count) 2026-10-26. Category names are
inconsistent per verse -- a wrong name silently returns an empty list,
so do not add an entry without verifying it first.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) nerd-referee-intake/1.0"
API_URL = "https://vsbattles.fandom.com/api.php"
WIKI_BASE = "https://vsbattles.fandom.com/wiki/"

# (roster category, franchise) -> vsbattles category title.
VERSE_CATEGORIES: dict[tuple[str, str], str] = {
    ("comic", "Marvel"): "Marvel_Comics",
    ("comic", "DC"): "DC_Comics",
    ("anime", "Dragon Ball"): "Dragon_Ball",
    ("anime", "Hunter x Hunter"): "Hunter_X_Hunter",
    ("anime", "My Hero Academia"): "My_Hero_Academia",
    ("anime", "JoJo's Bizarre Adventure"): "JoJo's_Bizarre_Adventure",
    ("anime", "One Piece"): "One_Piece",
    ("anime", "Naruto"): "Naruto",
    ("anime", "Bleach"): "Bleach",
    ("anime", "Jujutsu Kaisen"): "Jujutsu_Kaisen",
    ("anime", "Chainsaw Man"): "Chainsaw_Man",
    ("anime", "Berserk"): "Berserk",
    ("anime", "Fullmetal Alchemist"): "Fullmetal_Alchemist",
    ("anime", "Digimon"): "Digimon",
    ("anime", "Gundam"): "Gundam",
    ("anime", "Pokemon"): "Pokémon",
    ("game", "Tekken"): "Tekken",
    ("game", "Street Fighter"): "Street_Fighter",
    ("game", "Virtua Fighter"): "Virtua_Fighter",
    ("game", "Final Fantasy"): "Final_Fantasy",
    ("game", "Mortal Kombat"): "Mortal_Kombat",
    ("game", "Guilty Gear"): "Guilty_Gear",
    ("game", "Resident Evil"): "Resident_Evil",
    ("game", "Persona"): "Persona",
    ("game", "Kingdom Hearts"): "Kingdom_Hearts",
    ("game", "Castlevania"): "Castlevania",
    ("game", "Soul Calibur"): "Soul_Calibur",
    ("game", "Monster Hunter"): "Monster_Hunter",
    ("game", "Dark Souls"): "Dark_Souls",
    ("mixed", "Godzilla"): "Godzilla_(Toho)",
    ("mixed", "Power Rangers"): "Power_Rangers",
    ("mixed", "Kamen Rider"): "Kamen_Rider",
    ("mixed", "Breaking Bad"): "Breaking_Bad",
}

_REJECTED_PREFIXES = (
    "User blog:",
    "User:",
    "File:",
    "Template:",
    "Category:",
    "MediaWiki:",
    "Help:",
    "Thread:",
    "Message Wall:",
    "Blog:",
    "Forum:",
)


def is_candidate_title(title: str, exclude: tuple[str, ...] = ()) -> bool:
    """True when a category member looks like a fetchable character page.

    Rejects namespaced junk (User blog:, File:, ...), user-variant subpages
    ("Title/Author" -- those are CSPW-style user pages, not canonical
    character pages), blanks, and anything in `exclude` (used for the
    verse page itself, e.g. "Marvel Comics" inside Category:Marvel_Comics).
    Deliberately permissive otherwise: "007", team pages, and verse pages
    that slip through are the harvester identity guard's job, not this
    filter's.
    """
    if not title or not title.strip():
        return False
    title = title.strip()
    if "/" in title:
        return False
    if title.startswith(_REJECTED_PREFIXES):
        return False
    return title.casefold() not in {item.casefold() for item in exclude}


def filter_members(titles: list[str], exclude: tuple[str, ...] = ()) -> list[str]:
    """Dedupe (casefold, first occurrence wins) + candidate filter."""
    seen: set[str] = set()
    kept: list[str] = []
    for title in titles:
        if not is_candidate_title(title, exclude):
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        kept.append(title)
    return kept


def fetch_category_members(category: str, opener=None) -> list[str]:
    """Paginated categorymembers fetch. Returns raw member titles.

    `opener` is an injectable callable taking a urllib Request and returning
    a response with .read() (unit tests pass a fake); default is the real
    urlopen with the module User-Agent (Fandom 403s bare Python UAs).
    """
    titles: list[str] = []
    cont: str | None = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": "page",
            "cmlimit": "500",
            "format": "json",
        }
        if cont:
            params["cmcontinue"] = cont
        url = API_URL + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        response = opener(request) if opener is not None else urllib.request.urlopen(request, timeout=30)
        data = json.loads(response.read().decode("utf-8"))
        titles.extend(member["title"] for member in data.get("query", {}).get("categorymembers", []))
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
    return titles


def roster_rows(category: str, franchise: str, titles: list[str]) -> list[dict[str, str]]:
    """Build roster rows (ROSTER_HEADER order). Name == wiki_title here:
    category titles already carry their disambiguator ("Abomination (Marvel
    Comics)"), and the harvester identity guard matches on the fetched
    title, so the full title is the safest roster name."""
    rows: list[dict[str, str]] = []
    for title in titles:
        slug = urllib.parse.quote(title.replace(" ", "_"), safe="()_")
        rows.append(
            {
                "category": category,
                "franchise": franchise,
                "name": title,
                "aliases": "",
                "wiki_title": title,
                "wiki_url": f"{WIKI_BASE}{slug}",
            }
        )
    return rows


def dedupe_rows(
    rows: list[dict[str, str]],
    existing_keys: set[tuple[str, str, str]],
    db_names: set[str],
) -> list[dict[str, str]]:
    """Drop rows already in a roster CSV (casefold (category, franchise,
    name)) or already in the DB (casefold canonical_name)."""
    kept: list[dict[str, str]] = []
    for row in rows:
        key = (row["category"].casefold(), row["franchise"].casefold(), row["name"].casefold())
        if key in existing_keys:
            continue
        if row["name"].casefold() in db_names:
            continue
        kept.append(row)
    return kept
