#!/usr/bin/env python3
"""Inspect wikitext structure around Powers and Abilities."""
import json, glob, re

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

# Find Powers and Abilities section
idx = content.lower().find('powers and abilities')
print(f"Found at: {idx}")
if idx >= 0:
    print("Context:")
    print(repr(content[max(0,idx-200):idx+500]))
