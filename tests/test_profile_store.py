import unittest

from battlebot.profiles.store import resolve_character


def profile_row(character_id, name, *, aliases=None, profile_hash=None):
    return {
        "character_id": character_id,
        "canonical_name": name,
        "franchise": "Test",
        "category": "test",
        "profile_id": character_id,
        "profile_type": "auto_evidence_profile",
        "status": "auto_generated",
        "battle_eligible": True,
        "profile_hash": profile_hash or f"hash-{character_id}",
        "profile_json": {
            "abilities": [],
            "equipment": [],
            "weaknesses": [],
            "sources": [],
            "power_scale": {},
        },
        "aliases": aliases or [],
        "imported_at": None,
        "updated_at": None,
    }


class FakeProfileConnection:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, sql, *args):
        query = args[0]
        eligible_only = args[1]
        rows = [
            row
            for row in self.rows
            if not eligible_only or row.get("battle_eligible", False)
        ]
        if "JOIN character_aliases" in sql:
            normalized = query
            return [
                row
                for row in rows
                if normalized in {alias.casefold() for alias in row.get("aliases", [])}
            ]
        if "lower(c.canonical_name)" in sql:
            return [row for row in rows if row["canonical_name"].lower() == query.lower()]
        return [row for row in rows if row["canonical_name"] == query]


class ProfileStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolving_exact_name(self):
        result = await resolve_character(
            FakeProfileConnection([profile_row("goku", "Son Goku")]),
            "Son Goku",
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["matched_by"], "canonical_exact")

    async def test_resolving_case_insensitive_name(self):
        result = await resolve_character(
            FakeProfileConnection([profile_row("goku", "Son Goku")]),
            "son goku",
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["matched_by"], "canonical_case_insensitive")

    async def test_resolving_alias(self):
        result = await resolve_character(
            FakeProfileConnection([profile_row("goku", "Son Goku", aliases=["Goku"])]),
            "goku",
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["matched_by"], "alias")

    async def test_unresolved_character(self):
        result = await resolve_character(FakeProfileConnection([]), "Missing")

        self.assertEqual(result["status"], "not_found")

    async def test_ambiguous_character(self):
        result = await resolve_character(
            FakeProfileConnection(
                [
                    profile_row("akira-one", "Akira"),
                    profile_row("akira-two", "Akira"),
                ]
            ),
            "Akira",
        )

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(result["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
