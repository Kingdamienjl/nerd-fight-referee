#!/usr/bin/env python3
"""Frag-6 gate forensics #2: rex tier verbatim (again, alone) and the
raw Weaknesses section of the vsbattles Immortal page + the raw Tier
line of the Rex Splode page."""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

actual = json.loads(Path("/app/data/recovery_sample50j_actual.json").read_text())
rex = actual["profiles/needs_review/comic/image-comics/rex-splode.yaml"]
print("REX TIER FULL:", json.dumps((rex.get("power_scale") or {}).get("tier"),
                                  ensure_ascii=False))


def wikitext(title: str) -> str:
    url = ("https://vsbattles.fandom.com/api.php?action=parse&prop=wikitext"
           f"&format=json&page={urllib.request.quote(title)}")
    req = urllib.request.Request(url, headers={"User-Agent": "referee-forensics/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return ((body.get("parse") or {}).get("wikitext") or {}).get("*") or ""


for title, marker in (("The Immortal (Image Comics)", "Weakness"),
                      ("Rex Splode (Image Comics)", "Tier")):
    try:
        text = wikitext(title)
    except Exception as exc:  # noqa: BLE001
        print(f"== {title}: FETCH FAILED {type(exc).__name__}: {exc}")
        continue
    print(f"== {title} ({len(text)} chars)")
    for m in re.finditer(rf"\|\s*{marker}[^\n]*", text):
        print("  LINE:", m.group(0)[:600])
    idx = text.lower().find("==weaknesses==")
    if idx >= 0:
        print("  SECTION:", text[idx:idx + 900].replace("\n", " ")[:900])
