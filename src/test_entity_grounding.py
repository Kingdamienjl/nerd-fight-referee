import asyncio
import sys

sys.path.insert(0, "/app/src")
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.fight.llm_judge import judge_fight_packet, llm_output_violates_entity_grounding


async def main():
    async with connect_database() as conn:
        packet = await build_fight_packet(conn, "Ryu", "Radahn")
    smoke = smoke_judge_packet(packet)
    decision = await judge_fight_packet(packet, smoke)
    diag = decision.get("diagnostics") or {}
    print("Fallback:", diag.get("fallback"))
    print("Fallback Reason:", diag.get("fallback_reason"))
    print("Fallback Detail:", diag.get("fallback_detail"))
    print("LLM Guard Reasons:", decision.get("llm_guard_reasons"))
    print("Quick Verdict:", decision.get("quick_verdict"))
    print("Narrative Phases:")
    for phase in decision.get("narrative_phases") or []:
        print(" -", phase)
    from battlebot.fight.decision_formatter import format_fight_decision_embeds
    embeds = format_fight_decision_embeds(decision, packet)
    for i, e in enumerate(embeds):
        print(f"--- Embed {i}: {e.title} ---")
        if e.description:
            print(f"Desc: {e.description}")
        for f in e.fields:
            print(f"  Field [{f.name}]: {f.value}")


if __name__ == "__main__":
    asyncio.run(main())
