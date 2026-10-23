import sys
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.harvest.auto_profile_harvester import (
    read_roster_csv, profile_output_path, character_row_id, row_fingerprint,
    load_json_state, get_roster_state,
)

for roster_name in ("expansion_20261010_seeds.csv", "expansion_20261015_digimon.csv", "expansion_20261015_powerrangers.csv"):
    inp = Path("profiles/rosters") / roster_name
    rows = read_roster_csv(inp)
    state = load_json_state(Path("data/harvest_state.json"))
    _k, rs = get_roster_state(state, input_path=inp, roster_id=None)
    gen = Path("profiles/generated"); nr = Path("profiles/needs_review")
    counts = {"gen_file": 0, "nr_file": 0, "state_completed": 0, "state_nr": 0, "none": 0}
    nones = []
    for row in rows:
        rid = character_row_id(row); fp = row_fingerprint(row)
        if profile_output_path(gen, row).exists():
            counts["gen_file"] += 1
        elif profile_output_path(nr, row).exists():
            counts["nr_file"] += 1
        elif rs.get("completed", {}).get(rid) == fp:
            counts["state_completed"] += 1
        elif rs.get("needs_review", {}).get(rid) == fp:
            counts["state_nr"] += 1
        else:
            counts["none"] += 1
            nones.append(row.name)
    print(roster_name, "rows:", len(rows), "cursor:", rs.get("cursor_index"), counts)
    if nones:
        print("  unmatched sample:", nones[:8])
