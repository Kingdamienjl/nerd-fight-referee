import json
from pathlib import Path

import yaml

progress = json.loads(Path("data/recovery_progress.json").read_text())
sample = json.loads(Path("data/recovery_sample50_expected.json").read_text())
PRE = Path("/tmp/presample_extract")

for rel in sample:
    entry = progress.get(rel) or {}
    if not entry.get("merges"):
        continue
    before_path = PRE / rel
    before = (
        yaml.load(open(before_path), Loader=yaml.CSafeLoader)
        if before_path.exists()
        else {}
    )
    after = yaml.load(open(rel), Loader=yaml.CSafeLoader)
    print("=" * 100)
    print("PROFILE", rel, "| promoted:", entry.get("promoted"), "| recovered:", entry.get("recovered_fields"))
    recovered = set(entry.get("recovered_fields") or [])
    for axis in ("tier", "attack_potency", "speed", "durability", "range", "stamina", "intelligence"):
        if axis not in recovered:
            continue
        b = str(((before.get("power_scale") or {}).get(axis) or {}).get("text") or "")
        a = str(((after.get("power_scale") or {}).get(axis) or {}).get("text") or "")
        mark = "CHANGED" if a != b else "same   "
        print(f"  [{mark}] {axis}:")
        if a != b:
            print(f"      before: {b[:130]!r}")
            print(f"      after : {a[:130]!r}")
    if "abilities" in recovered:
        b_names = [
            str(x.get("name") if isinstance(x, dict) else x)[:50]
            for x in before.get("abilities") or []
        ]
        a_names = [
            str(x.get("name") if isinstance(x, dict) else x)[:50]
            for x in after.get("abilities") or []
        ]
        print(f"  [CHANGED] abilities: before={len(b_names)} {b_names[:3]}")
        print(f"                      after ={len(a_names)} {a_names[:4]}")
    if "weaknesses" in recovered:
        b_w = [str(x)[:60] for x in before.get("weaknesses") or []]
        a_w = [str(x.get("name") if isinstance(x, dict) else x)[:60] for x in after.get("weaknesses") or []]
        print(f"  weaknesses: before={len(b_w)} after={len(a_w)} after[0:2]={a_w[:2]}")
