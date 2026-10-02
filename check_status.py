import asyncio
from pathlib import Path
import yaml
from battlebot.common.db import connect_database

async def check():
    async with connect_database("postgresql://battlebot:change_me@postgres:5432/battlebot") as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM characters;")
        ready = await conn.fetchval("SELECT COUNT(*) FROM characters WHERE battle_ready = true;")
        not_ready = await conn.fetchval("SELECT COUNT(*) FROM characters WHERE battle_ready = false;")
        print(f"Postgres Characters: Total={total} | Battle-Ready={ready} | Needs-Review/Stub={not_ready}")
        
        akuma = await conn.fetch("SELECT canonical_name, battle_ready, status FROM characters WHERE canonical_name ILIKE '%akuma%';")
        twob = await conn.fetch("SELECT canonical_name, battle_ready, status FROM characters WHERE canonical_name ILIKE '%2b%' OR canonical_name ILIKE '%yorha%';")
        print("Akuma matches in DB:", [dict(r) for r in akuma])
        print("2B matches in DB:", [dict(r) for r in twob])

    # Check local YAML profile directories
    gen_dir = Path("/opt/referee/profiles/generated")
    rev_dir = Path("/opt/referee/profiles/needs_review")
    stubs_dir = Path("/opt/referee/profiles/stubs")
    
    gen_count = len(list(gen_dir.rglob("*.yaml"))) if gen_dir.exists() else 0
    rev_count = len(list(rev_dir.rglob("*.yaml"))) if rev_dir.exists() else 0
    stubs_count = len(list(stubs_dir.rglob("*.yaml"))) if stubs_dir.exists() else 0
    print(f"Local YAML Files: generated={gen_count} | needs_review={rev_count} | stubs={stubs_count}")

    # Search for akuma and 2b files
    for p in Path("/opt/referee/profiles").rglob("*.yaml"):
        if "akuma" in p.name.lower() or "2b" in p.name.lower() or "yorha" in p.name.lower():
            try:
                data = yaml.safe_load(p.read_text())
                print(f"File: {p.relative_to('/opt/referee/profiles')} | Name: {data.get('name')} | battle_eligible: {data.get('battle_eligible')} | status: {data.get('status')} | ineligibility: {data.get('generation', {}).get('ineligible_reasons')}")
            except Exception as e:
                print(f"Error reading {p}: {e}")

if __name__ == "__main__":
    asyncio.run(check())
