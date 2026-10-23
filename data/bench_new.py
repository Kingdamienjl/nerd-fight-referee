import time, sys, shutil, subprocess, os
sys.path.insert(0, "/app/src")
from pathlib import Path
import yaml
from battlebot.review import service

# fresh copy of the live file
shutil.copy("/app/profiles/review_notes.yaml", "/app/data/bench_notes_new.yaml")
p = Path("/app/data/bench_notes_new.yaml")

def count_notes(path):
    with open(path) as fh:
        return len(yaml.load(fh, Loader=yaml.CSafeLoader)["notes"])

n0 = count_notes(p)
print("notes before:", n0)

note = {"profile_path": "bench", "field_path": "", "issue_type": "bench", "note": "bench note",
        "suggested_value": "", "source_id": "", "timestamp": service.utc_now(), "created_at": service.utc_now()}
t = time.time(); service.atomic_append_note(p, dict(note)); dt = time.time() - t
print("NEW append #1: %.3fs" % dt)
t = time.time()
for i in range(20): service.atomic_append_note(p, dict(note))
print("NEW appends #2-21 avg: %.4fs each" % ((time.time() - t) / 20))
print("notes after sequential:", count_notes(p), "expected:", n0 + 21)

# concurrency: 6 processes x 20 appends each on a second fresh copy
shutil.copy("/app/profiles/review_notes.yaml", "/app/data/bench_notes_conc.yaml")
code = (
    "import sys; sys.path.insert(0,'/app/src')\n"
    "from pathlib import Path\n"
    "from battlebot.review import service\n"
    "p=Path('/app/data/bench_notes_conc.yaml')\n"
    "for i in range(20):\n"
    "    service.atomic_append_note(p, {'profile_path':'conc','field_path':'','issue_type':'conc','note':'c%d'%i,'suggested_value':'','source_id':'','timestamp':'t','created_at':'t'})\n"
)
procs = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(6)]
rcs = [pr.wait() for pr in procs]
print("conc rcs:", rcs)
nc = count_notes("/app/data/bench_notes_conc.yaml")
print("notes after concurrency:", nc, "expected:", n0 + 120, "LOSS:", (n0 + 120) - nc)
