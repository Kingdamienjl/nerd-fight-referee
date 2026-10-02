"""Proactive automated production duels with Discord Webhook broadcasting."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet
from battlebot.fight.llm_judge import judge_fight_packet
from battlebot.fight.personality import details
from battlebot.web.webhook import build_discord_webhook_payload, dispatch_discord_webhook

LOGGER = logging.getLogger(__name__)


async def get_random_or_curated_pair(connection):
    """Fetch an interesting random pair of battle-eligible characters or fallback to classics."""
    try:
        rows = await connection.fetch("""
            SELECT canonical_name 
            FROM characters 
            WHERE id IN (
                SELECT character_id 
                FROM character_profiles 
                WHERE battle_eligible = true
            )
            ORDER BY RANDOM() 
            LIMIT 2;
        """)
        if len(rows) >= 2:
            return (rows[0]["canonical_name"], rows[1]["canonical_name"])
    except Exception as exc:
        LOGGER.warning("Could not sample random fighters from DB: %s", exc)

    return ("Son Goku", "Vegeta")


async def run(args):
    curated_pairs = [("Batman", "Superman"), ("Son Goku", "Vegeta")]
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    while True:
        report = []
        async with connect_database(None) as connection:
            # Alternate between curated clashes and random battle-ready match-ups
            sampled_pair = await get_random_or_curated_pair(connection)
            run_pairs = [sampled_pair] if args.loop else curated_pairs

            for first, second in run_pairs:
                LOGGER.info("Simulating clash: %s vs %s", first, second)
                packet = await build_fight_packet(connection, first, second)
                if packet.get("errors"):
                    report.append({"pair": [first, second], "profile_errors": packet["errors"]})
                    continue
                decision = await judge_fight_packet(packet)
                sections = details(decision, packet)
                decision["sections"] = sections
                report.append({
                    "pair": [first, second],
                    "decision": decision,
                    "sections": sections,
                    "profile_hashes": packet.get("profile_hashes")
                })

                # Dispatch proactive fight result to Discord if webhook URL is configured
                if webhook_url:
                    try:
                        payload = build_discord_webhook_payload(
                            decision,
                            contender_a_name=first,
                            contender_b_name=second,
                            custom_note=f"??? **NEW SIMULATED MATCHUP**: `{first}` vs `{second}`!",
                        )
                        res = await dispatch_discord_webhook(webhook_url, payload)
                        LOGGER.info("Dispatched fight to Discord webhook: %s", res)
                    except Exception as exc:
                        LOGGER.error("Failed to dispatch duel result to Discord: %s", exc)

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
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=1800)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
