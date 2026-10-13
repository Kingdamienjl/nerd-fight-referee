"""Require source Origin evidence to match the expansion roster franchise."""
import json
import re
import unicodedata
from pathlib import Path
from battlebot.harvest.auto_profile_harvester import first_revision, revision_content

def normalize(value):
    value=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().casefold()
    return ' '.join(re.sub(r'[^a-z0-9]+',' ',value).split())

def expected_franchise(value):
    value=normalize(value)
    value=re.sub(r'^more ', '', value)
    value=re.sub(r' expansion$', '', value)
    return {"soulcalibur": "soul calibur"}.get(value, value)

def origin_matches(franchise, origin):
    expected=expected_franchise(franchise)
    if not expected or expected=='horror icons':
        return False
    return bool(re.search(r'\b'+re.escape(expected)+r'\b',normalize(origin).replace('wizarding world', 'harry potter')))

def check_origin(profile, cache_dir=Path('data/cache')):
    origins=[]
    for source in profile.sources:
        data=source.model_dump() if hasattr(source,'model_dump') else source
        cache=cache_dir/(str(data.get('raw_cache_key') or '')+'.json')
        if not cache.is_file():
            return False, 'Missing cached source identity evidence'
        record=json.loads(cache.read_text())
        pages=record.get('body',{}).get('query',{}).get('pages',[])
        matched=[p for p in pages if str(p.get('pageid',''))==str(data.get('page_id','')) and p.get('pageid')]
        if len(matched)!=1:
            return False, 'Source page identity not verifiable'
        raw=revision_content(first_revision(matched[0]))
        found=re.findall(r"(?im)^\s*'{0,3}Origin'{0,3}\s*:'{0,3}\s*(.+)$",raw)
        origins.extend(found)
        if not found or not all(origin_matches(profile.franchise,origin) for origin in found):
            return False, 'Origin mismatch or unverified: '+repr(found)
    return bool(origins), '; '.join(origins)
