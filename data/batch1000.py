"""Batch of 1000 mock duels for referee analysis. Mirrors bot/web production path:
maybe_stomp_decision first, then judge_fight_packet. NEVER posts to Discord."""
import asyncio, json, os, random, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/app/src")
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.tier_utils import maybe_stomp_decision
from battlebot.fight.llm_judge import judge_fight_packet

OUTDIR = Path("/app/data/mock_duels/batch_1000_20261019")
OUTDIR.mkdir(parents=True, exist_ok=True)
PROGRESS = OUTDIR / "progress.log"
SEED = 20261019
CONCURRENCY = 5

STRATA = [
    ("close_0.0-0.5", 0.0, 0.5, 75),
    ("close_0.5-1.0", 0.5, 1.0, 75),
    ("close_1.0-1.5", 1.0, 1.5, 75),
    ("close_1.5-2.0", 1.5, 2.0, 75),
    ("stomp_2.0-4.0", 2.0, 4.0, 250),
    ("stomp_4.0-6.0", 4.0, 6.0, 225),
    ("stomp_6.0+", 6.0, 99.0, 225),
]

def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    with open(PROGRESS, "a") as f:
        f.write(line + "\n")

def sample_pairs(idx, lo, hi, quota, rng):
    scored = [o for o in idx if o["score"] is not None]
    seen = set()
    pairs = []
    attempts = 0
    target = int(quota * 1.4) + 10
    while len(pairs) < target and attempts < target * 60:
        attempts += 1
        a, b = rng.sample(scored, 2)
        gap = abs(a["score"] - b["score"])
        if not (lo <= gap < hi):
            continue
        key = frozenset((a["name"], b["name"]))
        if key in seen:
            continue
        # prefer cross-franchise, but accept same-franchise after tries
        seen.add(key)
        pair = [a, b]
        rng.shuffle(pair)
        pairs.append({"a": pair[0], "b": pair[1], "gap": gap})
    return pairs

def verdict_method(decision, was_stomp):
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

async def run_duel(n, stratum, cand, judge_sem):
    rec = {
        "index": n, "stratum": stratum,
        "pair": [cand["a"]["name"], cand["b"]["name"]],
        "franchise": [cand["a"]["franchise"], cand["b"]["franchise"]],
        "tier": [cand["a"]["tier"], cand["b"]["tier"]],
        "tier_score": [cand["a"]["score"], cand["b"]["score"]],
        "tier_gap": round(cand["gap"], 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    t0 = time.time()
    try:
        async with connect_database(None) as conn:
            packet = await build_fight_packet(conn, cand["a"]["name"], cand["b"]["name"])
        if packet.get("errors"):
            rec["method"] = "profile_error"
            rec["profile_errors"] = packet["errors"]
            rec["duration_s"] = round(time.time() - t0, 2)
            return rec, False
        stomp = maybe_stomp_decision(packet)
        if stomp is not None:
            decision = stomp
            was_stomp = True
        else:
            async with judge_sem:
                decision = await asyncio.wait_for(judge_fight_packet(packet), timeout=900)
            was_stomp = False
        rec["method"] = verdict_method(decision, was_stomp)
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
    idx = json.load(open("/app/data/tier_index.json"))
    rng = random.Random(SEED)
    judge_sem = asyncio.Semaphore(CONCURRENCY)
    counter = {"done": 0}
    for stratum, lo, hi, quota in STRATA:
        cands = sample_pairs(idx, lo, hi, quota, rng)
        log(f"STRATUM {stratum}: quota={quota} candidates={len(cands)}")
        got = 0
        ci = 0
        pending = []
        async def consume(coro_rec):
            rec, ok = await coro_rec
            if ok:
                counter["done"] += 1
                got_local = counter["done"]
                path = OUTDIR / f"duel_{rec['index']:04d}.json"
                # index assigned at completion; use running done-count for filename
                path = OUTDIR / f"duel_{got_local:04d}.json"
                rec["file_index"] = got_local
                path.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
                log(f"DONE {got_local} [{rec['stratum']}] {rec['pair'][0]} vs {rec['pair'][1]} -> {rec.get('winner')} ({rec['method']}, conf={rec.get('confidence')}, {rec['duration_s']}s)")
            else:
                log(f"FAIL [{stratum}] {rec['pair'][0]} vs {rec['pair'][1]}: {rec['method']} {rec.get('error') or rec.get('profile_errors')}")
            return ok
        tasks = []
        while got < quota and ci < len(cands):
            # launch in waves to respect quota
            wave = []
            while ci < len(cands) and len(wave) < max(1, (quota - got)):
                cand = cands[ci]; ci += 1
                wave.append(asyncio.create_task(consume(run_duel(0, stratum, cand, judge_sem))))
                if len(wave) >= 12:
                    break
            if not wave:
                break
            results = await asyncio.gather(*wave)
            got += sum(1 for r in results if r)
        log(f"STRATUM {stratum} COMPLETE: got={got}/{quota}")
    log(f"BATCH COMPLETE total_done={counter['done']}")

asyncio.run(main())
