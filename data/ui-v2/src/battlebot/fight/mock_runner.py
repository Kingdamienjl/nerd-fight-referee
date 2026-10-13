"""Non-posting production smoke duels, with timestamped evidence reports."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.llm_judge import judge_fight_packet
from battlebot.fight.personality import details


async def run(args):
    pairs = [("Batman", "Superman"), ("Son Goku", "Vegeta")]
    while True:
        report = []
        async with connect_database(None) as connection:
            for first, second in pairs:
                packet = await build_fight_packet(connection, first, second)
                if packet.get("errors"):
                    report.append({"pair": [first, second], "profile_errors": packet["errors"]})
                    continue
                decision = await judge_fight_packet(packet)
                report.append({"pair": [first, second], "decision": decision,
                    "sections": details(decision, packet), "profile_hashes": packet.get("profile_hashes")})
        output = Path("data/mock_duels")
        output.mkdir(parents=True, exist_ok=True)
        path = output / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"report": str(path), "pairs": len(report), "results": [
            {"pair": r["pair"], "profile_errors": bool(r.get("profile_errors")),
             "diagnostics": r.get("decision", {}).get("diagnostics")} for r in report]}), flush=True)
        if not args.loop:
            return
        await asyncio.sleep(max(300, args.interval))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=1800)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
