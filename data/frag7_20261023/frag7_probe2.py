#!/usr/bin/env python3
"""Frag-7 probe #2: which sub-extractor inside extract_vsbattles_fields
produces the runaway weaknesses value for The Immortal's page?"""
import asyncio
import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.harvest import auto_profile_harvester as aph
from battlebot.review.providers import mediawiki
from battlebot.review import auto_repair as ar


async def main() -> int:
    prof = yaml.load(
        open("/app/profiles/needs_review/comic/image-comics/the-immortal.yaml"),
        Loader=yaml.CSafeLoader,
    ) or {}
    source = next(s for s in prof["sources"] if s["id"] == "vsbattles-the-immortal")
    fields0, meta = await mediawiki.fetch_mediawiki_fields(
        source, ar.parse_source_content
    )
    wt = str(meta.get("raw_content") or "")
    print("title:", meta.get("title"), "wikitext_len:", len(wt))

    stages = {}
    stages["template_pipe"] = aph.extract_template_pipe_fields(wt)
    expanded = aph.unpack_mediawiki_templates(wt)
    light = aph.light_markup_to_text(expanded)
    stages["inline_light"] = aph.extract_inline_labeled_fields(light)
    stages["delim_light"] = aph.extract_delimiterless_labeled_fields(light)
    text = aph.strip_markup(wt)
    stages["inline_text"] = aph.extract_inline_labeled_fields(text)
    stages["delim_text"] = aph.extract_delimiterless_labeled_fields(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    loop_fields = {}
    for index, line in enumerate(lines):
        parsed = aph.parse_field_line(line)
        if parsed:
            key, value = parsed
            loop_fields.setdefault(key, value)
            continue
        header = aph.normalize_field_name(line)
        canonical = aph.field_alias(header)
        if canonical and index + 1 < len(lines):
            loop_fields.setdefault(canonical, lines[index + 1])
    stages["line_loop"] = loop_fields
    stages["section_fields"] = aph.extract_section_fields(wt)
    for name, fields in stages.items():
        print(f"--- {name}: weaknesses =",
              json.dumps(fields.get("weaknesses"), ensure_ascii=False)[:300])
    print("=== extract_vsbattles_fields weaknesses:",
          json.dumps(aph.extract_vsbattles_fields(wt).get("weaknesses"),
                     ensure_ascii=False)[:300])
    print("=== parse_source_content weaknesses:",
          json.dumps(fields0.get("weaknesses"), ensure_ascii=False)[:300])
    # Where does the runaway value start? Show text right after Weaknesses label.
    idx = text.find("Weaknesses")
    print("=== strip_markup around Weaknesses:", repr(text[idx:idx + 400]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
