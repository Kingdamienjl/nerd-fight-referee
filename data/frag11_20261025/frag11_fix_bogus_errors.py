#!/usr/bin/env python3
"""Remove the 103 bogus progress entries written by the first one-off
cohort attempt (10:08), whose --env-file was a 1-line file with literal
'\\n' sequences (Go-template formatting bug). That made an env var's
value the whole env dump, so every profile it touched errored instantly
with ValueError: invalid literal for int() ... '6000\\nHARVEST_OLLAMA_URL=...'.
No real recovery attempt happened for those profiles (0 log lines).
The 3 'no_recorded_mediawiki_sources' entries are legitimate outcomes
and are KEPT. Removing the bogus keys returns those profiles to the
todo for a clean re-run."""
import json
from pathlib import Path

progress_path = Path("/app/data/recovery_progress.json")
progress = json.loads(progress_path.read_text())
removed = []
kept_nosource = []
for key in list(progress):
    err = (progress.get(key) or {}).get("error") or ""
    if err.startswith("ValueError: invalid literal for int()"):
        removed.append(key)
        del progress[key]
    elif err == "no_recorded_mediawiki_sources":
        kept_nosource.append(key)
progress_path.write_text(json.dumps(progress, indent=1, sort_keys=True))
print(json.dumps({
    "removed_bogus_valueerror": len(removed),
    "kept_no_source": len(kept_nosource),
    "progress_keys_after": len(progress),
}, indent=1))
print("FIX DONE")
