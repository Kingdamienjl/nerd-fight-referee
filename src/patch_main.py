#!/usr/bin/env python3
"""Patch extract_vsbattles_fields to expand templates first."""

PATCH_FILE = "/opt/referee/src/battlebot/harvest/auto_profile_harvester.py"

with open(PATCH_FILE) as f:
    content = f.read()

old = '''def extract_vsbattles_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    fields.update(extract_template_pipe_fields(content))
    light_text = light_markup_to_text(content)'''

new = '''def extract_vsbattles_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    fields.update(extract_template_pipe_fields(content))
    # Expand tabber/templates with mwparserfromhell before text extraction
    # This prevents {{#tag:tabber}} markup from leaking into field values
    expanded = unpack_mediawiki_templates(content)
    light_text = light_markup_to_text(expanded)'''

if old in content:
    content = content.replace(old, new, 1)
    print("Patched extract_vsbattles_fields")
else:
    print("Pattern not found!")

with open(PATCH_FILE, "w") as f:
    f.write(content)
