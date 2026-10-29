#!/usr/bin/env python3
"""Frag-7 root-cause probe: trace the weaknesses VALUE stage by stage
for the-immortal's recorded sources, exactly as recover_profile_evidence
fetches them (first pass -> fallback chain), plus the raw wikitext
around the Weaknesses / Notable Attacks lines."""
import asyncio
import json
import re
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.review import auto_repair as ar
from battlebot.review.providers import mediawiki
from battlebot.harvest.fallback_parsers import run_parse_fallback_chain

TARGETS = [
    "/app/profiles/needs_review/comic/image-comics/the-immortal.yaml",
    "/app/profiles/needs_review/comic/image-comics/the-immortal-image-comics.yaml",
]


async def probe(path: str) -> None:
    prof = yaml.load(open(path), Loader=yaml.CSafeLoader) or {}
    print(f"##### PROFILE {path}")
    for source in prof.get("sources") or []:
        url = str(source.get("url") or "")
        if not mediawiki.resolve_mediawiki_api_url(url):
            continue
        try:
            fields0, meta = await mediawiki.fetch_mediawiki_fields(
                source, ar.parse_source_content
            )
        except Exception as exc:  # noqa: BLE001
            print(f"=== SRC {source.get('id')}: FETCH ERR {type(exc).__name__}: {exc}")
            continue
        print(f"=== SRC {source.get('id')} title={meta.get('title')!r} "
              f"status={meta.get('fetch_status')}")
        print("  FIRST-PASS weaknesses:",
              json.dumps(fields0.get("weaknesses"), ensure_ascii=False)[:900])
        print("  FIRST-PASS powers:",
              json.dumps(fields0.get("powers_and_abilities"), ensure_ascii=False)[:300])
        wt = str(meta.get("raw_content") or "")
        print(f"  wikitext_len={len(wt)}")
        for marker in ("Weakness", "Notable Attacks"):
            for m in re.finditer(re.escape(marker), wt):
                seg = wt[max(0, m.start() - 60): m.start() + 260].replace("\n", " | ")
                print(f"  RAW[{marker}]: ...{seg}...")
                break
        chain = await run_parse_fallback_chain(
            wikitext=wt,
            title=str(meta.get("title") or ""),
            first_pass_fields=fields0,
            fetch_rendered_html=None,
        )
        fields = chain.get("fields") or {}
        print("  parser_used:", chain.get("parser_used"))
        print("  CHAIN weaknesses:",
              json.dumps(fields.get("weaknesses"), ensure_ascii=False)[:1200])
        kept, dropped, stripped = ar.filter_list_field_items_detailed(
            fields.get("weaknesses") or "", section="weaknesses"
        )
        print("  FILTER kept:", json.dumps(kept, ensure_ascii=False)[:600])
        print("  FILTER dropped:", json.dumps(dropped, ensure_ascii=False)[:900])


async def main() -> int:
    for path in TARGETS:
        await probe(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
