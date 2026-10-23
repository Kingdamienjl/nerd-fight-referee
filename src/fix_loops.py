#!/usr/bin/env python3
path = '/opt/referee/src/battlebot/harvest/auto_profile_harvester.py'
with open(path) as f:
    content = f.read()

# Fix both template loops to use list() and try/except
old1 = """            # Replace {{!}} (pipe template) with actual pipe
            for tmpl in code.filter_templates():
                if str(tmpl.name).strip() == "!":
                    code.replace(tmpl, "|")"""

new1 = """            # Replace {{!}} (pipe template) with actual pipe
            for tmpl in list(code.filter_templates()):
                if str(tmpl.name).strip() == "!":
                    try:
                        code.replace(tmpl, "|")
                    except ValueError:
                        pass"""

old2 = """            # Remove all remaining templates
            for tmpl in code.filter_templates():
                code.replace(tmpl, "")"""

new2 = """            # Remove all remaining templates
            for tmpl in list(code.filter_templates()):
                try:
                    code.replace(tmpl, "")
                except ValueError:
                    pass"""

if old1 in content:
    content = content.replace(old1, new1, 1)
    print("Patched loop 1")
else:
    print("Loop 1 not found")

if old2 in content:
    content = content.replace(old2, new2, 1)
    print("Patched loop 2")
else:
    print("Loop 2 not found")

with open(path, 'w') as f:
    f.write(content)
