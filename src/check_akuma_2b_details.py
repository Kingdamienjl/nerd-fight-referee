import asyncio
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet

async def check():
    async with connect_database("postgresql://battlebot:change_me@postgres:5432/battlebot") as conn:
        packet = await build_fight_packet(conn, "Akuma", "2B")
        pa = packet["contender_a"]
        pb = packet["contender_b"]
        print("Akuma power_scale:", pa.get("power_scale"))
        print("2B power_scale:", pb.get("power_scale"))
        print("Akuma abilities count:", len(pa.get("abilities", [])))
        print("2B abilities count:", len(pb.get("abilities", [])))
        smoke = smoke_judge_packet(packet)
        print("Smoke deciding_factors:", smoke.get("deciding_factors"))
        print("Smoke advantage_breakdown:", smoke.get("advantage_breakdown"))
        print("Smoke warnings:", smoke.get("warnings"))
        print("Smoke engine_reasoning:", smoke.get("engine_reasoning"))

if __name__ == "__main__":
    asyncio.run(check())
