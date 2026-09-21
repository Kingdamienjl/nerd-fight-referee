import asyncio, json
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.smoke_judge import smoke_judge_packet
from battlebot.fight.llm_judge import build_analyst_prompt, build_referee_stage2_prompt, call_ollama, _invoke_caller

async def main():
    async with connect_database() as conn:
        packet = await build_fight_packet(conn, "Goku", "Ken Masters")
    smoke = smoke_judge_packet(packet)
    analyst_msgs = build_analyst_prompt(packet, smoke)
    text = json.dumps(analyst_msgs)
    print("genjutsu in analyst prompt?", "genjutsu" in text.lower())
    if "genjutsu" in text.lower():
        for m in analyst_msgs:
            for line in m["content"].splitlines():
                if "genjutsu" in line.lower():
                    print("ANALYST LINE:", line)
    
    # Call analyst
    analyst_raw = await _invoke_caller(call_ollama, analyst_msgs, model="qwen3:8b")
    print("genjutsu in analyst_raw?", "genjutsu" in analyst_raw.lower())
    if "genjutsu" in analyst_raw.lower():
        print("=== ANALYST RAW ===")
        print(analyst_raw)
        print("===================")

    ref_msgs = build_referee_stage2_prompt(packet, smoke, analyst_raw)
    ref_text = json.dumps(ref_msgs)
    print("genjutsu in ref_msgs?", "genjutsu" in ref_text.lower())
    
    ref_raw = await _invoke_caller(call_ollama, ref_msgs, model="hermes3:8b")
    print("=== REFEREE RAW ===")
    print(ref_raw)
    print("===================")
    from battlebot.fight.llm_judge import llm_explained_decision
    dec = llm_explained_decision(smoke, ref_raw, packet=packet)
    print("Diagnostics:", dec.get("diagnostics"))
    print("Quick Verdict:", dec.get("quick_verdict"))
    print("Narrative Phases:", dec.get("narrative_phases"))

if __name__ == "__main__":
    asyncio.run(main())
