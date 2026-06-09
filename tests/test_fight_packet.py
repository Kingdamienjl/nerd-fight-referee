import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from battlebot.profiles.fight_packet import build_fight_packet, compact_profile
from battlebot.fight.debug import human_summary
from battlebot.profiles.locate import find_yaml_matches
from battlebot.profiles.quality import profile_warning_flags


def make_item(index):
    return {
        "id": f"item-{index}",
        "name": f"Item {index}",
        "description": f"Description {index}",
        "tags": [],
        "confidence": 0.9,
    }


def profile_row(
    character_id,
    name,
    *,
    profile_hash,
    franchise="Test",
    attack_potency="Planet level",
):
    return {
        "character_id": character_id,
        "canonical_name": name,
        "franchise": franchise,
        "category": "test",
        "profile_id": character_id,
        "profile_type": "auto_evidence_profile",
        "status": "auto_generated",
        "battle_eligible": True,
        "profile_hash": profile_hash,
        "profile_json": {
            "power_scale": {
                "tier": {"text": "5-B"},
                "attack_potency": {"text": attack_potency},
                "speed": {"text": "Relativistic"},
                "durability": {"text": "Planet level"},
                "range": {"text": "Planetary"},
                "stamina": {"text": "High"},
                "intelligence": {"text": "Genius"},
            },
            "abilities": [make_item(index) for index in range(20)],
            "equipment": [make_item(index) for index in range(10)],
            "weaknesses": [make_item(index) for index in range(12)],
            "sources": [{"id": f"source-{index}", "title": "Source"} for index in range(7)],
        },
        "aliases": [],
        "imported_at": None,
        "updated_at": None,
    }


class FakeProfileConnection:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, sql, *args):
        if "ILIKE" in sql:
            pattern = args[0].strip("%").lower()
            return [row for row in self.rows if pattern in row["canonical_name"].lower()]
        query = args[0]
        if "JOIN character_aliases" in sql:
            return []
        if "lower(c.canonical_name)" in sql:
            return [row for row in self.rows if row["canonical_name"].lower() == query.lower()]
        return [row for row in self.rows if row["canonical_name"] == query]


class FightPacketTests(unittest.IsolatedAsyncioTestCase):
    async def test_fight_packet_contains_both_profile_hashes(self):
        packet = await build_fight_packet(
            FakeProfileConnection(
                [
                    profile_row("goku", "Son Goku", profile_hash="hash-goku"),
                    profile_row("sephiroth", "Sephiroth", profile_hash="hash-sephiroth"),
                ]
            ),
            "Son Goku",
            "Sephiroth",
        )

        self.assertEqual(packet["errors"], [])
        self.assertEqual(packet["profile_hashes"], ["hash-goku", "hash-sephiroth"])

    async def test_fight_packet_ordered_pair_key_is_symmetric(self):
        connection = FakeProfileConnection(
            [
                profile_row("goku", "Son Goku", profile_hash="hash-goku"),
                profile_row("sephiroth", "Sephiroth", profile_hash="hash-sephiroth"),
            ]
        )

        packet_a = await build_fight_packet(connection, "Son Goku", "Sephiroth")
        packet_b = await build_fight_packet(connection, "Sephiroth", "Son Goku")

        self.assertEqual(packet_a["ordered_pair_key"], packet_b["ordered_pair_key"])

    def test_packet_respects_ability_and_weakness_limits(self):
        compact = compact_profile(
            profile_row("goku", "Son Goku", profile_hash="hash-goku"),
            ability_limit=12,
            weakness_limit=8,
            equipment_limit=8,
            source_limit=5,
        )

        self.assertEqual(len(compact["abilities"]), 12)
        self.assertEqual(len(compact["weaknesses"]), 8)
        self.assertEqual(len(compact["equipment"]), 8)
        self.assertEqual(len(compact["sources"]), 5)

    def test_goku_blocked_phrase_warning_from_preferred_override(self):
        profile = profile_row(
            "goku",
            "Son Goku",
            profile_hash="hash-goku",
            franchise="Dragon Ball",
            attack_potency="Building level",
        )

        warnings = profile_warning_flags(
            profile,
            preferred_profiles={
                "son-goku": {
                    "canonical_name": "Son Goku",
                    "required_franchise": "Dragon Ball",
                    "blocked_power_phrases": ["Building level"],
                    "status": "needs_profile_repair",
                }
            },
        )

        flags = {warning["flag"] for warning in warnings}
        self.assertIn("preferred_profile_blocked_phrase", flags)
        self.assertIn("needs_manual_review", flags)

    async def test_fight_packet_includes_warnings_but_still_builds(self):
        packet = await build_fight_packet(
            FakeProfileConnection(
                [
                    profile_row(
                        "goku",
                        "Son Goku",
                        profile_hash="hash-goku",
                        franchise="Dragon Ball",
                        attack_potency="Building level",
                    ),
                    profile_row("sephiroth", "Sephiroth", profile_hash="hash-sephiroth"),
                ]
            ),
            "Son Goku",
            "Sephiroth",
        )

        self.assertEqual(packet["errors"], [])
        self.assertEqual(packet["ordered_pair_key"], "goku::sephiroth")
        self.assertTrue(packet["contender_a"]["warnings"])
        self.assertTrue(packet["warnings"])

    def test_locate_finds_generated_path(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "comic" / "dc" / "batman.yaml"
            path.parent.mkdir(parents=True)
            path.write_text("name: Batman\n", encoding="utf-8")

            matches = find_yaml_matches("Batman", temp_dir)

        self.assertEqual(matches, [str(path)])

    def test_locate_finds_needs_review_path(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "comic" / "dc" / "superman.yaml"
            path.parent.mkdir(parents=True)
            path.write_text("name: Superman\n", encoding="utf-8")

            matches = find_yaml_matches("Superman", temp_dir)

        self.assertEqual(matches, [str(path)])

    def test_debug_not_found_summary_includes_diagnostics(self):
        summary = human_summary(
            {
                "errors": [
                    {
                        "contender": "contender_a",
                        "status": "not_found",
                        "query": "Batman",
                        "diagnostics": {
                            "generated_paths": ["profiles/generated/comic/dc/batman.yaml"],
                            "needs_review_paths": [
                                "profiles/needs_review/comic/dc/batman.yaml"
                            ],
                            "db_matches": [
                                {
                                    "canonical_name": "Batgirl",
                                    "franchise": "DC",
                                    "category": "comic",
                                }
                            ],
                        },
                    }
                ]
            }
        )

        self.assertIn("not found in DB", summary)
        self.assertIn("profiles/generated/comic/dc/batman.yaml", summary)
        self.assertIn("profiles/needs_review/comic/dc/batman.yaml", summary)
        self.assertIn("Batgirl", summary)


if __name__ == "__main__":
    unittest.main()
