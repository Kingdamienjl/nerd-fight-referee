#!/usr/bin/env python3
"""Frag-3 dict-level demote verification (needs_review files are
loaded as dicts by the repair path; CharacterProfile validation is
the importer's gate, not the repair path's)."""
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.profiles import yaml_io

TAILS = (
    "anime/dragon-ball/beerus-game.yaml",
    "anime/dragon-ball/cell-classic.yaml",
    "anime/dragon-ball/future-trunks-anime.yaml",
    "anime/dragon-ball/trunks-anime.yaml",
    "anime/dragon-ball/vegeta-classic.yaml",
    "anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml",
)
for tail in TAILS:
    dst = Path("/app/profiles/needs_review") / tail
    src = Path("/app/profiles/generated") / tail
    prof = yaml_io.load_yaml(dst)
    print(
        tail,
        "dst_exists=", dst.exists(),
        "src_gone=", not src.exists(),
        "status=", prof.get("status"),
        "eligible=", prof.get("battle_eligible"),
        "stamp=", "template_cleanup_demotion" in prof,
    )
rim = yaml_io.load_yaml(
    Path("/app/profiles/needs_review/anime/that-time-i-got-reincarnated-as-a-slime/rimuru-tempest.yaml")
)
print("rimuru ap entry:", (rim.get("power_scale") or {}).get("attack_potency"))
print("rimuru ps order:", list((rim.get("power_scale") or {}).keys()))
