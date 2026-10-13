"""Audit staged request recoveries; explicitly apply only new verified identities."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from expansion_identity_gate import check_origin
from battlebot.common.db import connect_database
from battlebot.ingest.import_profiles import validate_profile_path, compile_profile, upsert_compiled_profile


async def run(args):
    summary={'apply':args.apply,'imported':[],'ready':[],'existing':[],'rejected':[]}
    async with connect_database(os.environ['DATABASE_URL']) as db:
        async with db.transaction():
            if args.apply:
                await db.execute('LOCK TABLE characters IN SHARE ROW EXCLUSIVE MODE')
            summary['before']=await db.fetchval('SELECT count(*) FROM character_profiles')
            for path in sorted(args.root.rglob('*.yaml')):
                try:
                    profile=validate_profile_path(path)
                    compiled=compile_profile(profile,path)
                    if not profile.battle_eligible or not compiled.sources or not all(s['admissible'] for s in compiled.sources):
                        raise ValueError('Not eligible or missing admissible sources')
                    valid,reason=check_origin(profile, require_name=True)
                    if not valid:
                        raise ValueError(reason)
                except Exception as exc:
                    summary['rejected'].append({'path':str(path),'reason':str(exc)[:300]})
                    continue
                names=[compiled.character['canonical_name'].casefold()]+[a['normalized_alias'] for a in compiled.aliases]
                existing=await db.fetchval('''SELECT c.id FROM characters c
                    WHERE c.id=$1 OR lower(c.canonical_name)=ANY($2::text[])
                    OR EXISTS (SELECT 1 FROM character_aliases a WHERE a.character_id=c.id AND a.normalized_alias=ANY($2::text[]))
                    LIMIT 1''',compiled.character['id'],names)
                same_source=await db.fetchval('SELECT profile_id FROM profile_sources WHERE url=ANY($1::text[]) LIMIT 1',[s['url'] for s in compiled.sources])
                if existing or same_source:
                    summary['existing'].append({'name':profile.name,'match':existing or same_source})
                    continue
                entry={'name':profile.name,'id':compiled.character['id'],'path':str(path)}
                summary['ready'].append(entry)
                if args.apply:
                    await upsert_compiled_profile(db,compiled)
                    summary['imported'].append(entry)
            summary['after']=await db.fetchval('SELECT count(*) FROM character_profiles')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    temp=args.report.with_suffix('.tmp')
    temp.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    temp.replace(args.report)
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in summary.items()}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('profiles/request_recovery_v2/generated'))
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    asyncio.run(run(parser.parse_args()))
