#!/usr/bin/env python3
"""Fix template removal to avoid modification-during-iteration."""

PATCH_FILE = "/opt/referee/src/battlebot/harvest/auto_profile_harvester.py"

with open(PATCH_FILE) as f:
    content = f.read()

old = """            # Re-parse after tabber expansion
            code = mwparserfromhell.parse(text)
            # Replace {{!}} with pipe
            for tmpl in code.filter_templates():
                if str(tmpl.name).strip() == "!":
                    code.replace(tmpl, "|")
            # Remove all remaining templates
            for tmpl in code.filter_templates():
                code.replace(tmpl, "")
            text = str(code)"""

new = """            # Re-parse after tabber expansion
            code = mwparserfromhell.parse(text)
            # Replace {{!}} with pipe (collect first to avoid modification-during-iteration)
            for tmpl in list(code.filter_templates()):
                if str(tmpl.name).strip() == "!":
                    try:
                        code.replace(tmpl, "|")
                    except ValueError:
                        pass
            # Remove all remaining templates (collect first)
            for tmpl in list(code.filter_templates()):
                try:
                    code.replace(tmpl, "")
                except ValueError:
                    pass
            text = str(code)"""

if old in content:
    content = content.replace(old, new, 1)
    print("Fixed template iteration")
else:
    print("Pattern not found!")

with open(PATCH_FILE, "w") as f:
    f.write(content)
