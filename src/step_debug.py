#!/usr/bin/env python3
"""Step through unpack_mediawiki_templates."""
import sys
sys.path.insert(0, '/app/src')
import json, glob
import mwparserfromhell
import traceback
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

try:
    print("Step 1: parse")
    code = mwparserfromhell.parse(content)
    print(f"  OK")

    print("Step 2: _expand_tabber_mwparse")
    text = aph._expand_tabber_mwparse(code)
    print(f"  OK: {len(text)} chars")

    print("Step 3: re-parse")
    code = mwparserfromhell.parse(text)
    print(f"  OK")

    print("Step 4: replace {{!}}")
    count = 0
    for tmpl in code.filter_templates():
        if str(tmpl.name).strip() == "!":
            code.replace(tmpl, "|")
            count += 1
    print(f"  OK: replaced {count}")

    print("Step 5: remove templates")
    count = 0
    for tmpl in code.filter_templates():
        code.replace(tmpl, "")
        count += 1
        if count > 10000:
            print("  TOO MANY!")
            break
    print(f"  OK: removed {count}")

    print("Step 6: str(code)")
    text = str(code)
    print(f"  OK: {len(text)} chars")

except Exception:
    traceback.print_exc()
