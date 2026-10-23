#!/usr/bin/env python3
"""End-to-end test: extract fields from Supergirl (Post-Crisis) with new parser."""
import sys
sys.path.insert(0, '/app/src')
import json
import glob

from battlebot.harvest.auto_profile_harvester import (
    extract_vsbattles_fields,
    _HAS_MWPARSE,
)

print(f"mwparserfromhell: {_HAS_MWPARSE}")

# Find Supergirl Post-Crisis cache
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
print(f"Raw wikitext: {len(content)} chars")

fields = extract_vsbattles_fields(content)

print(f"\n=== Extracted {len(fields)} fields ===")
for k in sorted(fields.keys()):
    v = fields[k]
    has_markup = '{{' in v or '#tag:' in v
    print(f"  {k}: {len(v)} chars, markup_leak={has_markup}")

# Specifically check powers_and_abilities
pab = fields.get('powers_and_abilities', '')
print(f"\n=== powers_and_abilities ===")
print(f"Length: {len(pab)}")
print(f"Has tabber markup: {'#tag:tabber' in pab}")
print(f"Has template braces: {'{{' in pab}")
print(f"Preview: {pab[:400]}")
