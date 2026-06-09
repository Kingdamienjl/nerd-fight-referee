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


async def fetch_mediawiki_fields(source: dict[str, Any], parse_content) -> tuple[dict[str, str], dict[str, Any]]:
    url = str(source.get("url") or "")
    if not url:
        return {}, {"note": "missing_url"}
    api_url = mediawiki_api_from_url(url)
    title = title_from_wiki_url(url) or source.get("title")
    if not api_url or not title:
        return {}, {"note": "missing_mediawiki_title"}

    import aiohttp

    timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_connect=3, sock_read=6)
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
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "battlebot-review-repair/0.1"}) as session:
        async with session.get(api_url, params=query_params) as response:
            query_status = response.status
            body = await response.json(content_type=None)
        pages = body.get("query", {}).get("pages", [])
        if not pages:
            return {}, {
                "note": "mediawiki_no_pages",
                "fetch_status": "fetched",
                "http_status": query_status,
                "content_kind": "api_json",
                "content_length": len(str(body)),
            }
        page = pages[0]
        revision = (page.get("revisions") or [{}])[0]
        content = revision_content(revision)
        fields = parse_content(content)
        parse_body: dict[str, Any] = {}
        parse_status = None
        if len([key for key in ("attack_potency", "speed", "durability") if fields.get(key)]) < 3:
            parse_params = {
                "action": "parse",
                "page": page.get("title") or title,
                "prop": "text|sections|wikitext",
                "format": "json",
                "formatversion": "2",
            }
            async with session.get(api_url, params=parse_params) as parse_response:
                parse_status = parse_response.status
                parse_body = await parse_response.json(content_type=None)
            rendered = rendered_text_from_parse(parse_body)
            wikitext = (((parse_body.get("parse") or {}).get("wikitext") or {}).get("*") or "")
            fields = merge_extracted_fields(fields, parse_content(rendered))
            fields = merge_extracted_fields(fields, parse_content(str(wikitext)))
        metadata = {
            "title": page.get("title") or title,
            "url": page.get("fullurl") or url,
            "revision_id": str(revision.get("revid") or source.get("revision_id") or ""),
            "revision_timestamp": revision.get("timestamp"),
            "source_type": "mediawiki",
            "note": "ok" if fields else "fetched_but_no_fields",
            "fetch_status": "fetched",
            "http_status": parse_status or query_status,
            "content_length": len(content) + len(str(parse_body)),
            "content_kind": "api_json",
            "raw_content": content,
        }
        return fields, metadata
