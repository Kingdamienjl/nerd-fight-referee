#!/usr/bin/env python3
"""Test _expand_tabber_mwparse on real Supergirl section."""
import sys
sys.path.insert(0, '/app/src')
import json, glob
import mwparserfromhell
from battlebot.harvest.auto_profile_harvester import _expand_tabber_mwparse

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
idx = content.find('Powers and Abilities')
section = content[idx:idx+800]

print(f"Section len: {len(section)}")
code = mwparserfromhell.parse(section)
tags = list(code.filter_tags())
print(f"Tags: {[(t.tag, len(str(t.contents))) for t in tags]}")

try:
    result = _expand_tabber_mwparse(code)
    print(f"Result len: {len(result)}")
    print(f"Has <tabber>: {'<tabber>' in result}")
    print(f"Has #tag: {'#tag:' in result}")
except Exception as e:
    import traceback
    traceback.print_exc()
