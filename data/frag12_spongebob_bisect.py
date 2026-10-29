"""SpongeBob bisect probe (read-only): time each post-fetch step of the
recovery path for source 1, writing progress lines to a file as it goes
so a hang leaves a trail showing exactly which step stalled.
Steps: (1) fetch_mediawiki_fields, (2) categories fetch,
(3) rendered-HTML fetch (action=parse), (4) run_parse_fallback_chain.
"""
import asyncio
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import aiohttp
import yaml

from battlebot.review import auto_repair as ar
from battlebot.review import service
from battlebot.review.providers import mediawiki
from battlebot.harvest.fallback_parsers import run_parse_fallback_chain

LOG = open("/tmp/sponge_bisect.log", "w", encoding="utf-8")


def log(msg):
    LOG.write(msg + "\n")
    LOG.flush()
    print(msg, flush=True)


async def main():
    prof = yaml.load(
        open("/app/profiles/needs_review/mixed/adult-cartoons/spongebob-squarepants.yaml"),
        Loader=yaml.CSafeLoader,
    ) or {}
    source = [s for s in prof.get("sources") or [] if isinstance(s, dict)][0]
    log(f"source: {source.get('url')}")
    t0 = time.monotonic()
    fields, meta = await mediawiki.fetch_mediawiki_fields(source, ar.parse_source_content)
    log(f"step1 fetch_mediawiki_fields wall={time.monotonic()-t0:.1f}s "
        f"status={meta.get('fetch_status')} fields={len(fields)} "
        f"raw_len={len(str(meta.get('raw_content') or ''))}")
    wikitext = str(meta.get("raw_content") or "")
    fetched_title = str(meta.get("title") or source.get("title") or "")
    api_url = mediawiki.resolve_mediawiki_api_url(str(source.get("url") or ""))
    timeout = aiohttp.ClientTimeout(total=20, connect=3, sock_connect=3, sock_read=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        t0 = time.monotonic()
        cats = await ar._fetch_page_categories(session, api_url, fetched_title)
        log(f"step2 categories wall={time.monotonic()-t0:.1f}s n={len(cats)}")
        t0 = time.monotonic()
        params = {"action": "parse", "page": fetched_title, "prop": "text",
                  "format": "json", "formatversion": "2"}
        async with session.get(api_url, params=params) as response:
            body = await response.json(content_type=None)
        html_text = str(((body or {}).get("parse") or {}).get("text") or "")
        log(f"step3 rendered_html wall={time.monotonic()-t0:.1f}s html_len={len(html_text)}")
    async def _cached_html():
        return html_text

    t0 = time.monotonic()
    log("step4 run_parse_fallback_chain starting...")
    parsed = await run_parse_fallback_chain(
        wikitext=wikitext, title=fetched_title,
        fetch_rendered_html=_cached_html,
    )
    log(f"step4 parse_chain wall={time.monotonic()-t0:.1f}s keys={list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__}")
    log("BISECT-DONE")


asyncio.run(main())
