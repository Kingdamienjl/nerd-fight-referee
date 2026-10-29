#!/usr/bin/env python3
"""Frag-10: current validity state of the 13 gate-50m profiles (read-only)."""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

from battlebot.ingest.import_profiles import validate_profile_path

PATHS = [
    "profiles/needs_review/comics/teenage-mutant-ninja-turtles/casey-jones.yaml",
    "profiles/needs_review/comics/teenage-mutant-ninja-turtles/leatherhead.yaml",
    "profiles/needs_review/comics/teenage-mutant-ninja-turtles/shredder.yaml",
    "profiles/needs_review/comics/transformers/arcee.yaml",
    "profiles/needs_review/comics/transformers/blackarachnia.yaml",
    "profiles/needs_review/comics/transformers/devastator.yaml",
    "profiles/needs_review/comics/transformers/galvatron.yaml",
    "profiles/needs_review/comics/transformers/ironhide.yaml",
    "profiles/needs_review/comics/transformers/predaking.yaml",
    "profiles/needs_review/comics/transformers/rodimus-prime.yaml",
    "profiles/needs_review/comics/transformers/soundwave.yaml",
    "profiles/needs_review/comics/transformers/starscream.yaml",
    "profiles/needs_review/comics/transformers/ultra-magnus.yaml",
]

n_inv = 0
for p in PATHS:
    d = yaml.safe_load(open(p))
    gen = d.get("generation") or {}
    try:
        validate_profile_path(Path(p))
        verdict = "VALID"
    except Exception as e:  # noqa: BLE001 - report only
        verdict = "INVALID: " + str(e)[:200].replace("\n", " | ")
        n_inv += 1
    print(
        Path(p).name,
        "| status=", d.get("status"),
        "| elig=", d.get("battle_eligible"),
        "| inelig=", repr(gen.get("ineligible_reasons")),
        "| mtime=", datetime.utcfromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M"),
        "|", verdict,
    )
print("invalid_count=", n_inv)
