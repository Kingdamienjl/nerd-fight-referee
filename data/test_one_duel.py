import asyncio, json, sys, time
sys.path.insert(0, "/app/src")
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.tier_utils import maybe_stomp_decision
from battlebot.fight.llm_judge import judge_fight_packet

async def main():
    async with connect_database(None) as conn:
        packet = await build_fight_packet(conn, "Doctor Octopus", "Captain America (Classic)")
    if packet.get("errors"):
        print("PACKET ERRORS:", packet["errors"]); return
    stomp = maybe_stomp_decision(packet)
    print("stomp:", stomp is not None)
    if stomp is None:
        t0 = time.time()
        decision = await asyncio.wait_for(judge_fight_packet(packet), timeout=600)
        print("duration_s:", round(time.time()-t0, 1))
        print("winner:", decision.get("winner"))
        print("confidence:", decision.get("confidence"))
        d = decision.get("diagnostics", {}) or {}
        print("verdict_source:", d.get("verdict_source"))
        print("fallback_reason:", d.get("fallback_reason") or decision.get("fallback_reason"))
asyncio.run(main())
