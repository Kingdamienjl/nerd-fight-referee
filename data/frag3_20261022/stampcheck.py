#!/usr/bin/env python3
"""Frag-3: does a Job-2 continuity_demotion stamp validate?"""
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.ingest import import_profiles
from battlebot.schemas.profile import CharacterProfile

print("CharacterProfile extra config:", CharacterProfile.model_config.get("extra"))

for p in (
    Path("/app/profiles/needs_review/comic/marvel/blue-marvel-marvel-cinematic-universe.yaml"),
    Path("/app/profiles/needs_review/anime/dragon-ball/beerus-game.yaml"),
):
    try:
        prof = import_profiles.validate_profile_path(p)
        print(p.name, "VALIDATES, battle_eligible field:", prof.battle_eligible)
    except Exception as exc:  # noqa: BLE001
        print(p.name, "FAILS:", str(exc)[:220].replace("\n", " | "))
