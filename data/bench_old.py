import time, sys
sys.path.insert(0, "/app/src")
from pathlib import Path
from battlebot.review import service

p = Path("/app/data/bench_notes_old.yaml")
note = {"profile_path": "bench", "field_path": "", "issue_type": "bench", "note": "bench note",
        "suggested_value": "", "source_id": "", "timestamp": service.utc_now(), "created_at": service.utc_now()}
t = time.time()
service.atomic_append_note(p, note)
print("OLD atomic_append_note on 21MB file: %.2fs" % (time.time() - t))
