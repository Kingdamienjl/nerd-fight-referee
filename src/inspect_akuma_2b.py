import asyncio
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.fight.llm_judge import judge_fight_packet, referee_verdict

async def inspect_decision():
    async with connect_database("postgresql://battlebot:change_me@postgres:5432/battlebot") as conn:
        packet = await build_fight_packet(conn, "Akuma", "2B")
        smoke = smoke_judge_packet(packet)
        print("Smoke winner:", smoke.get("winner"))
        print("Smoke verdict_type:", smoke.get("verdict_type"))
        decision = await judge_fight_packet(packet, smoke)
        print("Decision winner:", decision.get("winner"))
        print("Referee verdict obj:", decision.get("referee_verdict"))

if __name__ == "__main__":
    asyncio.run(inspect_decision())
