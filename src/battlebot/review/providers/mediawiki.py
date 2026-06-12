"""MediaWiki provider adapter for battle-stat style pages."""

from __future__ import annotations

from typing import Any

from battlebot.harvest.auto_profile_harvester import (
    mediawiki_api_from_url,
    merge_extracted_fields,
    rendered_text_from_parse,
    revision_content,
    title_from_wiki_url,
)


CORE_FIELDS = ("attack_potency", "speed", "durability")


def core_count(fields: dict[str, str]) -> int:
    return len([key for key in CORE_FIELDS if fields.get(key)])


async def fetch_title_fields(
    session: Any,
    api_url: str,
    title: str,
    source: dict[str, Any],
    parse_content,
) -> tuple[dict[str, str], dict[str, Any]]:
    query_params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "prop": "revisions|info",
        "inprop": "url",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "titles": title,
        "redirects": "1",
    }
    async with session.get(api_url, params=query_params) as response:
        query_status = response.status
        body_value = await response.json(content_type=None)
    body = body_value if isinstance(body_value, dict) else {}
    pages = body.get("query", {}).get("pages", [])
    if not pages:
        return {}, {
            "note": "not_found",
            "fetch_status": "not_found",
            "http_status": query_status,
            "content_kind": "api_json",
            "content_length": len(str(body)),
        }
    page = pages[0]
    if page.get("missing"):
        return {}, {
            "title": page.get("title") or title,
            "note": "not_found",
            "fetch_status": "not_found",
            "http_status": query_status,
            "content_kind": "api_json",
            "content_length": len(str(body)),
        }
    revision = (page.get("revisions") or [{}])[0]
    content = revision_content(revision)
    fields = parse_content(content)
    parse_body: dict[str, Any] = {}
    parse_status = None
    if core_count(fields) < 3:
        parse_params = {
            "action": "parse",
            "page": page.get("title") or title,
            "prop": "text|sections|wikitext",
            "format": "json",
            "formatversion": "2",
        }
        async with session.get(api_url, params=parse_params) as parse_response:
            parse_status = parse_response.status
            parse_body_value = await parse_response.json(content_type=None)
            parse_body = parse_body_value if isinstance(parse_body_value, dict) else {}
        rendered = rendered_text_from_parse(parse_body)

        parse_value = parse_body.get("parse")
        parse_data = parse_value if isinstance(parse_value, dict) else {}
        wikitext_value = parse_data.get("wikitext")

        if isinstance(wikitext_value, str):
            wikitext = wikitext_value
        elif isinstance(wikitext_value, dict):
            wikitext = str(
                wikitext_value.get("*")
                or wikitext_value.get("content")
                or wikitext_value.get("text")
                or ""
            )
        else:
            wikitext = ""

        fields = merge_extracted_fields(fields, parse_content(rendered))
        fields = merge_extracted_fields(fields, parse_content(wikitext))
    metadata = {
        "title": page.get("title") or title,
        "url": page.get("fullurl") or source.get("url") or "",
        "revision_id": str(revision.get("revid") or source.get("revision_id") or ""),
        "revision_timestamp": revision.get("timestamp"),
        "source_type": "mediawiki",
        "note": "ok" if fields else "parser_empty",
        "fetch_status": "fetched",
        "http_status": parse_status or query_status,
        "content_length": len(content) + len(str(parse_body)),
        "content_kind": "api_json",
        "raw_content": content,
    }
    if fields and core_count(fields) < 3:
        metadata["note"] = "fetched_no_core_fields"
    return fields, metadata


async def search_titles(session: Any, api_url: str, query: str, limit: int = 5) -> list[str]:
    titles: list[str] = []
    opensearch_params = {
        "action": "opensearch",
        "search": query,
        "limit": limit,
        "format": "json",
    }
    async with session.get(api_url, params=opensearch_params) as response:
        if response.status == 200:
            body_value = await response.json(content_type=None)
            body = body_value if isinstance(body_value, (dict, list)) else {}
            if isinstance(body, list) and len(body) > 1 and isinstance(body[1], list):
                titles.extend(str(title) for title in body[1])
    query_params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
        "formatversion": "2",
    }
    async with session.get(api_url, params=query_params) as response:
        if response.status == 200:
            body_value = await response.json(content_type=None)
            body = body_value if isinstance(body_value, dict) else {}
            for row in (body.get("query") or {}).get("search") or []:
                if row.get("title"):
                    titles.append(str(row["title"]))
    seen = set()
    unique = []
    for title in titles:
        key = title.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(title)
    return unique


def resolve_mediawiki_api_url(url: str) -> str:
    """Resolve an Action API endpoint from a MediaWiki/Fandom URL."""
    api_url = mediawiki_api_from_url(url)
    if api_url:
        return api_url

    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc.casefold()

    if (
        parsed.scheme in {"http", "https"}
        and (host == "fandom.com" or host.endswith(".fandom.com"))
    ):
        return f"{parsed.scheme}://{parsed.netloc}/api.php"

    return ""


async def fetch_mediawiki_fields(source: dict[str, Any], parse_content) -> tuple[dict[str, str], dict[str, Any]]:
    url = str(source.get("url") or "")
    if not url:
        return {}, {"note": "missing_url"}
    api_url = resolve_mediawiki_api_url(url)
    title = title_from_wiki_url(url) or source.get("title")
    if not title:
        return {}, {"note": "missing_mediawiki_title"}
    if not api_url:
        return {}, {"note": "missing_mediawiki_api_url"}

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_connect=3, sock_read=6)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "battlebot-review-repair/0.1"}) as session:
        attempted: list[str] = []
        best_fields: dict[str, str] = {}
        best_metadata: dict[str, Any] = {}
        search_queries = [
            str(source.get("title") or title),
            str(source.get("search_query") or ""),
            str(source.get("notes") or ""),
        ]
        search_found_results = False
        for query in [item for item in search_queries if item.strip()]:
            for candidate_title in await search_titles(session, api_url, query):
                search_found_results = True
                if candidate_title in attempted:
                    continue
                attempted.append(candidate_title)
                candidate_fields, candidate_metadata = await fetch_title_fields(
                    session,
                    api_url,
                    candidate_title,
                    source,
                    parse_content,
                )
                candidate_metadata["search_attempted_titles"] = attempted
                if core_count(candidate_fields) >= 3 or candidate_fields.get("powers_and_abilities"):
                    candidate_metadata["note"] = "extracted_core_fields"
                    return candidate_fields, candidate_metadata
                if len(candidate_fields) > len(best_fields):
                    best_fields = candidate_fields
                    best_metadata = candidate_metadata
        if str(title) not in attempted:
            attempted.append(str(title))
            direct_fields, direct_metadata = await fetch_title_fields(session, api_url, str(title), source, parse_content)
            direct_metadata["search_attempted_titles"] = attempted
            if core_count(direct_fields) >= 3 or direct_fields.get("powers_and_abilities"):
                direct_metadata["note"] = "extracted_core_fields"
                return direct_fields, direct_metadata
            if len(direct_fields) > len(best_fields):
                best_fields = direct_fields
                best_metadata = direct_metadata
        best_metadata.setdefault("search_attempted_titles", attempted)
        if not search_found_results:
            best_metadata["note"] = "provider_search_no_results"
        elif best_fields:
            best_metadata["note"] = "fetched_no_core_fields"
        else:
            best_metadata["note"] = "ambiguous_candidates" if len(attempted) > 1 else "parser_empty"
        return best_fields, best_metadata
