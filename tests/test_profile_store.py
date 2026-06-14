import unittest

from battlebot.profiles.store import resolve_character


def profile_row(
    character_id,
    name,
    *,
    aliases=None,
    profile_hash=None,
    franchise="Test",
    status="auto_generated",
    sources=None,
    variant=None,
    battle_eligible=True,
):
    return {
        "character_id": character_id,
        "canonical_name": name,
        "franchise": franchise,
        "category": "test",
        "profile_id": character_id,
        "profile_type": "auto_evidence_profile",
        "status": status,
        "battle_eligible": battle_eligible,
        "profile_hash": profile_hash or f"hash-{character_id}",
        "profile_json": {
            "abilities": [],
            "equipment": [],
            "weaknesses": [],
            "sources": sources or [],
            "power_scale": {},
            "variant": variant or {},
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

    async def test_resolver_picks_default_sephiroth_instead_of_ambiguity(self):
        result = await resolve_character(
            FakeProfileConnection(
                [
                    profile_row("sephiroth-crossover", "Sephiroth", franchise="Crossover Icons"),
                    profile_row(
                        "sephiroth-ff7",
                        "Sephiroth",
                        franchise="Final Fantasy VII",
                        sources=[{"title": "source"}],
                        variant={"default_variant": True},
                    ),
                ]
            ),
            "sephiroth",
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["profile"]["character_id"], "sephiroth-ff7")

    async def test_resolver_rejects_unrelated_alias_when_exact_candidate_exists(self):
        result = await resolve_character(
            FakeProfileConnection(
                [
                    profile_row("son-goku", "Son Goku"),
                    profile_row("anderson", "Alexander Anderson", aliases=["goku"]),
                ]
            ),
            "goku",
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["profile"]["character_id"], "son-goku")

    async def test_resolver_goku_returns_son_goku(self):
        result = await resolve_character(
            FakeProfileConnection(
                [
                    profile_row("son-goku", "Son Goku", aliases=["Goku"], franchise="Dragon Ball"),
                    profile_row("anderson", "Alexander Anderson", aliases=["goku"], franchise="Hellsing"),
                ]
            ),
            "goku",
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["profile"]["canonical_name"], "Son Goku")

    async def test_resolver_sephiroth_prefers_final_fantasy_vii_when_no_default_flag(self):
        result = await resolve_character(
            FakeProfileConnection(
                [
                    profile_row("sephiroth-crossover", "Sephiroth", franchise="Crossover Icons", sources=[{"title": "source"}]),
                    profile_row("sephiroth-ff", "Sephiroth", franchise="Final Fantasy", sources=[{"title": "source"}]),
                    profile_row("sephiroth-ff7", "Sephiroth", franchise="Final Fantasy VII", sources=[{"title": "source"}]),
                ]
            ),
            "sephiroth",
        )

        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["profile"]["character_id"], "sephiroth-ff7")

    async def test_ambiguous_disambiguation_options_do_not_include_blank_suggestions(self):
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
        self.assertTrue(result["disambiguation_options"])
        self.assertFalse(any(", ," in option or " -  -" in option for option in result["disambiguation_options"]))


if __name__ == "__main__":
    unittest.main()
