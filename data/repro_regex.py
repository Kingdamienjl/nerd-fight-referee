import sys, time
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")
from battlebot.harvest.auto_profile_harvester import normalize_extracted_value
for n in (16, 18, 20, 22):
    val = "x " + "=" * n + " more text after the run " + "word " * 50
    t0 = time.monotonic()
    out = normalize_extracted_value(val)
    print(f"N={n} wall={time.monotonic()-t0:.2f}s out_len={len(out)}", flush=True)
print("REPRO-DONE")
