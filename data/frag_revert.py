#!/usr/bin/env python3
"""Fragment-gate FAIL reverts (sample 50e): remove exactly the debris
items the merges added, per profile, wherever the profile now lives.
Also removes the reverted profiles' recovery progress keys so a future
fixed run reprocesses them. Prints a per-action verification."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

# (profile rel path, section, item-name prefixes to remove)
REMOVE = {
    "profiles/needs_review/comic/dc/etrigan-dc-comics.yaml": [
        ("weaknesses", "particular high frequencies and Order and Chaos. Notes:"),
        ("weaknesses", "please read and follow the Power-scaling Rules"),
    ],
    "profiles/needs_review/comic/dc/gorilla-grodd-dc-comics.yaml": [
        ("weaknesses", "Deviantart"),
        ("weaknesses", "Grodd is prone to blind savage rage"),
    ],
    "profiles/needs_review/comic/dc/gorilla-grodd.yaml": [
        ("weaknesses", "Deviantart"),
        ("weaknesses", "Grodd is prone to blind savage rage"),
    ],
    "profiles/needs_review/comic/dc/deathstroke-rebirth.yaml": [
        ("weaknesses", "Often lashes out in rage Note:"),
    ],
    "profiles/needs_review/comic/dc/doctor-fate-rebirth.yaml": [
        ("weaknesses", "The True Fate:"),
        ("weaknesses", "a woman and a god"),
        ("weaknesses", "specifically Kent"),
        ("weaknesses", "Inza (Kent's wife) and Nabu."),
    ],
}


def locate(rel: str) -> list[Path]:
    found = []
    path = Path(rel)
    if path.exists():
        found.append(path)
    gen = Path(rel.replace("profiles/needs_review/", "profiles/generated/"))
    if gen.exists():
        found.append(gen)
    return found


actions = []
for rel, removals in REMOVE.items():
    for path in locate(rel):
        profile = yaml_io.load_yaml(path)
        for section, name_prefix in removals:
            items = profile.get(section)
            is_dict = isinstance(items, dict)
            seq = list(items.values()) if is_dict else list(items or [])
            hit = [i for i in seq if isinstance(i, dict)
                   and str(i.get("name") or "").startswith(name_prefix)]
            if not hit:
                actions.append(f"MISS {path} [{section}] no item named {name_prefix!r}")
                continue
            hit_ids = {str(i.get("id")) for i in hit}
            if is_dict:
                for k in [k for k, v in items.items()
                          if isinstance(v, dict) and str(v.get("id")) in hit_ids]:
                    del items[k]
            else:
                profile[section] = [i for i in seq
                                    if not (isinstance(i, dict)
                                            and str(i.get("id")) in hit_ids)]
            actions.append(
                f"REMOVED x{len(hit)} {path} [{section}] name-prefix {name_prefix!r}")
        yaml_io.write_yaml(path, profile)

progress_path = Path("/app/data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
for rel in REMOVE:
    if rel in progress:
        del progress[rel]
        actions.append(f"PROGRESS KEY REMOVED {rel}")
    else:
        actions.append(f"PROGRESS KEY ABSENT {rel}")
tmp = progress_path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(progress, indent=1, sort_keys=True))
tmp.replace(progress_path)

for a in actions:
    print(a)
