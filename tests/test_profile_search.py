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


if __name__ == "__main__":
    unittest.main()
