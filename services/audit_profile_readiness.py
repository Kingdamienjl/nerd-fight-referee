"""Audit structural readiness, optionally apply conservative flags and queue repairs."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from battlebot.common.db import connect_database
from battlebot.profiles.readiness import assess_readiness
from battlebot.profiles.store import decode_profile_json
from battlebot.review.queue import enqueue_job

async def run(args):
    report=[];counts=Counter();queued=0
    async with connect_database(None) as db:
        rows=await db.fetch('SELECT cp.profile_id,cp.character_id,cp.profile_hash,cp.profile_path,cp.status,cp.battle_eligible,cp.profile_json,c.canonical_name FROM character_profiles cp JOIN characters c ON c.id=cp.character_id ORDER BY c.canonical_name')
        for row in rows:
            profile=decode_profile_json(row['profile_json']);ready=assess_readiness(profile)
            counts[ready['level']]+=1
            report.append({'profile_id':row['profile_id'],'name':row['canonical_name'],'profile_hash':row['profile_hash'],'previous_status':row['status'],'previous_eligible':row['battle_eligible'],'readiness':ready})
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps({'timestamp':datetime.now(timezone.utc).isoformat(),'applied':False,'counts':dict(counts),'profiles':report},indent=2))
        if args.apply:
            async with db.transaction():
                for row,item in zip(rows,report):
                    if row['battle_eligible'] and not item['readiness']['battle_ready']:
                        await db.execute("UPDATE character_profiles SET battle_eligible=false,status='provisional',updated_at=now() WHERE profile_id=$1 AND profile_hash=$2",row['profile_id'],row['profile_hash'])
                    if queued < args.queue_limit and not item['readiness']['battle_ready']:
                        path=Path(row['profile_path'])
                        if path.is_file():
                            inserted=await enqueue_job(db,profile_path=str(path),target=str(path.parent),providers='vsbattles',priority=70,max_attempts=3)
                            queued+=bool(inserted)
            data=json.loads(output.read_text());data['applied']=True;data['repair_jobs_queued']=queued;output.write_text(json.dumps(data,indent=2))
    print(json.dumps({'counts':dict(counts),'applied':args.apply,'repair_jobs_queued':queued,'report':str(output)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--queue-limit',type=int,default=50);parser.add_argument('--output',default='data/reports/readiness-20260922.json');asyncio.run(run(parser.parse_args()))
