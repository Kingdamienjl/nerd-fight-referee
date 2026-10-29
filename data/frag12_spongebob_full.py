"""SpongeBob full-path probe (read-only w.r.t. the real profile).

Copies the SpongeBob profile to a temp dir and runs the LIVE
recover_profile_evidence(dry_run=True) on the copy, timing the whole
call. dry_run writes nothing to disk. The outer `timeout` at launch
caps the run; a timeout kill here reproduces the frag-11 hang in the
full path (fetch + guard + rendered HTML + parse chain).
"""
import asyncio
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from battlebot.review import auto_repair


async def main():
    src = Path("/app/profiles/needs_review/mixed/adult-cartoons/spongebob-squarepants.yaml")
    tmp = Path("/tmp/sponge_probe")
    tmp.mkdir(exist_ok=True)
    copy = tmp / "spongebob-squarepants.yaml"
    shutil.copyfile(src, copy)
    t0 = time.monotonic()
    try:
        rep = await auto_repair.recover_profile_evidence(copy, dry_run=True)
    except Exception as exc:
        print(f"wall={time.monotonic()-t0:.1f}s EXCEPTION {type(exc).__name__}: {exc}", flush=True)
        return
    print(f"wall={time.monotonic()-t0:.1f}s", flush=True)
    print("recovered_fields:", rep.get("recovered_fields"), flush=True)
    print("sources_tried:", [(s.get("source_id"), s.get("fetch_status"), s.get("error")) for s in rep.get("sources_tried") or []], flush=True)
    print("parser_used:", rep.get("parser_used"), flush=True)
    print("guard_rejections:", len(rep.get("guard_rejections") or []), flush=True)
    print("identity_mismatch:", rep.get("identity_mismatch"), "error:", repr(rep.get("error")), flush=True)
    print("PROBE-DONE", flush=True)


asyncio.run(main())
