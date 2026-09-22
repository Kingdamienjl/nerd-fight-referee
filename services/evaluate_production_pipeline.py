"""Read-only matchup evaluation. Never dispatches Discord messages or imports profiles."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.llm_judge import judge_fight_packet, call_ollama, build_analyst_prompt, compact_evidence_packet
from battlebot.fight.smoke_judge import smoke_judge_packet

async def main(args):
    report = []
    async with connect_database(None) as db:
        await db.execute('SET default_transaction_read_only = on')
        packet = await build_fight_packet(db, args.fighter_a, args.fighter_b)
    if packet.get('errors'):
        raise RuntimeError('Evaluation fighter evidence unavailable')
    for analyst,voice in [tuple(pair.split(',', 1)) for pair in args.models]:
        calls=[]
        async def measured(messages, *, model=None, env=None):
            start=time.monotonic()
            raw=await call_ollama(messages,model=model,env=env)
            calls.append({'model':model,'seconds':round(time.monotonic()-start,2),'prompt_chars':sum(len(x['content']) for x in messages),'output_chars':len(raw),'raw':raw})
            return raw
        measured.is_2llm=True
        env={**os.environ,'BATTLEBOT_LLM_ENABLED':'true','REFEREE_ANALYST_MODEL':analyst,'REFEREE_VOICE_MODEL':voice,'BATTLEBOT_2LLM_ENABLED':'true','BATTLEBOT_LLM_NUM_CTX':'8192','BATTLEBOT_LLM_NUM_PREDICT':'1200','BATTLEBOT_LLM_TIMEOUT_SECONDS':'150'}
        start=time.monotonic()
        result=await judge_fight_packet(packet,env=env,ollama_caller=measured)
        item={'pair':[args.fighter_a,args.fighter_b],'analyst':analyst,'voice':voice,'seconds':round(time.monotonic()-start,2),'calls':calls,'winner':result.get('winner'),'difficulty':result.get('difficulty'),'diagnostics':result.get('diagnostics'),'quick_verdict':result.get('quick_verdict'),'phases':result.get('narrative_phases'),'analyst_breakdown':result.get('analyst_breakdown'),'profile_hashes':packet.get('profile_hashes')}
        report.append(item)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report,indent=2))
        print(json.dumps({k:item[k] for k in ['pair','analyst','voice','seconds','winner','difficulty','diagnostics']}),flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fighter_a')
    parser.add_argument('fighter_b')
    parser.add_argument('--models', action='append', default=None, help='Analyst,voice model pair; repeat for comparison')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    args.models = args.models or ['qwen3:8b,hermes3:8b']
    if any(len(pair.split(',')) != 2 or not all(pair.split(',')) for pair in args.models):
        parser.error('--models requires analyst,voice')
    asyncio.run(main(args))
