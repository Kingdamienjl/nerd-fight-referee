#!/usr/bin/env python3
"""Test _expand_tabber_mwparse directly."""
import sys
sys.path.insert(0, '/app/src')
import json, glob

from battlebot.harvest.auto_profile_harvester import (
    unpack_mediawiki_templates,
    _HAS_MWPARSE,
)

print(f"mwparserfromhell: {_HAS_MWPARSE}")

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

# Find the Powers section
idx = content.find('Powers and Abilities')
section = content[idx:idx+800]
print("=== Original section ===")
print(section[:400])

print("\n=== After unpack_mediawiki_templates ===")
unpacked = unpack_mediawiki_templates(section)
print(unpacked[:500])
print(f"\nStill has #tag: {'#tag:' in unpacked}")
print(f"Still has <tabber>: {'<tabber>' in unpacked}")
