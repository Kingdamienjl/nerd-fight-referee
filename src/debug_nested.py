#!/usr/bin/env python3
"""Debug nested tabber parsing."""
import sys
sys.path.insert(0, '/app/src')
import mwparserfromhell

# Simplified nested structure
test = """'''Powers and Abilities:'''
<tabber>
|-|Kryptonian Physiology=
{{#tag:tabber|Shown Powers='''[[Flight]]''', '''[[Strength]]'''}}
</tabber>"""

code = mwparserfromhell.parse(test)
print("=== Tags ===")
for tag in code.filter_tags():
    print(f"  <{tag.tag}> contents len: {len(str(tag.contents))}")

print("\n=== Templates (top-level) ===")
for tmpl in code.filter_templates(recursive=False):
    print(f"  {{{{{tmpl.name}}}}}")

print("\n=== Templates (recursive) ===")
for tmpl in code.filter_templates(recursive=True):
    print(f"  {{{{{tmpl.name}}}}}")
