#!/usr/bin/env python3
"""Find the exception in unpack_mediawiki_templates."""
import sys
sys.path.insert(0, '/app/src')
import json, glob
import mwparserfromhell
import traceback

# Import the internal function
from battlebot.harvest import auto_profile_harvester as aph

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

print("Testing _expand_tabber_mwparse...")
try:
    code = mwparserfromhell.parse(content)
    result = aph._expand_tabber_mwparse(code)
    print(f"Success: {len(result)} chars")
except Exception:
    traceback.print_exc()
