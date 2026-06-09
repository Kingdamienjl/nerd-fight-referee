import unittest

from battlebot.profiles.fight_packet import build_fight_packet, compact_profile


def make_item(index):
    return {
        "id": f"item-{index}",
        "name": f"Item {index}",
        "description": f"Description {index}",
        "tags": [],
        "confidence": 0.9,
    }


def profile_row(character_id, name, *, profile_hash):
    return {
        "character_id": character_id,
        "canonical_name": name,
        "franchise": "Test",
        "category": "test",
        "profile_id": character_id,
        "profile_type": "auto_evidence_profile",
        "status": "auto_generated",
        "battle_eligible": True,
        "profile_hash": profile_hash,
        "profile_json": {
            "power_scale": {
                "tier": {"text": "5-B"},
                "attack_potency": {"text": "Planet level"},
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


if __name__ == "__main__":
    unittest.main()
