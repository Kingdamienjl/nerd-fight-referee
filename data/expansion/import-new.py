"""Import only new, eligible expansion identities; preserve existing live records."""
import asyncio
import json
import os
from pathlib import Path
from expansion_identity_gate import check_origin
from battlebot.common.db import connect_database
from battlebot.ingest.import_profiles import validate_profile_path, compile_profile, upsert_compiled_profile

async def main():
    summary = {'imported': [], 'existing': [], 'rejected': []}
    async with connect_database(os.environ['DATABASE_URL']) as db:
        async with db.transaction():
            await db.execute('LOCK TABLE characters IN SHARE ROW EXCLUSIVE MODE')
            summary['before'] = await db.fetchval('SELECT count(*) FROM character_profiles')
            for path in sorted(Path('profiles/expansion_staging/generated').rglob('*.yaml')):
                try:
                    profile = validate_profile_path(path)
                    compiled = compile_profile(profile, path)
                except Exception as exc:
                    summary['rejected'].append({'path': str(path), 'reason': str(exc)[:300]})
                    continue
                if not profile.battle_eligible or not compiled.sources or not all(s['admissible'] for s in compiled.sources):
                    summary['rejected'].append({'path': str(path), 'reason': 'Not eligible or missing admissible sources'})
                    continue
                identity_ok, identity_reason = check_origin(profile)
                if not identity_ok:
                    summary['rejected'].append({'path': str(path), 'reason': identity_reason})
                    continue
                names = [compiled.character['canonical_name'].casefold()] + [a['normalized_alias'] for a in compiled.aliases]
                existing = await db.fetchval('''SELECT c.id FROM characters c
                    WHERE c.id=$1 OR lower(c.canonical_name)=ANY($2::text[])
                    OR EXISTS (SELECT 1 FROM character_aliases a WHERE a.character_id=c.id AND a.normalized_alias=ANY($2::text[]))
                    LIMIT 1''', compiled.character['id'], names)
                same_source = await db.fetchval('SELECT profile_id FROM profile_sources WHERE url=ANY($1::text[]) LIMIT 1', [s['url'] for s in compiled.sources])
                if existing or same_source:
                    summary['existing'].append({'name':profile.name,'match':existing or same_source})
                    continue
                await upsert_compiled_profile(db, compiled)
                summary['imported'].append({'name':profile.name,'id':compiled.character['id']})
            summary['after'] = await db.fetchval('SELECT count(*) FROM character_profiles')
    Path('data/expansion/import-results-20260909.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary))

asyncio.run(main())
