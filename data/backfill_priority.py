import asyncio
import json
from pathlib import Path

from battlebot.common.db import connect_database
from battlebot.review.queue import priority_for_blocker_count


async def main() -> None:
    data = json.loads(Path("data/bulk_sweep_results.json").read_text())
    counts = data["blocker_counts"]
    async with connect_database(None) as conn:
        updated = 0
        for path, count in counts.items():
            res = await conn.execute(
                "UPDATE profile_jobs SET priority=$1, updated_at=now() "
                "WHERE profile_path=$2 AND status IN ('pending', 'retry')",
                priority_for_blocker_count(int(count)),
                path,
            )
            updated += int(str(res).split()[-1])
        print("rows updated:", updated)
        rows = await conn.fetch(
            "SELECT priority, count(*) AS c FROM profile_jobs "
            "WHERE status IN ('pending', 'retry') GROUP BY 1 ORDER BY 1"
        )
        for r in rows:
            print("priority", r["priority"], "jobs", r["c"])


asyncio.run(main())
