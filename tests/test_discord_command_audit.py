import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from battlebot.bot import audit
from battlebot.bot.commands.fight import (
    FightDetailsView,
    build_confidence_embed_color,
    build_fight_embed,
    fight_detail_payload,
    send_deferred_fight_result,
    send_ephemeral_chunks,
)


class FakeDiscordObject:
    def __init__(self, object_id):
        self.id = object_id


class FakeUser:
    id = 333
    display_name = "Tester"


class FakeInteraction:
    guild = FakeDiscordObject(111)
    channel = FakeDiscordObject(222)
    user = FakeUser()


class FakeMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeFollowup:
    def __init__(self):
        self.calls = []
        self.message = FakeMessage()

    async def send(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        if kwargs.get("wait"):
            return self.message
        return None


class FakeResponse:
    def __init__(self):
        self.calls = []

    async def send_message(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})


class FakeFightInteraction(FakeInteraction):
    def __init__(self):
        self.followup = FakeFollowup()
        self.response = FakeResponse()


class DiscordCommandAuditTests(unittest.IsolatedAsyncioTestCase):
    def test_fight_embed_contains_compact_sections(self):
        embed, full_analysis = build_fight_embed(
            {
                "winner": "Spawn",
                "loser": "Godzilla",
                "confidence": "medium",
                "summary": "Spawn opened by forcing short engagements. Godzilla answered by extending pressure.",
                "loser_best_path": "Godzilla needed to keep Spawn spending necroplasm before Spawn controlled spacing.",
                "matchup_card": [
                    {
                        "name": "Spawn",
                        "key_tools": ["Necroplasm", "chains", "teleportation", "Hell King Spawn"],
                        "best_route": "Burst in and out.",
                        "risk": "limited necroplasm supply",
                    },
                    {
                        "name": "Godzilla",
                        "key_tools": ["atomic breath", "size", "durability", "raw power"],
                        "best_route": "Force a long fight.",
                        "risk": "slower adaptation",
                    },
                ],
                "deciding_factors": [
                    {
                        "factor": "Special Abilities",
                        "evidence": "Spawn brings named tools: Necroplasm, chains, teleportation",
                    }
                ],
            }
        )

        field_names = [field.name for field in embed.fields]

        self.assertEqual(embed.title, "⚔️ SPAWN VS GODZILLA")
        self.assertIn("🏆 Winner: Spawn", embed.description)
        self.assertIn("📊 Battle odds:", embed.description)
        self.assertIn("🎚️ Confidence: Medium", embed.description)
        self.assertIn("🟥 Spawn — Fight Card", field_names)
        self.assertIn("🟦 Godzilla — Fight Card", field_names)
        self.assertIn("⚖️ Quick Verdict", field_names)
        self.assertIn("🔎 Quick Evidence", field_names)
        self.assertEqual(full_analysis, "Spawn opened by forcing short engagements. Godzilla answered by extending pressure.")

    def test_confidence_colors_use_custom_theme_values(self):
        self.assertEqual(build_confidence_embed_color("strong").value, 0x10B981)
        self.assertEqual(build_confidence_embed_color("medium").value, 0xF59E0B)
        self.assertEqual(build_confidence_embed_color("low").value, 0xF97316)

    def test_fight_detail_view_exposes_three_buttons(self):
        view = FightDetailsView({"full_analysis": "a", "full_evidence": "b", "loser_best_path": "c"})

        labels = [item.label for item in view.children]

        self.assertEqual(labels, ["🧠 Full Analysis", "📜 Evidence", "🛣️ Loser's Path"])

    def test_fight_detail_payload_uses_separate_full_fields(self):
        payload = fight_detail_payload(
            {
                "winner": "Cloud",
                "loser": "Kratos",
                "confidence": "medium",
                "summary": "Full judge analysis paragraph one. Full judge analysis paragraph two.",
                "loser_best_path": "Kratos needed to force melee before Cloud controlled range.",
                "deciding_factors": [
                    {
                        "factor": "Weapon",
                        "evidence": "Cloud had Buster Sword and Limit Breaks.",
                        "tactical_effect": "Cloud could punish openings with burst damage.",
                    }
                ],
            }
        )

        self.assertIn("Full judge analysis paragraph two.", payload["full_analysis"])
        self.assertIn("Weapon: Cloud had Buster Sword", payload["full_evidence"])
        self.assertIn("less reliable", payload["loser_best_path"])
        self.assertNotEqual(payload["full_analysis"], payload["full_evidence"])
        self.assertNotEqual(payload["full_evidence"], payload["loser_best_path"])

    async def test_ephemeral_detail_chunks_are_page_labeled_and_split(self):
        interaction = FakeFightInteraction()
        text = "\n\n".join(f"Paragraph {index} has enough words to split safely." for index in range(80))

        await send_ephemeral_chunks(interaction, "Full Analysis", text)

        self.assertGreater(len(interaction.response.calls) + len(interaction.followup.calls), 1)
        self.assertIn("Full Analysis - Page 1/", interaction.response.calls[0]["args"][0])
        self.assertIn("Full Analysis - Page 2/", interaction.followup.calls[0]["args"][0])

    async def test_initial_fight_output_is_sent_before_llm_finishes(self):
        interaction = FakeFightInteraction()
        packet = {"errors": [], "contender_a": {}, "contender_b": {}}
        smoke = {
            "winner": "Sentry",
            "loser": "Wolverine",
            "confidence": "medium",
            "winner_probability": 0.65,
            "loser_probability": 0.35,
            "summary": "Sentry has the deterministic edge.",
            "win_condition": "Sentry controls range.",
            "loser_best_path": "Wolverine needed melee attrition before Sentry controlled range.",
            "matchup_card": [
                {"name": "Wolverine", "key_tools": ["Adamantium claws"], "best_route": "Force melee.", "risk": "range denial"},
                {"name": "Sentry", "key_tools": ["flight"], "best_route": "Deny melee.", "risk": "instability"},
            ],
            "deciding_factors": [{"factor": "Range", "evidence": "Sentry controls range."}],
        }
        llm_can_finish = asyncio.Event()

        async def fake_judge(packet_arg, smoke_arg):
            await llm_can_finish.wait()
            return {
                **smoke_arg,
                "summary": "Sentry opened by denying melee and finished after Wolverine could not force attrition.",
                "diagnostics": {"fallback": False, "fallback_reason": "llm_explanation"},
            }

        with patch("battlebot.bot.commands.fight.judge_fight_packet", fake_judge):
            task = asyncio.create_task(send_deferred_fight_result(interaction, packet, smoke, ephemeral=False))
            await asyncio.sleep(0)

            self.assertEqual(len(interaction.followup.calls), 1)
            self.assertEqual(interaction.followup.calls[0]["kwargs"]["embed"].title, "⚔️ WOLVERINE VS SENTRY")
            self.assertIn("Generating full referee breakdown", interaction.followup.calls[0]["kwargs"]["embed"].description)
            self.assertIsInstance(interaction.followup.calls[0]["kwargs"].get("view"), FightDetailsView)

            llm_can_finish.set()
            await task

        self.assertTrue(interaction.followup.message.edits)

    async def test_llm_timeout_preserves_deterministic_result(self):
        interaction = FakeFightInteraction()
        packet = {"errors": [], "contender_a": {}, "contender_b": {}}
        smoke = {
            "winner": "Sentry",
            "loser": "Wolverine",
            "confidence": "medium",
            "summary": "Sentry has the deterministic edge.",
            "loser_best_path": "Wolverine needed melee attrition before Sentry controlled range.",
            "matchup_card": [
                {"name": "Sentry", "key_tools": ["flight"], "best_route": "Deny melee.", "risk": "instability"},
                {"name": "Wolverine", "key_tools": ["Adamantium claws"], "best_route": "Force melee.", "risk": "range denial"},
            ],
            "deciding_factors": [],
        }

        async def fake_judge(packet_arg, smoke_arg):
            return {
                **smoke_arg,
                "diagnostics": {"fallback": True, "fallback_reason": "timeout"},
            }

        with patch("battlebot.bot.commands.fight.judge_fight_packet", fake_judge):
            await send_deferred_fight_result(interaction, packet, smoke, ephemeral=False)

        edited_embed = interaction.followup.message.edits[-1]["embed"]

        self.assertIn("Winner: Sentry", edited_embed.description)
        self.assertIn("deterministic verdict remains", edited_embed.description)

    async def test_successful_fight_command_creates_audit_entry(self):
        recorded = []

        async def handler():
            return "winner: Superman"

        async def fake_record(entry, **kwargs):
            recorded.append(entry)

        with patch("battlebot.bot.audit.record_discord_command_audit", fake_record):
            result = await audit.run_audited_command(
                FakeInteraction(),
                command_name="fight",
                options={"contender_a": "Batman", "contender_b": "Superman"},
                response_is_private=False,
                database_url="postgresql://audit-user:secret@localhost/db",
                handler=handler,
            )

        self.assertEqual(result, "winner: Superman")
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0].command_name, "fight")
        self.assertTrue(recorded[0].success)
        self.assertEqual(recorded[0].response_text, "winner: Superman")
        self.assertEqual(recorded[0].options["contender_a"], "Batman")

    async def test_failed_command_creates_audit_entry(self):
        recorded = []

        async def handler():
            raise RuntimeError("database unavailable")

        async def fake_record(entry, **kwargs):
            recorded.append(entry)

        with patch("battlebot.bot.audit.record_discord_command_audit", fake_record):
            with self.assertRaises(RuntimeError):
                await audit.run_audited_command(
                    FakeInteraction(),
                    command_name="profile",
                    options={"character": "Batman"},
                    response_is_private=True,
                    database_url=None,
                    handler=handler,
                )

        self.assertEqual(len(recorded), 1)
        self.assertFalse(recorded[0].success)
        self.assertEqual(recorded[0].error_type, "RuntimeError")
        self.assertIn("database unavailable", recorded[0].error_message)

    async def test_audit_failure_does_not_break_command_response(self):
        async def handler():
            return "search results"

        with patch(
            "battlebot.bot.audit.record_discord_command_audit",
            AsyncMock(side_effect=OSError("audit disk failed")),
        ):
            result = await audit.run_audited_command(
                FakeInteraction(),
                command_name="search",
                options={"query": "Goku"},
                response_is_private=True,
                database_url=None,
                handler=handler,
            )

        self.assertEqual(result, "search results")

    def test_token_and_database_url_are_not_present_in_fallback_log(self):
        with TemporaryDirectory() as temp_dir:
            fallback = Path(temp_dir) / "discord_command_audit.jsonl"
            with patch.dict(
                "os.environ",
                {
                    "DISCORD_TOKEN": "super-secret-token",
                    "DATABASE_URL": "postgresql://user:pass@localhost/db",
                },
                clear=False,
            ):
                audit.write_jsonl_fallback(
                    audit.DiscordCommandAuditEntry(
                        command_name="repair_queue",
                        guild_id="1",
                        channel_id="2",
                        user_id="3",
                        user_display_name="Tester",
                        options={
                            "token": "super-secret-token",
                            "database": "postgresql://user:pass@localhost/db",
                        },
                        response_text="used super-secret-token and postgresql://user:pass@localhost/db",
                        response_is_private=True,
                        success=True,
                        error_type="",
                        error_message="",
                        duration_ms=5,
                        llm_enabled=False,
                        llm_model="",
                    ),
                    path=fallback,
                )

            payload = fallback.read_text(encoding="utf-8")
            row = json.loads(payload)

        self.assertNotIn("super-secret-token", payload)
        self.assertNotIn("postgresql://user:pass@localhost/db", payload)
        self.assertIn("[REDACTED]", payload)
        self.assertEqual(row["command_name"], "repair_queue")


if __name__ == "__main__":
    unittest.main()
