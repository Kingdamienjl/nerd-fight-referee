#!/usr/bin/env python3
"""Frag-10 tier root-cause probe (live fetch, read-only).

For Arcee (Transformers) — one of the 5 gate-50m rating-stripped
tiers — reproduce the tier value layer by layer:
  1. raw wikitext lines mentioning 'tier'
  2. extract_vsbattles_fields(wikitext)['tier']
  3. parse_source_content(wikitext)['tier'] (recovery first pass)
  4. run_parse_fallback_chain tier + parser_used (with rendered HTML)
  5. extract_from_rendered_html tier
The gate-50m merged value was 'likely higher. with swords'; the
source page states 'Low 5-B, likely higher. High 5-A with swords'.
"""
import asyncio
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import aiohttp

from battlebot.harvest import auto_profile_harvester as aph
from battlebot.harvest import fallback_parsers as fp
from battlebot.review import auto_repair as ar
from battlebot.review.providers import mediawiki as mw

API = "https://vsbattles.fandom.com/api.php"
TITLE = "Arcee (Transformers)"


async def main() -> int:
    timeout = aiohttp.ClientTimeout(total=30, connect=5, sock_connect=5, sock_read=15)
    async with aiohttp.ClientSession(
        timeout=timeout, headers={"User-Agent": "battlebot-review-repair/0.1"}
    ) as session:
        fields, meta = await mw.fetch_title_fields(
            session, API, TITLE,
            {"url": "https://vsbattles.fandom.com/wiki/Arcee_%28Transformers%29",
             "title": TITLE},
            ar.parse_source_content,
        )
        print("first_pass_tier=", repr(fields.get("tier")))
        print("first_pass_core=", {k: fields.get(k) for k in ("attack_potency", "speed", "durability") if fields.get(k)})
        print("fetch_status=", meta.get("fetch_status"), "note=", meta.get("note"))
        wikitext = str(meta.get("raw_content") or "")
        print("wikitext_len=", len(wikitext))
        for line in wikitext.splitlines():
            if "tier" in line.casefold():
                print("WIKITEXT TIER LINE:", line[:300])
        vfields = aph.extract_vsbattles_fields(wikitext)
        print("extract_vsbattles_fields tier=", repr(vfields.get("tier")))

        async def _fetch_rendered_html() -> str:
            params = {
                "action": "parse", "page": TITLE, "prop": "text",
                "format": "json", "formatversion": "2",
            }
            async with session.get(API, params=params) as response:
                body = await response.json(content_type=None)
            parse = (body or {}).get("parse") or {}
            text = parse.get("text")
            if isinstance(text, dict):
                return str(text.get("*") or "")
            return str(text or "")

        chain = await fp.run_parse_fallback_chain(
            wikitext=wikitext, title=TITLE,
            first_pass_fields=dict(fields),
            fetch_rendered_html=_fetch_rendered_html,
        )
        print("chain_tier=", repr((chain.get("fields") or {}).get("tier")))
        print("chain_parser_used=", chain.get("parser_used"))
        html = await _fetch_rendered_html()
        print("rendered_html_len=", len(html))
        hfields = fp.extract_from_rendered_html(html)
        print("rendered_html_tier=", repr(hfields.get("tier")))
        # Where in the rendered HTML does the tier live?
        import re
        for m in re.finditer(r"(?i)tier.{0,200}", aph.strip_markup(html)[:0] or ""):
            pass
        text = aph.strip_markup(html)
        idx = text.casefold().find("tier")
        print("rendered_text tier context:", repr(text[max(0, idx - 40):idx + 200]) if idx >= 0 else "not found")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
