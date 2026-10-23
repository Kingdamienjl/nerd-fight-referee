#!/usr/bin/env python3
"""Debug _expand_tabber_mwparse."""
import sys
sys.path.insert(0, '/app/src')
import mwparserfromhell
from battlebot.harvest.auto_profile_harvester import _expand_tabber_mwparse

test = """<tabber>
|-|Kryptonian Physiology=
{{#tag:tabber|Shown Powers='''[[Flight]]'''}}
</tabber>"""

print("Input:", repr(test[:100]))
code = mwparserfromhell.parse(test)
print(f"Tags found: {len(list(code.filter_tags()))}")
print(f"Templates found: {len(list(code.filter_templates()))}")

try:
    result = _expand_tabber_mwparse(code)
    print(f"Result len: {len(result)}")
    print(f"Has tabber: {'tabber' in result.lower()}")
    print(f"Result: {result[:200]}")
except Exception as e:
    import traceback
    traceback.print_exc()
