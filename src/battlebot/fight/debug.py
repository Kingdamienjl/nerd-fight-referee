"""CLI for building non-LLM fight debug packets."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from battlebot.common.db import connect_database
from battlebot.profiles.fight_packet import build_fight_packet


def truncate(value: str | None, limit: int = 140) -> str:
    if not value:
        return "n/a"
    return value if len(value) <= limit else f"{value[: limit - 3]}..."


def human_summary(packet: dict[str, Any]) -> str:
    if packet.get("errors"):
        lines = ["Fight packet errors:"]
        for error in packet["errors"]:
            lines.append(f"- {error['contender']}: {error['status']} for {error['query']!r}")
            for candidate in error.get("candidates", [])[:5]:
                lines.append(
                    f"  candidate: {candidate['canonical_name']} "
                    f"({candidate['franchise']}, {candidate['category']})"
                )
            diagnostics = error.get("diagnostics") or {}
            if diagnostics:
                lines.append("  not found in DB")
                generated_paths = diagnostics.get("generated_paths") or []
                needs_review_paths = diagnostics.get("needs_review_paths") or []
                closest = diagnostics.get("db_matches") or []
                if generated_paths:
                    lines.append("  found in generated:")
                    for path in generated_paths[:3]:
                        lines.append(f"    {path}")
                if needs_review_paths:
                    lines.append("  found in needs_review:")
                    for path in needs_review_paths[:3]:
                        lines.append(f"    {path}")
                if closest:
                    lines.append("  closest DB names:")
                    for match in closest[:5]:
                        lines.append(
                            f"    {match['canonical_name']} "
                            f"({match['franchise']}, {match['category']})"
                        )
        return "\n".join(lines)

    lines = [
        f"Ordered pair key: {packet['ordered_pair_key']}",
    ]
    for label in ("contender_a", "contender_b"):
        contender = packet[label]
        power = contender["power_scale"]
        lines.extend(
            [
                "",
                f"{label}: {contender['canonical_name']} "
                f"({contender['franchise']}, {contender['category']})",
                f"profile: {contender['profile_id']} hash={contender['profile_hash']}",
                f"abilities: {contender['ability_count']} weaknesses: {contender['weakness_count']}",
                f"attack: {truncate(power.get('attack_potency'))}",
                f"speed: {truncate(power.get('speed'))}",
                f"durability: {truncate(power.get('durability'))}",
            ]
        )
        warnings = contender.get("warnings") or []
        if warnings:
            lines.append(
                "warnings: "
                + ", ".join(str(warning.get("flag")) for warning in warnings[:5])
            )
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> int:
    async with connect_database(args.database_url) as connection:
        packet = await build_fight_packet(
            connection,
            args.contender_a,
            args.contender_b,
            rules={"debug": True},
        )
    if args.summary:
        print(human_summary(packet))
    else:
        print(json.dumps(packet, indent=2, sort_keys=True, default=str))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a non-LLM fight debug packet")
    parser.add_argument("contender_a")
    parser.add_argument("contender_b")
    parser.add_argument("--database-url")
    parser.add_argument("--summary", action="store_true")
    return parser


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_arg_parser().parse_args())))


if __name__ == "__main__":
    main()
