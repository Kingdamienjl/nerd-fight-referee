import sys,asyncio,json,os
from pathlib import Path
sys.path.insert(0,'data/ui-v2/src')
from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.llm_judge import judge_fight_packet,call_ollama
from battlebot.bot.commands.fight import build_fight_embed,fight_detail_payload,FightDetailsView,FightPanelView
async def main():
 reports=[]
 async with connect_database(None) as db:
  for a,b in [('The Flash','Green Lantern'),('Big Barda','Zatanna')]:
   packet=await build_fight_packet(db,a,b)
   if packet.get('errors'):
    print(json.dumps({'pair':[a,b],'errors':packet['errors']}));continue
   raw=[]
   async def caller(messages,env=None):
    text=await call_ollama(messages,env=env);raw.append(text);return text
   env={**os.environ,'BATTLEBOT_LLM_NUM_PREDICT':'1800','BATTLEBOT_LLM_NUM_CTX':'8192'}
   decision=await judge_fight_packet(packet,env=env,ollama_caller=caller)
   embed,_=build_fight_embed(decision);payload=fight_detail_payload(decision)
   view=FightDetailsView(payload)
   report={'pair':[a,b],'winner':decision.get('winner'),'quick':decision.get('quick_verdict'),'phases':decision.get('narrative_phases'),'difficulty':decision.get('difficulty'),'diagnostics':{k:decision.get('diagnostics',{}).get(k) for k in ('fallback','fallback_reason','fallback_detail')},'raw':raw,'embed':embed.to_dict(),'buttons':[x.label for x in view.children],'source_panel':payload['sources']}
   reports.append(report);print(json.dumps({k:v for k,v in report.items() if k not in ('embed','source_panel','raw')}))
   view.stop()
 Path('data/ui-v2/qa-results.json').write_text(json.dumps(reports,indent=2))
asyncio.run(main())
