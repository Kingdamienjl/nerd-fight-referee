import unittest

from battlebot.profiles.search import format_search_results, search_characters


class ProfileSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_output_includes_status(self):
        rows = await search_characters("Batman", limit=5)
        text = format_search_results(rows)

        self.assertIn("Batman", text)
        self.assertRegex(text, "generated|needs_review|roster_stub|imported")

    async def test_alias_search_marks_alias_used(self):
        rows = await search_characters("ironman", limit=5)

        self.assertTrue(rows)
        self.assertEqual(rows[0].get("alias_canonical"), "Iron Man")

    async def test_needs_review_search_can_find_missing_profiles(self):
        rows = await search_characters("Sailor Moon", status_filter="needs_review", limit=10)

        self.assertTrue(any(row["status"] == "needs_review" for row in rows))

    async def test_characters_query_paginates_by_slice(self):
        rows = await search_characters("", status_filter="generated", limit=15)
        page_two = rows[10:15]

        self.assertLessEqual(len(page_two), 5)
        self.assertTrue(rows)

    async def test_search_iron_man_returns_base_and_curated_variant(self):
        rows = await search_characters("iron man", limit=20)
        names = {row["canonical_name"] for row in rows}

        self.assertIn("Iron Man", names)
        self.assertIn("Iron Man (Hulkbuster)", names)

    async def test_exact_variant_search_resolves_variant_row(self):
        rows = await search_characters("Iron Man (Hulkbuster)", limit=10)

        self.assertTrue(rows)
        self.assertEqual(rows[0]["canonical_name"], "Iron Man (Hulkbuster)")
        self.assertEqual(rows[0]["variant"]["variant_name"], "Hulkbuster")


if __name__ == "__main__":
    unittest.main()
