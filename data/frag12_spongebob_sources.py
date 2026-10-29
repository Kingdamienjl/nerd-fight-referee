"""SpongeBob per-source probe (read-only): time fetch_mediawiki_fields
for EACH of the profile's 6 recorded sources, with a 90s per-source
asyncio.wait_for cap so a stalled source is reported, not hung.
This finds which source/host stalls the recovery run.
"""
import asyncio
import sys
import time

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar
from battlebot.review.providers import mediawiki


async def timed_source(source, cap=90.0):
    t0 = time.monotonic()
    try:
        fields, meta = await asyncio.wait_for(
            mediawiki.fetch_mediawiki_fields(source, ar.parse_source_content),
            timeout=cap,
        )
        print(f"url={source.get('url')} wall={time.monotonic()-t0:.1f}s "
              f"status={meta.get('fetch_status')} fields={len(fields)} "
              f"note={meta.get('note')}", flush=True)
    except asyncio.TimeoutError:
        print(f"url={source.get('url')} wall={time.monotonic()-t0:.1f}s TIMEOUT>{cap}s",
              flush=True)
    except Exception as exc:
        print(f"url={source.get('url')} wall={time.monotonic()-t0:.1f}s "
              f"ERROR {type(exc).__name__}: {exc}", flush=True)


async def main():
    prof = yaml.load(
        open("/app/profiles/needs_review/mixed/adult-cartoons/spongebob-squarepants.yaml"),
        Loader=yaml.CSafeLoader,
    ) or {}
    sources = [s for s in prof.get("sources") or [] if isinstance(s, dict)]
    for source in sources:
        await timed_source(source)
    print("PER-SOURCE-DONE", flush=True)


asyncio.run(main())
