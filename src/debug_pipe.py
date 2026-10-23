#!/usr/bin/env python3
"""Debug extract_template_pipe_fields on Supergirl."""
import sys
sys.path.insert(0, '/app/src')
import json, glob, re

from battlebot.harvest.auto_profile_harvester import (
    extract_template_pipe_fields,
    field_alias,
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

# Find the Powers line
for i, line in enumerate(content.splitlines()):
    if 'powers' in line.lower() and 'abilities' in line.lower() and line.strip().startswith('|'):
        print(f"Line {i}: {line[:100]}")
        # Show next 5 lines
        for j in range(1, 6):
            nl = content.splitlines()[i+j] if i+j < len(content.splitlines()) else ""
            print(f"  +{j}: {nl[:80]}")
        break

print("\n=== extract_template_pipe_fields result ===")
fields = extract_template_pipe_fields(content)
pab = fields.get('powers_and_abilities', '')
print(f"Length: {len(pab)}")
print(f"Preview: {pab[:200]}")
