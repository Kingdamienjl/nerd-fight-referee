import asyncio, time, json, sys
sys.path.insert(0, "/app/src")
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.tier_utils import maybe_stomp_decision, fighter_tier
from battlebot.fight.llm_judge import judge_fight_packet

async def main():
    idx = json.load(open("/app/data/tier_index.json"))
    # find a close pair: same bucket, different franchises
    scored = [o for o in idx if o["score"] is not None]
    scored.sort(key=lambda o: o["score"])
    pair = None
    for i in range(len(scored)-1):
        a, b = scored[i], scored[i+1]
        if a["franchise"] != b["franchise"] and abs(a["score"]-b["score"]) < 0.3:
            pair = (a["name"], b["name"], abs(a["score"]-b["score"]))
            break
    print("PAIR:", pair, flush=True)
    async with connect_database(None) as conn:
        packet = await build_fight_packet(conn, pair[0], pair[1])
        if packet.get("errors"):
            print("PACKET ERRORS:", packet["errors"]); return
        stomp = maybe_stomp_decision(packet)
        print("STOMP:", "YES" if stomp else "no", flush=True)
        t0 = time.time()
        decision = await judge_fight_packet(packet)
        dt = time.time() - t0
        d = decision.get("diagnostics", {})
        print(f"TIME: {dt:.1f}s", flush=True)
        print("WINNER:", decision.get("winner"), "| CONF:", decision.get("confidence"),
              "| PIPELINE:", d.get("pipeline"), "| VERDICT_SRC:", d.get("verdict_source"), flush=True)
asyncio.run(main())
