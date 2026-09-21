import asyncio
from pathlib import Path
import yaml
from battlebot.common.db import connect_database

async def check():
    async with connect_database("postgresql://battlebot:change_me@postgres:5432/battlebot") as conn:
        total_chars = await conn.fetchval("SELECT COUNT(*) FROM characters;")
        total_profiles = await conn.fetchval("SELECT COUNT(*) FROM character_profiles;")
        ready = await conn.fetchval("SELECT COUNT(*) FROM character_profiles WHERE battle_eligible = true;")
        not_ready = await conn.fetchval("SELECT COUNT(*) FROM character_profiles WHERE battle_eligible = false;")
        types = await conn.fetch("SELECT profile_type, COUNT(*) as cnt FROM character_profiles GROUP BY profile_type;")
        statuses = await conn.fetch("SELECT status, COUNT(*) as cnt FROM character_profiles GROUP BY status;")
        jobs = await conn.fetch("SELECT status, COUNT(*) as cnt FROM profile_jobs GROUP BY status;")

        print(f"=== DATABASE COUNTS ===")
        print(f"Total Characters: {total_chars}")
        print(f"Total Profiles: {total_profiles}")
        print(f"Battle-Eligible (Ready): {ready}")
        print(f"Not Eligible (Needs Review/Stub): {not_ready}")
        print(f"Profile Types: {[dict(r) for r in types]}")
        print(f"Statuses: {[dict(r) for r in statuses]}")
        print(f"Background Profile Jobs: {[dict(r) for r in jobs]}")
        
        # Check Akuma and 2B
        akuma = await conn.fetch("""
            SELECT c.canonical_name, cp.battle_eligible, cp.status, cp.profile_type, cp.profile_path
            FROM characters c
            LEFT JOIN character_profiles cp ON c.id = cp.character_id
            WHERE c.canonical_name ILIKE '%akuma%';
        """)
        twob = await conn.fetch("""
            SELECT c.canonical_name, cp.battle_eligible, cp.status, cp.profile_type, cp.profile_path
            FROM characters c
            LEFT JOIN character_profiles cp ON c.id = cp.character_id
            WHERE c.canonical_name ILIKE '%2b%' OR c.canonical_name ILIKE '%yorha%';
        """)
        print("\n=== MATCHUPS INVESTIGATION ===")
        print("Akuma matches:", [dict(r) for r in akuma])
        print("2B matches:", [dict(r) for r in twob])

    # Check local files
    print("\n=== LOCAL YAML FILES ===")
    gen_dir = Path("/app/profiles/generated")
    rev_dir = Path("/app/profiles/needs_review")
    stubs_dir = Path("/app/profiles/stubs")
    
    print(f"generated dir exists: {gen_dir.exists()} (count: {len(list(gen_dir.rglob('*.yaml'))) if gen_dir.exists() else 0})")
    print(f"needs_review dir exists: {rev_dir.exists()} (count: {len(list(rev_dir.rglob('*.yaml'))) if rev_dir.exists() else 0})")
    print(f"stubs dir exists: {stubs_dir.exists()} (count: {len(list(stubs_dir.rglob('*.yaml'))) if stubs_dir.exists() else 0})")

    for p in Path("/app/profiles").rglob("*.yaml"):
        p_str = p.name.lower()
        if "akuma" in p_str or "2b" in p_str or "yorha" in p_str:
            try:
                data = yaml.safe_load(p.read_text())
                print(f"File: {p.relative_to('/app/profiles')} | Name: {data.get('name')} | eligible: {data.get('battle_eligible')} | reasons: {data.get('generation', {}).get('ineligible_reasons')}")
            except Exception as e:
                print(f"Error {p}: {e}")

if __name__ == "__main__":
    asyncio.run(check())
