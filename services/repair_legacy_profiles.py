"""Resumable, source-pinned repair lane. Dry run unless --apply is supplied.

Only unreviewed profiles with one unambiguous pinned source are eligible. Source
identity, schema and structural evidence must all pass before replacement.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import yaml
from battlebot.common.db import connect_database
from battlebot.harvest.auto_profile_harvester import (RosterRow, RawCache, HttpClient, ProfileHarvester, build_profile, stable_hash_without_profile_hash)
from battlebot.profiles.readiness import assess_readiness
from battlebot.schemas.profile import CharacterProfile
from battlebot.ingest.import_profiles import compile_profile, upsert_compiled_profile

POLICY = 'legacy-repair-20260922-v2'
PROTECTED = {'verified', 'approved_override', 'approved'}


from battlebot.profiles.source_identity import identity_matches


def pinned_source(profile):
    candidates = {}
    for source in profile.get('sources') or []:
        if not isinstance(source, dict):
            continue
        if urlsplit(str(source.get('url') or '')).hostname != 'vsbattles.fandom.com':
            continue
        if not re.fullmatch(r'[1-9][0-9]*', str(source.get('page_id') or '')) or not source.get('revision_id'):
            continue
        if not identity_matches(profile.get('name'), source.get('title'), profile.get('franchise')):
            continue
        candidates[str(source['page_id'])] = source
    return next(iter(candidates.values())) if len(candidates) == 1 else None


def title_source(profile):
    """Recover a previously fetched page title; never trust discovery candidates."""
    candidates={}
    for source in profile.get('sources') or []:
        if not isinstance(source,dict) or not source.get('raw_cache_key'):
            continue
        if urlsplit(str(source.get('url') or '')).hostname != 'vsbattles.fandom.com':
            continue
        if identity_matches(profile.get('name'),source.get('title'),profile.get('franchise')):
            candidates[str(source.get('url'))]=source
    return next(iter(candidates.values())) if len(candidates)==1 else None


def digest(content):
    return hashlib.sha256(content).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, default=str))
    temporary.replace(path)


async def promote(candidate, path, original, args, archive):
    model = CharacterProfile.model_validate(candidate)
    relative = path.relative_to(args.root)
    compiled = compile_profile(model, Path('profiles/generated') / relative)
    if not compiled.profile['battle_eligible']:
        raise ValueError('Compiled profile failed readiness')
    archive.mkdir(parents=True, exist_ok=True)
    (archive / 'original.yaml').write_bytes(original)
    (archive / 'candidate.yaml').write_text(yaml.safe_dump(candidate, sort_keys=False, allow_unicode=True))
    candidate_bytes=yaml.safe_dump(candidate, sort_keys=False, allow_unicode=True).encode('utf-8')
    installed=False
    try:
        async with connect_database(None) as db:
            async with db.transaction():
                existing = await db.fetchrow('SELECT profile_hash,profile_json,status FROM character_profiles WHERE profile_id=$1 FOR UPDATE', candidate['id'])
                if existing and existing['status'] in PROTECTED:
                    raise ValueError('Database profile has protected review status')
                old = yaml.load(original, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
                if existing and existing['profile_hash'] != old.get('profile_hash'):
                    raise ValueError('Database and file differ; refusing to overwrite newer work')
                if path.read_bytes() != original:
                    raise ValueError('Profile changed during extraction')
                write_json(archive / 'database-before.json', dict(existing) if existing else {})
                await upsert_compiled_profile(db, compiled)
                temporary = path.with_suffix('.repair.tmp')
                temporary.write_bytes(candidate_bytes)
                temporary.replace(path)
                installed=True
    except BaseException:
        if installed and path.read_bytes()==candidate_bytes:
            temporary=path.with_suffix('.rollback.tmp')
            temporary.write_bytes(original)
            temporary.replace(path)
        raise
    # Durable archive permits recovery if a process dies between filesystem/DB commits.


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    state_path = args.output / ('apply-state.json' if args.apply else 'preview-state.json')
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    http = HttpClient(cache=RawCache(args.output/'cache'), user_agent='NerdRefereeEvidenceRepair/1.0', min_interval_seconds=2, use_cache=True)
    harvester = ProfileHarvester(http=http, mediawiki_api='https://vsbattles.fandom.com/api.php', output_dir=args.output/'candidates', needs_review_dir=args.output/'review', force=True, debug_extract=False)
    preview_path=args.output/'preview-state.json'
    preview=json.loads(preview_path.read_text()) if preview_path.exists() else {}
    selected=[]; summary=Counter()
    for path in sorted(args.root.rglob('*.yaml')):
        original=path.read_bytes()
        try:
            profile=yaml.load(original, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
            if not isinstance(profile,dict):
                continue
            if profile.get('status') in PROTECTED:
                summary['protected']+=1; continue
            readiness=assess_readiness(profile)
            if readiness['battle_ready']:
                summary['already_structurally_ready']+=1; continue
            key=str(path.relative_to(args.root))
            fingerprint=POLICY+':'+digest(original)
            if args.apply and (preview.get(key,{}).get('status')!='validated_candidate' or preview[key].get('fingerprint')!=fingerprint):
                summary['awaiting_validated_preview']+=1; continue
            previous=state.get(key,{})
            if previous.get('fingerprint')==fingerprint and (previous.get('status') != 'error' or time.time() < previous.get('retry_after',0)):
                summary['already_attempted']+=1; continue
            source=pinned_source(profile) or title_source(profile)
            if not source:
                summary['needs_source_identity']+=1; continue
            selected.append((len(readiness['blockers']), key, path, original, profile, source, fingerprint))
            if len(selected)>=args.limit:
                break
        except (ValueError,yaml.YAMLError):
            summary['invalid_yaml']+=1
    selected.sort(key=lambda entry:(entry[0],entry[1]))
    for _,key,path,original,old,source,fingerprint in selected[:args.limit]:
        result={'fingerprint':fingerprint,'name':old.get('name'),'timestamp':datetime.now(timezone.utc).isoformat()}
        archive=args.output/'attempts'/digest(original)
        try:
            row=RosterRow(category=old['category'],franchise=old['franchise'],name=old['name'],aliases=old.get('aliases') or [],wiki_title=source['title'],wiki_url=source['url'],wiki_page_id=str(source['page_id']) if re.fullmatch(r'[1-9][0-9]*',str(source.get('page_id') or '')) else None)
            wiki=await asyncio.wait_for(harvester.fetch_mediawiki_source(row),timeout=45)
            if not wiki or not identity_matches(row.name,wiki['title'],row.franchise):
                raise ValueError('Source identity could not be confirmed')
            if not row.wiki_page_id and not (wiki.get('fields') or {}).get('origin'):
                raise ValueError('Title-only recovery requires source franchise evidence')
            candidate=build_profile(row=row,anilist_identity=None,igdb_identity=None,wiki_source=wiki,errors=[])
            candidate['id']=old['id']
            candidate['profile_hash']=stable_hash_without_profile_hash(candidate)
            CharacterProfile.model_validate(candidate)
            readiness=assess_readiness(candidate)
            result['blockers']=readiness['blockers']
            result['source_revision']=wiki['revision_id']
            archive.mkdir(parents=True,exist_ok=True)
            (archive/'candidate.yaml').write_text(yaml.safe_dump(candidate,sort_keys=False,allow_unicode=True))
            if readiness['battle_ready'] and candidate['battle_eligible']:
                if args.apply:
                    await promote(candidate,path,original,args,archive)
                result['status']='promoted' if args.apply else 'validated_candidate'
            else:
                result['status']='needs_review'
        except Exception as error:
            result['status']='error';result['error']=str(error)[:500];result['retry_after']=time.time()+3600
        state[key]=result
        summary[result['status']]+=1
        write_json(state_path,state)
        print(json.dumps({'profile':key,**result}),flush=True)
    write_json(args.output/'latest-summary.json',dict(summary))
    print(json.dumps({'summary':dict(summary),'apply':args.apply}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=12)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if not 1<=args.limit<=100:
        parser.error('--limit must be between 1 and 100')
    asyncio.run(run(args))
