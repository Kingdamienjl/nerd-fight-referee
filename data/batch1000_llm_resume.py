"""RESUME of the LLM mock-duel batch (batch_1000_llm_20261020).

Round 1 (batch1000_llm.py) completed 69 close duels before Fails PC Ollama
wedged under GPU contention. This resume variant:
  - loads the deterministic batch's exact pairs (same order/indices as round 1)
  - SKIPS close pairs already present in OUTDIR (matched by stored 'index')
  - runs ONLY the remaining close-strata pairs (231), then Phase 2:
    the same 50 forced-LLM stomp duels the original would have sampled
    (random.Random(999) over stomp pairs in deterministic order)
  - continues output file numbering after the existing files
  - wedge guard: if 10 consecutive finished duels are all non-LLM
    (fallback:*/error), it aborts instead of burning timeouts for hours
NEVER posts to Discord.
"""
import asyncio, collections, json, os, random, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/app/src")
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.tier_utils import maybe_stomp_decision
from battlebot.fight.llm_judge import judge_fight_packet

DET_DIR = Path("/app/data/mock_duels/batch_1000_20261019")
OUTDIR = Path("/app/data/mock_duels/batch_1000_llm_20261020")
OUTDIR.mkdir(parents=True, exist_ok=True)
PROGRESS = OUTDIR / "progress.log"
CONCURRENCY = 4
DUEL_TIMEOUT = 900
FORCED_STOMP_N = 50
WEDGE_WINDOW = 10

def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    with open(PROGRESS, "a") as f:
        f.write(line + "\n")

def verdict_method(decision, was_stomp, forced):
    if forced:
        d = decision.get("diagnostics", {}) or {}
        vs = d.get("verdict_source")
        fb = d.get("fallback_reason") or decision.get("fallback_reason")
        if vs == "schema_verdict":
            return "llm_schema"
        if vs:
            return f"llm_{vs}"
        if fb:
            return f"fallback:{fb}"
        if decision.get("winner") in (None, "needs_judge_review"):
            return "needs_judge_review"
        return "llm_unknown"
    if was_stomp:
        return "tier_stomp"
    d = decision.get("diagnostics", {}) or {}
    vs = d.get("verdict_source")
    if vs == "schema_verdict":
        return "llm_schema"
    if vs:
        return f"llm_{vs}"
    fb = d.get("fallback_reason") or decision.get("fallback_reason")
    if fb:
        return f"fallback:{fb}"
    if decision.get("winner") in (None, "needs_judge_review"):
        return "needs_judge_review"
    return "llm_unknown"

async def run_duel(n, stratum, pair, judge_sem, forced_llm=False):
    rec = {
        "index": n, "stratum": stratum, "forced_llm": forced_llm,
        "pair": pair,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    t0 = time.time()
    try:
        async with connect_database(None) as conn:
            packet = await build_fight_packet(conn, pair[0], pair[1])
        if packet.get("errors"):
            rec["method"] = "profile_error"
            rec["profile_errors"] = packet["errors"]
            rec["duration_s"] = round(time.time() - t0, 2)
            return rec, False
        was_stomp = False
        if forced_llm:
            async with judge_sem:
                decision = await asyncio.wait_for(judge_fight_packet(packet), timeout=DUEL_TIMEOUT)
        else:
            stomp = maybe_stomp_decision(packet)
            if stomp is not None:
                decision = stomp
                was_stomp = True
            else:
                async with judge_sem:
                    decision = await asyncio.wait_for(judge_fight_packet(packet), timeout=DUEL_TIMEOUT)
        rec["method"] = verdict_method(decision, was_stomp, forced_llm)
        rec["winner"] = decision.get("winner")
        rec["confidence"] = decision.get("confidence")
        rec["decision"] = decision
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec, True
    except Exception as exc:
        rec["method"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["duration_s"] = round(time.time() - t0, 2)
        return rec, False

async def main():
    # Load deterministic pairs, preserving original A/B assignment and indices
    pairs = []
    files = sorted(DET_DIR.glob("duel_*.json"))
    for f in files:
        d = json.loads(f.read_text())
        pairs.append((d["stratum"], d["pair"]))
    assert len(pairs) == 1000, f"expected 1000 pairs, got {len(pairs)}"

    # Load existing LLM results: skip what's already done
    existing_files = sorted(OUTDIR.glob("duel_*.json"))
    done_idx = set()
    forced_done = set()
    for f in existing_files:
        r = json.loads(f.read_text())
        if r.get("forced_llm"):
            forced_done.add(frozenset(r["pair"]))
        elif r.get("index") is not None:
            done_idx.add(r["index"])
    log(f"RESUME start: {len(existing_files)} result files present; "
        f"{len(done_idx)} main-phase indices done, {len(forced_done)} forced done")

    judge_sem = asyncio.Semaphore(CONCURRENCY)
    counter = {"done": len(existing_files), "fail": 0}
    recent_health = collections.deque(maxlen=WEDGE_WINDOW)
    state = {"wedge_abort": False}

    async def consume(coro_rec):
        rec, ok = await coro_rec
        healthy = rec.get("method", "").startswith("llm") or rec.get("method") == "tier_stomp"
        recent_health.append(healthy)
        if ok:
            counter["done"] += 1
            n = counter["done"]
            rec["file_index"] = n
            path = OUTDIR / f"duel_{n:04d}.json"
            path.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
            tag = "FORCED" if rec.get("forced_llm") else rec.get("stratum", "")
            log(f"DONE {n} [{tag}] {rec['pair'][0]} vs {rec['pair'][1]} -> {rec.get('winner')} ({rec['method']}, conf={rec.get('confidence')}, {rec['duration_s']}s)")
        else:
            counter["fail"] += 1
            log(f"FAIL [{rec.get('stratum')}] {rec['pair'][0]} vs {rec['pair'][1]}: {rec['method']} {rec.get('error') or rec.get('profile_errors')}")
        return ok

    def wedged():
        return len(recent_health) == WEDGE_WINDOW and not any(recent_health)

    async def run_waves(jobs, phase_label):
        tasks = []
        for coro in jobs:
            tasks.append(asyncio.create_task(consume(coro)))
            if len(tasks) >= 12:
                await asyncio.gather(*tasks)
                tasks = []
                if wedged():
                    state["wedge_abort"] = True
                    log(f"WEDGE ABORT during {phase_label}: {WEDGE_WINDOW} consecutive non-LLM outcomes; stopping to protect Fails PC")
                    return False
        if tasks:
            await asyncio.gather(*tasks)
            if wedged():
                state["wedge_abort"] = True
                log(f"WEDGE ABORT at end of {phase_label}: {WEDGE_WINDOW} consecutive non-LLM outcomes")
                return False
        return True

    # Phase 1 (resume): remaining CLOSE pairs only
    remaining_close = [
        (i, s, p) for i, (s, p) in enumerate(pairs)
        if s.startswith("close") and i not in done_idx
    ]
    log(f"PHASE 1 RESUME: {len(remaining_close)} close duels remaining")
    jobs = [run_duel(i, s, p, judge_sem) for (i, s, p) in remaining_close]
    ok = await run_waves(jobs, "PHASE 1")
    log(f"PHASE 1 RESUME COMPLETE done_total={counter['done']} fail={counter['fail']} aborted={state['wedge_abort']}")

    # Phase 2: 50 forced-LLM stomp duels — sample reproduced exactly as round 1
    if not state["wedge_abort"]:
        rng = random.Random(999)
        stomp_pairs = [(s, p) for (s, p) in pairs if s.startswith("stomp_")]
        forced = rng.sample(stomp_pairs, min(FORCED_STOMP_N, len(stomp_pairs)))
        forced = [(s, p) for (s, p) in forced if frozenset(p) not in forced_done]
        log(f"PHASE 2: {len(forced)} forced-LLM stomp duels start")
        jobs = [
            run_duel(1000 + i, s + "+forced_llm", p, judge_sem, forced_llm=True)
            for i, (s, p) in enumerate(forced)
        ]
        await run_waves(jobs, "PHASE 2")
        log(f"PHASE 2 COMPLETE done_total={counter['done']} fail={counter['fail']} aborted={state['wedge_abort']}")
    log("BATCH COMPLETE" if not state["wedge_abort"] else "BATCH ABORTED (wedge guard)")

asyncio.run(main())
