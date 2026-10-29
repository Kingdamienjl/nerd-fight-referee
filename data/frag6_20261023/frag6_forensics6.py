#!/usr/bin/env python3
"""Frag-6 gate forensics #6 (light): among profiles whose files carry
the 'auto_repair source extraction' marker (recovery-merged at some
point), how many tier texts are code-stripped (no '{{')? Establishes
whether rex-splode's tier form is the pipeline's standing recovery
normalization or a one-off."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import yaml

out = subprocess.run(
    ["grep", "-rl", "auto_repair source extraction", "/app/profiles"],
    capture_output=True, text=True, timeout=600)
files = [Path(l) for l in out.stdout.splitlines() if l.strip()]
coded = stripped = notier = 0
examples = []
for path in files:
    try:
        prof = yaml.load(path.open(), Loader=yaml.CSafeLoader) or {}
    except Exception:
        continue
    tier = ((prof.get("power_scale") or {}).get("tier") or {})
    if not isinstance(tier, dict):
        notier += 1
        continue
    text = str(tier.get("text") or "")
    if not text:
        notier += 1
    elif "{{" in text:
        coded += 1
    else:
        stripped += 1
        if len(examples) < 8:
            examples.append((path.name, text[:80]))
print(f"auto_repair_files={len(files)} tier_coded={coded} "
      f"tier_code_stripped={stripped} tier_empty_or_absent={notier}")
for name, text in examples:
    print("STRIPPED:", name, "|", text)
