"""1000-duel batch, DETERMINISTIC pipeline (Fails PC Ollama unreachable).
Mirrors bot/web production path with LLM disabled:
  maybe_stomp_decision -> tier_stomp | judge_fight_packet(env LLM off) -> deterministic_fallback.
NEVER posts to Discord (no webhook calls anywhere)."""
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
CONCURRENCY = 8
DET_ENV = {**dict(os.environ), "BATTLEBOT_LLM_ENABLED": "false"}

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
        seen.add(key)
        pair = [a, b]
        rng.shuffle(pair)
        pairs.append({"a": pair[0], "b": pair[1], "gap": gap})
    return pairs

async def run_duel(stratum, cand, db_sem):
    rec = {
        "stratum": stratum,
        "pair": [cand["a"]["name"], cand["b"]["name"]],
        "franchise": [cand["a"]["franchise"], cand["b"]["franchise"]],
        "tier": [cand["a"]["tier"], cand["b"]["tier"]],
        "tier_score": [cand["a"]["score"], cand["b"]["score"]],
        "tier_gap": round(cand["gap"], 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    t0 = time.time()
    try:
        async with db_sem:
            async with connect_database(None) as conn:
                packet = await build_fight_packet(conn, cand["a"]["name"], cand["b"]["name"])
        if packet.get("errors"):
            rec["method"] = "profile_error"
            rec["profile_errors"] = packet["errors"]
            rec["duration_s"] = round(time.time() - t0, 2)
            return rec, False
        stomp = maybe_stomp_decision(packet, env=DET_ENV)
        if stomp is not None:
            decision = stomp
            rec["method"] = "tier_stomp"
        else:
            decision = await asyncio.wait_for(
                judge_fight_packet(packet, env=DET_ENV), timeout=120)
            fb = (decision.get("diagnostics") or {}).get("fallback_reason")
            rec["method"] = f"deterministic_fallback:{fb}" if fb else "deterministic_fallback"
        rec["winner"] = decision.get("winner")
        rec["loser"] = decision.get("loser")
        rec["confidence"] = decision.get("confidence")
        rec["deciding_factors"] = decision.get("deciding_factors")
        rec["winner_probability"] = decision.get("winner_probability")
        rec["advantage_breakdown"] = decision.get("advantage_breakdown")
        rec["engine_verdict"] = decision.get("engine_verdict")
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
    db_sem = asyncio.Semaphore(CONCURRENCY)
    done = 0
    fails = 0
    for stratum, lo, hi, quota in STRATA:
        cands = sample_pairs(idx, lo, hi, quota, rng)
        log(f"STRATUM {stratum}: quota={quota} candidates={len(cands)}")
        got = 0
        ci = 0
        while got < quota and ci < len(cands):
            wave = [asyncio.create_task(run_duel(stratum, cands[ci + i], db_sem))
                    for i in range(min(20, len(cands) - ci, (quota - got) * 2))]
            ci += len(wave)
            for coro in asyncio.as_completed(wave):
                rec, ok = await coro
                if ok:
                    done += 1
                    got += 1
                    rec["index"] = done
                    (OUTDIR / f"duel_{done:04d}.json").write_text(
                        json.dumps(rec, indent=2, default=str), encoding="utf-8")
                    if done % 50 == 0:
                        log(f"PROGRESS {done}/1000")
                else:
                    fails += 1
                    log(f"FAIL [{stratum}] {rec['pair'][0]} vs {rec['pair'][1]}: {rec['method']} {rec.get('error') or rec.get('profile_errors')}")
                if got >= quota:
                    for t in wave:
                        if not t.done():
                            t.cancel()
                    break
        log(f"STRATUM {stratum} COMPLETE: got={got}/{quota} fails={fails}")
    log(f"BATCH COMPLETE total_done={done} fails={fails}")

asyncio.run(main())
