"""SpongeBob fetch diagnosis (read-only, network fetch with a hard cap).

Times fetch_mediawiki_fields for SpongeBob's first recorded source,
candidate by candidate, to find where the recovery run stalls: how many
search candidates, per-fetch wall time, and response sizes. Hard outer
cap via the `timeout` command at launch; this script itself only
observes and prints.
"""
import asyncio
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import aiohttp
import yaml

from battlebot.review import service
from battlebot.review.providers import mediawiki
from battlebot.review.auto_repair import parse_source_content


async def main():
    prof = yaml.load(
        open("/app/profiles/needs_review/mixed/adult-cartoons/spongebob-squarepants.yaml"),
        Loader=yaml.CSafeLoader,
    ) or {}
    sources = [s for s in prof.get("sources") or [] if isinstance(s, dict)]
    print("sources:", len(sources), flush=True)
    source = sources[0]
    print("first source:", source.get("url"), "| parser:", source.get("parser"), flush=True)
    api_url = mediawiki.resolve_mediawiki_api_url(str(source.get("url") or ""))
    print("api_url:", api_url, flush=True)
    title = mediawiki.title_from_wiki_url(str(source.get("url") or "")) or source.get("title")
    print("title:", title, flush=True)
    timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_connect=3, sock_read=6)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        t0 = time.monotonic()
        titles = await mediawiki.search_titles(session, api_url, str(title))
        print(f"search_titles wall={time.monotonic()-t0:.1f}s n={len(titles)} titles={titles[:12]}", flush=True)
        for cand in titles[:8]:
            t0 = time.monotonic()
            try:
                fields, meta = await mediawiki.fetch_title_fields(
                    session, api_url, cand, source, parse_source_content
                )
                print(f"candidate {cand!r} wall={time.monotonic()-t0:.1f}s "
                      f"status={meta.get('fetch_status')} fields={len(fields)} "
                      f"content_len={meta.get('content_length')} note={meta.get('note')}",
                      flush=True)
            except Exception as exc:
                print(f"candidate {cand!r} wall={time.monotonic()-t0:.1f}s ERROR {type(exc).__name__}: {exc}", flush=True)


asyncio.run(main())
print("PROBE-DONE", flush=True)
