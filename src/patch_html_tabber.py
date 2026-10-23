#!/usr/bin/env python3
"""Add <tabber> HTML tag handling to _expand_tabber_mwparse."""

PATCH_FILE = "/opt/referee/src/battlebot/harvest/auto_profile_harvester.py"

with open(PATCH_FILE) as f:
    content = f.read()

old = '''def _expand_tabber_mwparse(code) -> str:
    """Expand {{#tag:tabber}} blocks into concatenated tab contents using mwparserfromhell."""
    import re as _re
    for tmpl in code.filter_templates():'''

new = '''def _expand_tabber_mwparse(code) -> str:
    """Expand {{#tag:tabber}} and <tabber> blocks into concatenated tab contents using mwparserfromhell."""
    import re as _re
    # Handle <tabber> HTML tags first
    for tag in code.filter_tags():
        if tag.tag.lower() == "tabber":
            tab_content = str(tag.contents)
            # Tabber tabs are separated by |-|
            tab_content = _re.sub(r"\\|\\-\\|", "\\n", tab_content)
            # Strip tab name headers
            lines = []
            for line in tab_content.split("\\n"):
                header_match = _re.match(r"^\\s*[A-Za-z][A-Za-z0-9 /&\\-]*\\s*=\\s*$", line)
                if header_match:
                    continue
                inline_match = _re.match(r"^\\s*[A-Za-z][A-Za-z0-9 /&\\-]*\\s*=\\s*(.+)$", line)
                if inline_match:
                    line = inline_match.group(1)
                lines.append(line)
            code.replace(tag, "\\n".join(lines))
    for tmpl in code.filter_templates():'''

if old in content:
    content = content.replace(old, new, 1)
    print("Added <tabber> tag handling")
else:
    print("Pattern not found!")

with open(PATCH_FILE, "w") as f:
    f.write(content)
