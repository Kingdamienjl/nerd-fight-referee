import unittest
from unittest.mock import patch

from battlebot.bot.commands.catalog import (
    catalog_command_names,
    catalog_response_ephemeral,
    format_needs_review,
    format_repair_queue_command,
    is_admin_or_dm,
)
from battlebot.bot.commands.fight import discord_message_from_packet, fight_response_ephemeral
from battlebot.fight.smoke_judge import smoke_judge_packet


class BotFightCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_fight_message_uses_referee_decision_label(self):
        packet = {
            "errors": [],
            "contender_a": {
                "canonical_name": "Batman",
                "character_id": "batman",
                "power_scale": {
                    "attack_potency": "Building level",
                    "speed": "Peak Human",
                    "durability": "Building level",
                },
            },
            "contender_b": {
                "canonical_name": "Superman",
                "character_id": "superman",
                "power_scale": {
                    "attack_potency": "Solar System level",
                    "speed": "Massively FTL+",
                    "durability": "Solar System level",
                },
            },
            "warnings": [],
        }

        message = await discord_message_from_packet(packet, smoke_judge_packet(packet))

        self.assertIn("Nerd Fight Referee Decision", message)
        self.assertNotIn("pre-LLM", message)
        self.assertIn("winner: Superman", message)

    async def test_fight_output_uses_llm_decision_title_when_enabled(self):
        packet = {
            "errors": [],
            "contender_a": {
                "canonical_name": "Batman",
                "character_id": "batman",
                "power_scale": {"attack_potency": "Building level", "speed": "Peak Human", "durability": "Building level"},
            },
            "contender_b": {
                "canonical_name": "Superman",
                "character_id": "superman",
                "power_scale": {
                    "attack_potency": "Solar System level",
                    "speed": "Massively FTL+",
                    "durability": "Solar System level",
                },
            },
            "warnings": [],
        }

        async def fake_judge(packet_arg, smoke_arg):
            return {
                "title": "Nerd Fight Referee Decision",
                "winner": "Superman",
                "confidence": "strong",
                "summary": "Superman wins from packet-backed advantages.",
                "win_condition": "Speed and power decide the exchange.",
                "loser_best_path": "Batman needs listed counterplay.",
                "deciding_factors": [
                    {
                        "factor": "Initiative",
                        "evidence": "Superman leads speed.",
                        "tactical_effect": "He acts first and controls spacing.",
                    }
                ],
                "warnings": [],
                "judge_notes": [],
            }

        with patch("battlebot.bot.commands.fight.judge_fight_packet", fake_judge):
            message = await discord_message_from_packet(packet, smoke_judge_packet(packet))

        self.assertIn("Nerd Fight Referee Decision", message)
        self.assertNotIn("pre-LLM", message)
        self.assertIn("He acts first and controls spacing.", message)

    async def test_public_fight_not_found_hides_file_paths_and_includes_suggestions(self):
        packet = {
            "errors": [
                {
                    "contender": "contender_a",
                    "status": "not_found",
                    "query": "ironman",
                    "alias_match": {"canonical": "Iron Man"},
                    "canonical_not_battle_ready": True,
                    "diagnostics": {
                        "generated_paths": ["profiles/generated/comic/marvel/iron-man.yaml"],
                        "needs_review_paths": [],
                    },
                }
            ],
            "warnings": [],
        }
        smoke = smoke_judge_packet(packet)

        message = await discord_message_from_packet(packet, smoke)

        self.assertIn("alias matched: Iron Man", message)
        self.assertIn("not battle-ready yet", message)
        self.assertIn("/search", message)
        self.assertIn("Admins can queue repair", message)
        self.assertNotIn("profiles/generated", message)

    async def test_private_fight_not_found_can_include_diagnostics(self):
        packet = {
            "errors": [
                {
                    "contender": "contender_a",
                    "status": "not_found",
                    "query": "ironman",
                    "diagnostics": {
                        "generated_paths": ["profiles/generated/comic/marvel/iron-man.yaml"],
                        "needs_review_paths": ["profiles/needs_review/comic/marvel/iron-man.yaml"],
                    },
                }
            ],
            "warnings": [],
        }

        message = await discord_message_from_packet(packet, smoke_judge_packet(packet), include_diagnostics=True)

        self.assertIn("profiles/generated/comic/marvel/iron-man.yaml", message)
        self.assertIn("profiles/needs_review/comic/marvel/iron-man.yaml", message)

    def test_needs_review_lists_missing_fields(self):
        text = format_needs_review(
            [
                {
                    "name": "Usagi Tsukino",
                    "franchise": "Sailor Moon",
                    "category": "anime",
                    "review_reasons": ["missing_attack", "missing_speed"],
                }
            ]
        )

        self.assertIn("Usagi Tsukino", text)
        self.assertIn("missing_attack", text)

    def test_repair_queue_returns_terminal_command(self):
        text = format_repair_queue_command("comic", "DC", 25, True)

        self.assertIn("battlebot.review.batch_promote", text)
        self.assertIn("vsbattles,character_stats_profiles,superherodb,kaggle_superherodb", text)

    def test_sources_command_is_not_registered(self):
        self.assertNotIn("sources", catalog_command_names())

    def test_fight_visibility_defaults_public_with_private_override(self):
        self.assertFalse(fight_response_ephemeral())
        self.assertTrue(fight_response_ephemeral(private=True))

    def test_catalog_visibility_defaults_private_with_public_override(self):
        self.assertTrue(catalog_response_ephemeral())
        self.assertFalse(catalog_response_ephemeral(public=True))

    def test_admin_guard_allows_dm_and_blocks_non_admin_guild_user(self):
        class Permissions:
            administrator = False

        class User:
            guild_permissions = Permissions()

        class GuildInteraction:
            user = User()

        class DmInteraction:
            user = object()

        self.assertFalse(is_admin_or_dm(GuildInteraction()))
        self.assertTrue(is_admin_or_dm(DmInteraction()))


if __name__ == "__main__":
    unittest.main()
