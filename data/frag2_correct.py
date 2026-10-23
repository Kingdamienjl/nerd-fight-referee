#!/usr/bin/env python3
"""Corrective pass over frag2_tailrescan keeps: remove items whose
stripped keep is itself debris (placeholder/key-label residue,
numeric/instruction/calc shards, citation-glued or bundle keeps),
and trim dangling 'Feats:' tails off two otherwise-real clauses.
Targeted by (profile, item id); prints every action."""
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

REMOVE = {
    "profiles/generated/anime/dragon-ball/chi-chi-dragon-ball.yaml":
        "weaknesses-adult-none-notable-note-the-instances-in-which-she-intimidated-and-fr",
    "profiles/generated/anime/dragon-ball/chi-chi.yaml":
        "weaknesses-adult-none-notable-note-the-instances-in-which-she-intimidated-and-fr",
    "profiles/generated/comic/marvel/annihilus-earth-616.yaml":
        "weaknesses-000-b-c-note-this-profile-only-covers-the-616-version-of-doctor-doom-",
    "profiles/generated/comic/marvel/doctor-doom-earth-616.yaml":
        "weaknesses-000-b-c-note-this-profile-only-covers-the-616-version-of-doctor-doom-",
    "profiles/generated/comic/marvel/doctor-doom-marvel-comics.yaml":
        "weaknesses-000-b-c-note-this-profile-only-covers-the-616-version-of-doctor-doom-",
    "profiles/generated/comic/marvel/doctor-doom.yaml":
        "weaknesses-000-b-c-note-this-profile-only-covers-the-616-version-of-doctor-doom-",
    "profiles/generated/recentchanges/unknown/babylon-guardian-sonic-the-hedgehog.yaml":
        "weaknesses-consult-this-page-note-despite-the-guardian-being-able-to-fire-energy",
    "profiles/generated/game/kingdom-hearts/mickey-mouse-game.yaml":
        "weaknesses-calculated-to-be-around-67-2m-note-respect-threads",
    "profiles/generated/anime/berserk/griffith.yaml":
        "weaknesses-losing-control-of-his-corporeal-body-to-the-child-berserk-chapter-364",
    "profiles/generated/anime/one-piece/marshall-d-teach-one-piece.yaml":
        "weaknesses-or-even-in-the-air-the-different-techniques-blackbeard-have-so-far-de",
    "profiles/generated/anime/one-piece/marshall-d-teach.yaml":
        "weaknesses-or-even-in-the-air-the-different-techniques-blackbeard-have-so-far-de",
}
TRIM = {
    "profiles/generated/comic/image-comics/spawn.yaml":
        "weaknesses-his-necromancy-only-lasts-for-a-short-duration-and-is-limited-to-a-20",
    "profiles/generated/mixed/crossover-icons/spawn.yaml":
        "weaknesses-his-necromancy-only-lasts-for-a-short-duration-and-is-limited-to-a-20",
    "profiles/generated/comic/marvel/loki-marvel-comics.yaml":
        "weaknesses-sliced-off-by-balder-in-the-same-storyline-feats-see-this-respect-thr",
    "profiles/generated/comic/marvel/loki.yaml":
        "weaknesses-sliced-off-by-balder-in-the-same-storyline-feats-see-this-respect-thr",
}

actions = []
for rel, id_prefix in REMOVE.items():
    path = Path(rel)
    profile = yaml_io.load_yaml(path)
    items = profile.get("weaknesses")
    is_dict = isinstance(items, dict)
    seq = list(items.values()) if is_dict else list(items or [])
    hit = [i for i in seq if isinstance(i, dict)
           and str(i.get("id") or "").startswith(id_prefix)]
    if not hit:
        actions.append(f"MISS {rel} id-prefix {id_prefix[:50]}")
        continue
    hit_ids = {str(i.get("id")) for i in hit}
    if is_dict:
        for key in [k for k, v in items.items()
                    if isinstance(v, dict) and str(v.get("id")) in hit_ids]:
            del items[key]
    else:
        profile["weaknesses"] = [
            i for i in seq
            if not (isinstance(i, dict) and str(i.get("id")) in hit_ids)
        ]
    yaml_io.write_yaml(path, profile)
    actions.append(f"REMOVE {rel} x{len(hit)} name={str(hit[0].get('name'))[:70]!r}")

for rel, id_prefix in TRIM.items():
    path = Path(rel)
    profile = yaml_io.load_yaml(path)
    items = profile.get("weaknesses")
    seq = list(items.values()) if isinstance(items, dict) else list(items or [])
    hit = [i for i in seq if isinstance(i, dict)
           and str(i.get("id") or "").startswith(id_prefix)]
    if not hit:
        actions.append(f"MISS {rel} id-prefix {id_prefix[:50]}")
        continue
    item = hit[0]
    name = str(item.get("name") or "")
    new_name = re.split(r"\.\s*Feats:.*$|\s+Feats:.*$", name)[0].rstrip(" .;,")
    if new_name and new_name != name:
        item["name"] = new_name
        yaml_io.write_yaml(path, profile)
        actions.append(f"TRIM {rel} -> {new_name[:80]!r}")
    else:
        actions.append(f"TRIM-SKIP {rel} name={name[:80]!r}")

for line in actions:
    print(line)
