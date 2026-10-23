#!/usr/bin/env python3
"""Patch flush_multiline_field to use unpack_mediawiki_templates."""

PATCH_FILE = "/opt/referee/src/battlebot/harvest/auto_profile_harvester.py"

with open(PATCH_FILE) as f:
    content = f.read()

old = '''def flush_multiline_field(
    fields: dict[str, str],
    current_key: str | None,
    current_value: list[str],
) -> None:
    if not current_key:
        return
    value = normalize_text(strip_markup("\\n".join(current_value)))
    if value:
        fields[current_key] = value'''

new = '''def flush_multiline_field(
    fields: dict[str, str],
    current_key: str | None,
    current_value: list[str],
) -> None:
    if not current_key:
        return
    raw = "\\n".join(current_value)
    # Expand tabber and other templates with mwparserfromhell before stripping
    raw = unpack_mediawiki_templates(raw)
    value = normalize_text(strip_markup(raw))
    if value:
        fields[current_key] = value'''

if old in content:
    content = content.replace(old, new, 1)
    print("Patched flush_multiline_field")
else:
    print("Pattern not found!")

with open(PATCH_FILE, "w") as f:
    f.write(content)
