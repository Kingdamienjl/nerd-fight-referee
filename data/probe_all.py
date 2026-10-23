import sys
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.harvest.auto_profile_harvester import (
    read_roster_csv, profile_output_path, character_row_id, row_fingerprint,
    load_json_state, get_roster_state,
)

state = load_json_state(Path("data/harvest_state.json"))
gen = Path("profiles/generated"); nr = Path("profiles/needs_review")
tot_unmatched = 0
for inp in sorted(Path("profiles/rosters").glob("*.csv")):
    rows = read_roster_csv(inp)
    _k, rs = get_roster_state(state, input_path=inp, roster_id=None)
    c = {"gen": 0, "nr": 0, "state": 0, "none": 0}
    for row in rows:
        rid = character_row_id(row); fp = row_fingerprint(row)
        if profile_output_path(gen, row).exists():
            c["gen"] += 1
        elif profile_output_path(nr, row).exists():
            c["nr"] += 1
        elif rs.get("completed", {}).get(rid) == fp or rs.get("needs_review", {}).get(rid) == fp:
            c["state"] += 1
        else:
            c["none"] += 1
    tot_unmatched += c["none"]
    flag = "  <-- UNMATCHED" if c["none"] else ""
    print(f"{inp.name}: rows={len(rows)} cursor={rs.get('cursor_index')} gen={c['gen']} nr={c['nr']} state_only={c['state']} unmatched={c['none']}{flag}")
print("TOTAL unmatched rows across all rosters:", tot_unmatched)
