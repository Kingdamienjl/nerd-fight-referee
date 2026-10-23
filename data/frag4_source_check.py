#!/usr/bin/env python3
"""Frag-4 50h: verify two suspect weakness merges against their
live source pages (fetch the page, print its weaknesses section)."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import aiohttp

from battlebot.profiles import yaml_io
from battlebot.review.providers import mediawiki

TARGETS = {
    "profiles/needs_review/comic/dc/raven-rebirth.yaml": (
        "have it carry her",
        "use it to absorb energy",
    ),
    "profiles/needs_review/comic/dc/raven-prime-earth.yaml": (
        "Can be sometimes exhausted by using her",
    ),
}


async def main() -> int:
    async with aiohttp.ClientSession() as session:
        for rel, needles in TARGETS.items():
            profile = yaml_io.load_yaml(Path("/app") / rel)
            print(f"== {rel}")
            src_by_id = {
                str(s.get("id")): s
                for s in profile.get("sources") or []
                if isinstance(s, dict)
            }
            urls = []
            for item in profile.get("weaknesses") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "")
                if any(n in name for n in needles) or "Soul Self" in name:
                    print(f"   ITEM name={name!r}")
                    print(f"        desc={str(item.get('description') or '')!r}")
                    for sid in item.get("source_ids") or []:
                        src = src_by_id.get(str(sid))
                        if src and src.get("url"):
                            print(f"        source: {src.get('title')} {src.get('url')}")
                            urls.append((str(src.get("title")), str(src.get("url"))))
            for title, url in dict.fromkeys(urls):
                api = mediawiki.resolve_mediawiki_api_url(url)
                if not api:
                    continue
                async with session.get(api, params={
                    "action": "query", "format": "json", "formatversion": "2",
                    "prop": "revisions", "rvprop": "content", "rvslots": "main",
                    "titles": title,
                }) as resp:
                    body = await resp.json(content_type=None)
                pages = ((body or {}).get("query") or {}).get("pages") or []
                raw = ""
                if pages:
                    revs = pages[0].get("revisions") or []
                    if revs:
                        raw = str(((revs[0].get("slots") or {}).get("main") or {}).get("content") or "")
                idx = raw.casefold().find("weakness")
                print(f"   PAGE {title}: raw_len={len(raw)}")
                print("   ", raw[max(0, idx - 50): idx + 700].replace("\n", " ")[:760])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
