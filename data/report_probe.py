import json
from collections import Counter
from pathlib import Path

r = json.loads(Path("/opt/referee/data/continuity_sweep_report_dry.json").read_text())
print("keys:", {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()})
pairs = Counter((x["scope"], x["page_continuity"]) for x in r["suspect"])
print("suspect scope->page pairs:", pairs.most_common(12))
print("suspect resolved split:", Counter(x["resolved"] for x in r["suspect"]))
fams = Counter(x["profile"].split("/")[1] if "/" in x["profile"] else "?"
               for x in r["suspect"])
print("suspect by family:", fams.most_common(8))
print("fixed examples:")
for x in r["fixed"][:5]:
    print("  ", x["profile"], "|", x["title"], "->", x.get("new_title"))
print("suspect examples:")
for x in r["suspect"][:5]:
    print("  ", x["profile"], "|", x["title"], "| scope", x["scope"],
          "| page", x["page_continuity"], "| resolved", x["resolved"])
stamped = r["stamped_profiles"]
print("stamped total:", len(stamped),
      "battle_eligible:", sum(1 for s in stamped if s["battle_eligible"]))
for s in stamped:
    if s["battle_eligible"]:
        print("   ELIGIBLE:", s["profile"], s["status"], s["tainted_source_ids"])
