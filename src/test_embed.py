import asyncio
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.fight.llm_judge import judge_fight_packet
from battlebot.bot.commands.fight import fight_detail_payload, build_fight_embed

async def test():
    async with connect_database() as conn:
        packet = await build_fight_packet(conn, "Goku", "Ken Masters")
    smoke = smoke_judge_packet(packet)
    decision = await judge_fight_packet(packet, smoke)
    print("Diagnostics:", decision.get("diagnostics"))
    print("Decision Quick Verdict:", decision.get("quick_verdict"))
    print("Decision Phases:", decision.get("narrative_phases"))
    decision["presentation_packet"] = packet
    embed, analysis = build_fight_embed(decision)
    print("=== EMBED FIELDS ===")
    for f in embed.fields:
        print(f"[{f.name}]: {f.value}")
    payload = fight_detail_payload(decision)
    print("=== QUICK EVIDENCE ===")
    print(payload["quick_evidence"])
    print("=== QUICK VERDICT ===")
    print(payload["quick_verdict"])
    print("=== FULL BATTLE ===")
    print(payload["full_battle"])

if __name__ == "__main__":
    asyncio.run(test())
