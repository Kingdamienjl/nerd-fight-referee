import asyncio
import json
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.fight.llm_judge import judge_fight_packet
from battlebot.fight.decision_formatter import structured_decision_output

async def test_akuma_2b():
    async with connect_database("postgresql://battlebot:change_me@postgres:5432/battlebot") as conn:
        packet = await build_fight_packet(conn, "Akuma", "2B")
        print("Packet errors:", packet.get("errors"))
        smoke = smoke_judge_packet(packet)
        print("Smoke verdict_type:", smoke.get("verdict_type"), "winner:", smoke.get("winner"))
        decision = await judge_fight_packet(packet, smoke)
        print("LLM decision verdict_type:", decision.get("verdict_type"), "winner:", decision.get("winner"))
        print("Raw decision keys:", list(decision.keys()))
        structured = structured_decision_output(decision)
        print("Structured winner:", structured.get("winner"))
        print("Structured summary:", structured.get("summary"))
        print("Contender A card:", structured.get("contender_a_card"))
        print("Contender B card:", structured.get("contender_b_card"))

if __name__ == "__main__":
    asyncio.run(test_akuma_2b())
