#!/usr/bin/env python3
"""Frag-3: validate the demoted files compile (rimuru AP restored)."""
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.ingest import import_profiles

for tail in (
    "anime/dragon-ball/beerus-game.yaml",
    "anime/dragon-ball/vegeta-classic.yaml",
    "anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml",
):
    p = Path("/app/profiles/needs_review") / tail
    prof = import_profiles.validate_profile_path(p)
    cand = import_profiles.compile_profile(prof, p)
    ap = (cand.profile.get("power_scale") or {}).get("attack_potency") or {}
    print(
        tail,
        "valid=True eligible=",
        cand.profile.get("battle_eligible"),
        "ap_text=",
        repr(ap.get("text"))[:40],
        "status=",
        cand.profile.get("status"),
    )
