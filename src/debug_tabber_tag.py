#!/usr/bin/env python3
"""Check tabber tag parsing in full context."""
import sys
sys.path.insert(0, '/app/src')
import json, glob
import mwparserfromhell

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
idx = content.find('<tabber>')
print(f"<tabber> at: {idx}")
if idx >= 0:
    # Get 2000 chars around it
    section = content[max(0,idx-100):idx+2000]
    print(f"Has </tabber>: {'</tabber>' in section}")
    # Find closing
    close_idx = section.find('</tabber>')
    print(f"Close at offset: {close_idx}")
    print(f"Section len to close: {close_idx + 9 if close_idx >= 0 else 'N/A'}")

    code = mwparserfromhell.parse(section)
    tags = [(t.tag, len(str(t.contents))) for t in code.filter_tags()]
    print(f"Tags found: {tags}")
