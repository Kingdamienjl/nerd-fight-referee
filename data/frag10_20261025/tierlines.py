import json, sys
d = json.load(open("/tmp/p.json"))
p = (d.get("query") or {}).get("pages", [{}])[0]
rev = (p.get("revisions") or [{}])[0]
content = str(rev.get("slots", {}).get("main", {}).get("content", ""))
print("==", p.get("title"), "len=", len(content))
for line in content.splitlines():
    if "tier" in line.casefold():
        print("  TIER LINE:", line[:400])
