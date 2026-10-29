#!/usr/bin/env python3
"""Frag-6 gate forensics #4: raw wikitext of the vsbattles Immortal
page via the query/revisions API, with errors visible."""
import json
import re
import urllib.parse
import urllib.request

for title in ("The Immortal (Comics)", "Rex Splode (Comics)"):
    url = ("https://vsbattles.fandom.com/api.php?action=query&redirects=1&prop=revisions"
           "&rvprop=content&rvslots=main&format=json&formatversion=2&titles="
           + urllib.parse.quote(title))
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 referee-forensics"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        print(f"== {title}: FETCH FAILED {type(exc).__name__}: {exc}")
        continue
    pages = ((body.get("query") or {}).get("pages") or [])
    text = ""
    for page in pages:
        for rev in page.get("revisions") or []:
            text = ((rev.get("slots") or {}).get("main") or {}).get("content") or ""
    print(f"== {title}: {len(text)} chars")
    if not text:
        print("  RAW:", json.dumps(body)[:300])
        continue
    for m in re.finditer(r"\|\s*(tier|weaknesses)[^\n]*", text, re.I):
        print("  LINE:", m.group(0)[:500])
    idx = text.lower().find("weaknesses")
    while idx >= 0:
        print("  CTX:", text[max(0, idx - 40):idx + 420].replace("\n", " ")[:460])
        idx = text.lower().find("weaknesses", idx + 1)
        break
