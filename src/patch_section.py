#!/usr/bin/env python3
"""Patch extract_section_fields to expand templates before stripping."""

PATCH_FILE = "/opt/referee/src/battlebot/harvest/auto_profile_harvester.py"

with open(PATCH_FILE) as f:
    content = f.read()

old = '''def extract_section_fields(content: str) -> dict[str, str]:
    text = strip_markup(content)'''

new = '''def extract_section_fields(content: str) -> dict[str, str]:
    # Expand tabber/templates with mwparserfromhell before stripping markup
    text = strip_markup(unpack_mediawiki_templates(content))'''

if old in content:
    content = content.replace(old, new, 1)
    print("Patched extract_section_fields")
else:
    print("Pattern not found!")

with open(PATCH_FILE, "w") as f:
    f.write(content)
