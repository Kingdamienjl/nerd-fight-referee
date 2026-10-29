"""Frag-11 live reproduction probe (read-only fetches).
For one profile (argv[1] = file name under profiles/), fetch each recorded
mediawiki source the way recover_profile_evidence does (fetch_mediawiki_fields
+ run_parse_fallback_chain) and print the raw fields relevant to the frag-11
verbatim failures, plus the list-split pieces around them.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import aiohttp
import yaml

from battlebot.harvest import auto_profile_harvester as aph
from battlebot.harvest import fallback_parsers as fp
from battlebot.review import auto_repair as ar
from battlebot.review.providers import mediawiki as mw

NAME = sys.argv[1]

def find(name):
    for cand in (Path("/app/profiles/needs_review").rglob(name),
                 Path("/app/profiles").rglob(name)):
        hits = sorted(cand)
        if hits:
            return hits[0]
    return None

async def main():
    src = find(NAME)
    prof = yaml.safe_load(src.open()) or {}
    print("PROFILE:", src, "name:", prof.get("name"))
    timeout = aiohttp.ClientTimeout(total=30, connect=5, sock_connect=5, sock_read=15)
    async with aiohttp.ClientSession(
        timeout=timeout, headers={"User-Agent": "battlebot-evidence-recovery/0.1"}
    ) as session:
        for source in prof.get("sources") or []:
            url = str(source.get("url") or "")
            api = mw.resolve_mediawiki_api_url(url)
            if not api:
                continue
            title = str(source.get("title") or "")
            print("=" * 30, "SOURCE:", title, url)
            try:
                fields0, meta = await mw.fetch_mediawiki_fields(
                    source, ar.parse_source_content
                )
            except Exception as exc:
                print("  FETCH ERROR:", type(exc).__name__, exc)
                continue
            print("  fetch_status:", meta.get("fetch_status"), "note:", meta.get("note"),
                  "rev:", meta.get("revision_id"), meta.get("revision_timestamp"))
            print("  first_pass fields:", sorted(fields0.keys()))
            for k in ("speed", "range", "intelligence", "tier"):
                if fields0.get(k):
                    print(f"  FP[{k}]: {fields0[k]!r}")
            wikitext = str(meta.get("raw_content") or "")
            print("  wikitext_len:", len(wikitext))
            # verbatim needles in wikitext
            for needle in ("Deadly Absorp", "Absorption", "Battle ID Types",
                           "Dark Lord abilities", "Lifting Strength",
                           "Radagon", "but after the Night", "he was limited",
                           "Durability Negation", "Frost Damage"):
                idx = wikitext.find(needle)
                if idx >= 0:
                    print(f"  WIKITEXT[{needle}]: ...{wikitext[max(0,idx-160):idx+220]!r}...")
            # fallback chain
            try:
                async def _fetch_rendered_html():
                    params = {"action": "parse", "page": title, "prop": "text",
                              "format": "json", "formatversion": "2"}
                    async with session.get(api, params=params) as resp:
                        body = await resp.json(content_type=None)
                    parse = (body or {}).get("parse") or {}
                    text = parse.get("text")
                    return str(text.get("*") or "") if isinstance(text, dict) else str(text or "")
                chain = await fp.run_parse_fallback_chain(
                    wikitext=wikitext, title=title, first_pass_fields=fields0,
                    fetch_rendered_html=_fetch_rendered_html)
                print("  chain parser_used:", chain.get("parser_used"))
                cfields = chain.get("fields") or {}
                for k in ("speed", "range", "intelligence", "tier",
                          "powers_and_abilities", "weaknesses"):
                    if cfields.get(k):
                        print(f"  CHAIN[{k}]: {str(cfields[k])[:600]!r}")
                        # pieces around needles
                        from battlebot.harvest.auto_profile_harvester import split_listish, unpack_mediawiki_templates
                        if k in ("powers_and_abilities", "weaknesses"):
                            pieces = split_listish(unpack_mediawiki_templates(str(cfields[k])))
                            for p in pieces:
                                if any(n in p for n in ("Absorp", "ID Types", "Dark Lord abilities",
                                                       "Creatures of Chaos", "Radagon", "but after",
                                                       "he was limited", "Durability Negation",
                                                       "Forcefield Creation (Via Protective")):
                                    print(f"    PIECE: {p!r}")
            except Exception as exc:
                print("  CHAIN ERROR:", type(exc).__name__, exc)

asyncio.run(main())
