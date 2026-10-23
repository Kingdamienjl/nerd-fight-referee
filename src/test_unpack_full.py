#!/usr/bin/env python3
"""Direct test of unpack_mediawiki_templates on full content."""
import sys
sys.path.insert(0, '/app/src')
import json, glob

from battlebot.harvest.auto_profile_harvester import unpack_mediawiki_templates

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
print(f"Input: {len(content)} chars, has tabber: {'<tabber>' in content}")

result = unpack_mediawiki_templates(content)
print(f"Output: {len(result)} chars")
print(f"Has <tabber>: {'<tabber>' in result}")
print(f"Has #tag:tabber: {'#tag:tabber' in result}")
print(f"Has {{: {'{{' in result}")
