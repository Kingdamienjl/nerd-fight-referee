import asyncio
import asyncpg
import aiohttp
import json
import re
import os
import sys

LAYOUT_REGEX = re.compile(
    r'(?i)^\s*(\{\{Border|Scroll\s*=|Visible\s*=|Padding\s*=|Content\s*=|-|\{\{#tag:tabber|\{\{!|\{\{)', 
    re.IGNORECASE
)

def unpack_mediawiki_templates(text: str) -> list[dict]:
    text = re.sub(r'(?i)\{\{Border\s*\|(?:[^{}]*?\|)?Content\s*=\s*', '', text)
    text = re.sub(r'(?i)\{\{#tag:tabber\s*\|\s*[^=|]+=\s*', '', text)
    text = re.sub(r'\}\}', '', text)
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<ref[^/>]*/>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)
    text = text.replace("'''", "").replace("''", "")
    
    abilities = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('*'):
            name = line.lstrip('*').strip()
            name = re.sub(r'\[https?://[^\s\]]+\s*([^\]]*)\]', r'\1', name).strip()
            if name and len(name) > 2 and not re.search(r'(?i)\b(?:Border|Scroll|Visible|Padding|Content)\s*=', name):
                abilities.append({
                    'id': f'repaired-{len(abilities)+1}',
                    'name': name[:100],
                    'description': name,
                    'confidence': 0.85,
                    'tags': []
                })
    return abilities

async def fetch_wiki_abilities(session: aiohttp.ClientSession, wiki_url: str) -> list[dict]:
    try:
        page_title = wiki_url.split('/wiki/')[-1]
        api_url = 'https://vsbattles.fandom.com/api.php'
        params = {
            'action': 'query',
            'prop': 'revisions',
            'rvslots': 'main',
            'rvprop': 'content',
            'format': 'json',
            'redirects': '1',
            'titles': page_title
        }
        async with session.get(api_url, params=params, headers={'User-Agent': 'Mozilla/5.0 (AI-Nerd-Referee)'}, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            pages = data.get('query', {}).get('pages', {})
            for pid, page in pages.items():
                content = page.get('revisions', [{}])[0].get('slots', {}).get('main', {}).get('*', '')
                m = re.search(r'Powers and Abilities.*?(?=\n==|\n\|[A-Z]|\Z)', content, re.DOTALL | re.IGNORECASE)
                if m:
                    return unpack_mediawiki_templates(m.group(0))
    except Exception as e:
        pass
    return []

async def main():
    db_url = os.getenv('DATABASE_URL', 'postgresql://battlebot:change_me@postgres:5432/battlebot')
    conn = await asyncpg.connect(db_url)
    
    rows = await conn.fetch('''
        SELECT profile_id, profile_json 
        FROM character_profiles 
        WHERE EXISTS (
            SELECT 1 FROM jsonb_array_elements(profile_json->'abilities') a 
            WHERE a->>'name' ILIKE '%border%' OR a->>'name' ILIKE '%scroll=%' OR a->>'name' ILIKE '%tabber%'
        );
    ''')
    print(f"Found {len(rows)} profiles containing layout tags in abilities.")
    
    cleaned_count = 0
    refetched_count = 0
    
    async with aiohttp.ClientSession() as session:
        for idx, row in enumerate(rows):
            pid = row['profile_id']
            pj = json.loads(row['profile_json'])
            abilities = pj.get('abilities', [])
            cleaned = [a for a in abilities if not LAYOUT_REGEX.search(str(a.get('name', '')))]
            
            if len(cleaned) >= 3:
                pj['abilities'] = cleaned
                await conn.execute(
                    'UPDATE character_profiles SET profile_json = $1 WHERE profile_id = $2',
                    json.dumps(pj), pid
                )
                cleaned_count += 1
            else:
                sources = pj.get('sources', [])
                wiki_url = None
                for s in sources:
                    if 'vsbattles' in s.get('url', ''):
                        wiki_url = s['url']
                        break
                if wiki_url:
                    new_abs = await fetch_wiki_abilities(session, wiki_url)
                    if new_abs:
                        pj['abilities'] = new_abs
                        await conn.execute(
                            'UPDATE character_profiles SET profile_json = $1 WHERE profile_id = $2',
                            json.dumps(pj), pid
                        )
                        refetched_count += 1
                    else:
                        if cleaned:
                            pj['abilities'] = cleaned
                            await conn.execute(
                                'UPDATE character_profiles SET profile_json = $1 WHERE profile_id = $2',
                                json.dumps(pj), pid
                            )
                            cleaned_count += 1
                else:
                    if cleaned:
                        pj['abilities'] = cleaned
                        await conn.execute(
                            'UPDATE character_profiles SET profile_json = $1 WHERE profile_id = $2',
                            json.dumps(pj), pid
                        )
                        cleaned_count += 1
            
            if (idx + 1) % 50 == 0 or idx + 1 == len(rows):
                print(f"Processed {idx + 1}/{len(rows)} (Cleaned: {cleaned_count}, Refetched: {refetched_count})")
    
    print(f"\nFINISHED! Successfully cleaned {cleaned_count} profiles and re-fetched {refetched_count} profiles.")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
EOF
