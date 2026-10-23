#!/usr/bin/env python3
"""Replay recovery's exact item filter on the etrigan vsbattles page's
weaknesses field text: what would recovery itself have kept?"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair as ar
from battlebot.review.providers import mediawiki

expected = json.loads(Path("/app/data/recovery_sample50e_expected.json").read_text())
prof = expected["profiles/needs_review/comic/dc/etrigan-dc-comics.yaml"]
source = None
for s in prof.get("sources") or []:
    if isinstance(s, dict) and s.get("id") == "vsbattles-etrigan-dc-comics":
        source = s
        break
print("source:", source.get("url") if source else None, "parser:", source.get("parser"))


async def main():
    fields, meta = await mediawiki.fetch_mediawiki_fields(
        source, ar.parse_source_content)
    print("fetch_status:", meta.get("fetch_status"), "title:", meta.get("title"))
    raw = fields.get("weaknesses") or ""
    print("RAW weaknesses text:")
    print(raw[:1500])
    kept, dropped = ar.filter_list_field_items(raw, section="weaknesses")
    print("\nKEPT_TEXT:")
    print(kept[:1500])
    print("\nDROPPED:")
    for d in dropped:
        print(" ", d["reasons"], "::", str(d["item"])[:140])


asyncio.run(main())
