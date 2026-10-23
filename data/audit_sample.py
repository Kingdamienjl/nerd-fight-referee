import json
import sys
from pathlib import Path

sys.path.insert(0, "/app/src")
sys.path.insert(0, "/app")
import yaml

progress = json.loads(Path("data/recovery_progress.json").read_text())
sample = json.loads(Path("data/recovery_sample50_expected.json").read_text())
BOILER = [
    "in bold",
    "add any explanations",
    "using brackets",
    "{{",
    "[[category",
    "the character's attack power",
    "current tier of the character",
]
stats = {"processed": 0, "recovered": 0, "promoted": 0, "merges": 0, "rejections": 0}
flags = []
reason_counts = {}
for rel in sample:
    entry = progress.get(rel)
    if entry is None:
        flags.append(f"MISSING progress entry: {rel}")
        continue
    stats["processed"] += 1
    stats["rejections"] += len(entry.get("guard_rejections") or [])
    if entry.get("recovered_fields"):
        stats["recovered"] += 1
    if entry.get("promoted"):
        stats["promoted"] += 1
    for rej in entry.get("guard_rejections") or []:
        key = ",".join(rej.get("reasons") or [])
        reason_counts[key] = reason_counts.get(key, 0) + 1
    merges = entry.get("merges") or []
    stats["merges"] += len(merges)
    if entry.get("error"):
        flags.append(f"ERROR {rel}: {entry['error']}")
    if not merges:
        continue
    path = Path(rel)
    prof = yaml.load(open(path), Loader=yaml.CSafeLoader) if path.exists() else {}
    print("=" * 100)
    print(
        "PROFILE", rel, "| name:", prof.get("name"), "| franchise:",
        prof.get("franchise"), "| promoted:", entry.get("promoted"),
        "| recovered:", entry.get("recovered_fields"),
    )
    for merge in merges:
        print(
            f"  MERGE page={merge.get('fetched_title')!r} via={merge.get('via')} "
            f"channels={merge.get('franchise_channels')} rev={merge.get('revision_id')} "
            f"url={merge.get('fetched_url')}"
        )
        print(f"        fields={merge.get('recovered_fields')}")
    power = prof.get("power_scale") or {}
    for axis in ("attack_potency", "speed", "durability", "tier"):
        axis_entry = power.get(axis) or {}
        text = str(axis_entry.get("text") or "")
        if text:
            hit = [b for b in BOILER if b in text.casefold()]
            print(f"  {axis}: {text[:150]!r}" + (f"  <<< BOILERPLATE {hit}" if hit else ""))
            if hit:
                flags.append(f"BOILERPLATE in {rel} {axis}: {hit}")
    abilities = prof.get("abilities") or []
    names = [
        str(a.get("name") if isinstance(a, dict) else a)[:60] for a in abilities[:6]
    ]
    print("  abilities[0:6]:", names, "| total:", len(abilities))

print("=" * 100)
print("SAMPLE STATS:", json.dumps(stats))
print("REJECTION REASON COUNTS:", json.dumps(reason_counts, indent=1))
print("FLAGS:", flags if flags else "none")
