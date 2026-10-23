#!/usr/bin/env python3
"""Trace which extractor produces the broken powers_and_abilities."""
import sys
sys.path.insert(0, '/app/src')
import json, glob

from battlebot.harvest.auto_profile_harvester import (
    extract_template_pipe_fields,
    extract_inline_labeled_fields,
    extract_delimiterless_labeled_fields,
    extract_section_fields,
    light_markup_to_text,
    strip_markup,
    unpack_mediawiki_templates,
)

# Find Supergirl Post-Crisis
target = None
for f in glob.glob('/app/data/cache/*.json'):
    try:
        d = json.load(open(f))
        pages = d.get('body', {}).get('query', {}).get('pages', [])
        if pages and pages[0].get('title') == 'Supergirl (Post-Crisis)':
            target = f
            break
    except:
        pass

d = json.load(open(target))
content = d['body']['query']['pages'][0]['revisions'][0]['slots']['main']['content']

print("=== Testing each extractor for powers_and_abilities ===")

# 1. Template pipe fields
f1 = extract_template_pipe_fields(content)
print(f"1. template_pipe: '{f1.get('powers_and_abilities', '')[:80]}'")

# 2. Inline labeled on light text
light = light_markup_to_text(content)
f2 = extract_inline_labeled_fields(light)
print(f"2. inline(light): '{f2.get('powers_and_abilities', '')[:80]}'")

# 3. Section fields
f3 = extract_section_fields(content)
print(f"3. section: '{f3.get('powers_and_abilities', '')[:80]}'")

# 4. Inline on strip_markup text
text = strip_markup(content)
f4 = extract_inline_labeled_fields(text)
print(f"4. inline(strip): '{f4.get('powers_and_abilities', '')[:80]}'")

# 5. Inline on unpacked text
unpacked = unpack_mediawiki_templates(content)
text2 = strip_markup(unpacked)
f5 = extract_inline_labeled_fields(text2)
print(f"5. inline(unpacked+strip): '{f5.get('powers_and_abilities', '')[:80]}'")
