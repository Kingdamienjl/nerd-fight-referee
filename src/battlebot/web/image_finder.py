"""Character image lookup service using AniList and Wikimedia/Wikipedia APIs."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)

# In-memory cache for fast responses
IMAGE_CACHE: dict[str, str] = {}


async def find_character_image(name: str, franchise: str = "") -> str | None:
    """Find a high-quality portrait/artwork image URL for a given character."""
    if not name:
        return None

    clean_name = name.strip()
    cache_key = clean_name.casefold()
    if cache_key in IMAGE_CACHE:
        return IMAGE_CACHE[cache_key]

    async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
        # 1. Try AniList GraphQL (great for anime, manga, fighting games)
        try:
            graphql_query = """
            query ($search: String) {
              Character(search: $search) {
                name { full }
                image { large medium }
              }
            }
            """
            response = await client.post(
                "https://graphql.anilist.co",
                json={"query": graphql_query, "variables": {"search": clean_name}},
                headers={"User-Agent": "NerdFightReferee/1.0", "Content-Type": "application/json"},
            )
            if response.status_code == 200:
                data = response.json().get("data", {})
                char_data = data.get("Character")
                if char_data and char_data.get("image"):
                    img_url = char_data["image"].get("large") or char_data["image"].get("medium")
                    if img_url:
                        IMAGE_CACHE[cache_key] = img_url
                        return img_url
        except Exception as exc:
            LOGGER.debug("AniList search failed for %s: %s", clean_name, exc)

        # 2. Try Wikipedia / Wikimedia API (great for comics, games, mythology, sci-fi)
        try:
            # First search page titles
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_name)}&format=json&utf8=1&srlimit=1"
            res = await client.get(search_url, headers={"User-Agent": "NerdFightReferee/1.0"})
            if res.status_code == 200:
                search_results = res.json().get("query", {}).get("search", [])
                if search_results:
                    page_title = search_results[0].get("title")
                    if page_title:
                        # Fetch thumbnail
                        img_req = f"https://en.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(page_title)}&prop=pageimages&format=json&pithumbsize=600"
                        img_res = await client.get(img_req, headers={"User-Agent": "NerdFightReferee/1.0"})
                        if img_res.status_code == 200:
                            pages = img_res.json().get("query", {}).get("pages", {})
                            for page in pages.values():
                                thumb = page.get("thumbnail", {}).get("source")
                                if thumb:
                                    IMAGE_CACHE[cache_key] = thumb
                                    return thumb
        except Exception as exc:
            LOGGER.debug("Wikipedia image search failed for %s: %s", clean_name, exc)

        # 3. DuckDuckGo Instant Answer
        try:
            ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_name)}&format=json&no_html=1"
            ddg_res = await client.get(ddg_url, headers={"User-Agent": "NerdFightReferee/1.0"})
            if ddg_res.status_code == 200:
                ddg_data = ddg_res.json()
                img = ddg_data.get("Image")
                if img:
                    full_url = f"https://duckduckgo.com{img}" if img.startswith("/") else img
                    IMAGE_CACHE[cache_key] = full_url
                    return full_url
        except Exception as exc:
            LOGGER.debug("DuckDuckGo image search failed for %s: %s", clean_name, exc)

    return None
