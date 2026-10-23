#!/usr/bin/env python3
"""Fix: re-parse after tag replacement."""

PATCH_FILE = "/opt/referee/src/battlebot/harvest/auto_profile_harvester.py"

with open(PATCH_FILE) as f:
    content = f.read()

old = '''            code.replace(tag, "\\n".join(lines))
    for tmpl in code.filter_templates():'''

new = '''            code.replace(tag, "\\n".join(lines))
    # Re-parse to catch nested {{#tag:tabber}} that were inside <tabber> tags
    code = mwparserfromhell.parse(str(code))
    for tmpl in code.filter_templates():'''

if old in content:
    content = content.replace(old, new, 1)
    print("Added re-parse after tag replacement")
else:
    print("Pattern not found!")

with open(PATCH_FILE, "w") as f:
    f.write(content)
