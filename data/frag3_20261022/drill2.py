#!/usr/bin/env python3
"""Frag-3 drill 2: why does the importer skip the cleaned files?
Run the importer's own validate+compile per target and print
battle_eligible + readiness + fingerprint-vs-state status."""
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.ingest import import_profiles

TARGETS = (
    "profiles/generated/anime/demon-slayer/shinobu-kocho.yaml",
    "profiles/generated/anime/dragon-ball/beerus-game.yaml",
    "profiles/generated/anime/dragon-ball/cell-classic.yaml",
    "profiles/generated/anime/dragon-ball/future-trunks-anime.yaml",
    "profiles/generated/anime/dragon-ball/trunks-anime.yaml",
    "profiles/generated/anime/dragon-ball/vegeta-classic.yaml",
    "profiles/generated/anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml",
)

state = import_profiles.load_import_state(Path("data/worker_import_state.json"))
for rel in TARGETS:
    path = Path("/app") / rel
    fp = import_profiles.profile_file_fingerprint(path)
    in_state = rel in (state.get("profiles") or {})
    changed = import_profiles.profile_fingerprint_changed(path, state, fp)
    try:
        profile = import_profiles.validate_profile_path(path)
        cand = import_profiles.compile_profile(profile, path)
        print(
            f"{rel}\n  in_state={in_state} changed={changed} "
            f"eligible={cand.profile.get('battle_eligible')} "
            f"readiness={cand.profile.get('readiness')}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{rel}\n  in_state={in_state} changed={changed} ERROR {type(exc).__name__}: {str(exc)[:200]}")
