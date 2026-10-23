import asyncio, json, collections
from battlebot.common.db import connect_database

async def main():
    async with connect_database(None) as conn:
        row = await conn.fetchrow("""
            SELECT cp.profile_json FROM character_profiles cp
            WHERE cp.battle_eligible = true LIMIT 1
        """)
        pj = row["profile_json"]
        if isinstance(pj, str): pj = json.loads(pj)
        def keys(d, p=""):
            out = []
            if isinstance(d, dict):
                for k, v in d.items():
                    out.append(p+k)
                    out += keys(v, p+k+".")
            return out
        print("KEYS:", keys(pj)[:40])
        # find tier anywhere
        def find(d, path=""):
            if isinstance(d, dict):
                for k, v in d.items():
                    if "tier" in k.lower():
                        print("TIERKEY:", path+k, "=", str(v)[:80])
                    find(v, path+k+".")
            elif isinstance(d, list):
                for i, v in enumerate(d[:3]): find(v, path+f"[{i}].")
        find(pj)
asyncio.run(main())
