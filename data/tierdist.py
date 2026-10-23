import asyncio, json, collections, sys
sys.path.insert(0, "/app/src")
from battlebot.common.db import connect_database
from battlebot.fight.tier_utils import strongest_tier

async def main():
    out = []
    async with connect_database(None) as conn:
        rows = await conn.fetch("""
            SELECT c.canonical_name, c.franchise, cp.profile_json
            FROM characters c JOIN character_profiles cp ON cp.character_id = c.id
            WHERE cp.battle_eligible = true
        """)
        for r in rows:
            pj = r["profile_json"]
            if isinstance(pj, str): pj = json.loads(pj)
            ttext = None
            try:
                ttext = (pj.get("power_scale") or {}).get("tier", {})
                if isinstance(ttext, dict): ttext = ttext.get("text")
            except Exception: pass
            tok = strongest_tier(ttext)
            out.append({"name": r["canonical_name"], "franchise": r["franchise"],
                        "tier": tok.display if tok else None, "score": tok.score if tok else None})
    with open("/app/data/tier_index.json", "w") as f:
        json.dump(out, f)
    scored = [o for o in out if o["score"] is not None]
    unscored = len(out) - len(scored)
    print(f"total={len(out)} scored={len(scored)} unscored={unscored}")
    import statistics
    scores = sorted(o["score"] for o in scored)
    print(f"score min={scores[0]:.2f} max={scores[-1]:.2f} median={statistics.median(scores):.2f}")
    buckets = collections.Counter()
    for o in scored:
        buckets[round(o["score"])] += 1
    print("SCORE BUCKETS:", dict(sorted(buckets.items())))
asyncio.run(main())
