"""LLM 1000-duel batch for referee analysis. Reuses the EXACT pairs from the
deterministic batch (batch_1000_20261019) so results are directly comparable.
Runs the production pipeline with LLM enabled: maybe_stomp_decision first,
then judge_fight_packet. Plus 50 forced-LLM stomp duels as a bonus check.
NEVER posts to Discord."""
import asyncio, json, os, random, sys, time
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
    # Load deterministic pairs, preserving original A/B assignment
    pairs = []
    files = sorted(DET_DIR.glob("duel_*.json"))
    log(f"loaded {len(files)} deterministic duel files")
    for f in files:
        d = json.loads(f.read_text())
        pairs.append((d["stratum"], d["pair"]))
    assert len(pairs) == 1000, f"expected 1000 pairs, got {len(pairs)}"

    judge_sem = asyncio.Semaphore(CONCURRENCY)
    counter = {"done": 0, "fail": 0}

    async def consume(coro_rec):
        rec, ok = await coro_rec
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

    # Phase 1: main 1000, same pairs as deterministic batch
    log("PHASE 1: 1000 comparison duels start")
    tasks = []
    for i, (stratum, pair) in enumerate(pairs):
        tasks.append(asyncio.create_task(consume(run_duel(i, stratum, pair, judge_sem))))
        if len(tasks) >= 12:
            await asyncio.gather(*tasks)
            tasks = []
    if tasks:
        await asyncio.gather(*tasks)
    log(f"PHASE 1 COMPLETE done={counter['done']} fail={counter['fail']}")

    # Phase 2: 50 forced-LLM stomp duels (does LLM agree with tier math on obvious fights?)
    rng = random.Random(999)
    stomp_pairs = [(s, p) for (s, p) in pairs if s.startswith("stomp_")]
    forced = rng.sample(stomp_pairs, min(FORCED_STOMP_N, len(stomp_pairs)))
    log(f"PHASE 2: {len(forced)} forced-LLM stomp duels start")
    tasks = []
    for i, (stratum, pair) in enumerate(forced):
        tasks.append(asyncio.create_task(consume(run_duel(1000 + i, stratum + "+forced_llm", pair, judge_sem, forced_llm=True))))
        if len(tasks) >= 12:
            await asyncio.gather(*tasks)
            tasks = []
    if tasks:
        await asyncio.gather(*tasks)
    log(f"PHASE 2 COMPLETE done={counter['done']} fail={counter['fail']}")
    log("BATCH COMPLETE")

asyncio.run(main())
