import unittest

from battlebot.profiles.search import browse_character_catalog, format_character_catalog


class FakeCatalogConnection:
    def __init__(self, rows):
        self.rows = rows

    def filtered_rows(self, category, franchise):
        rows = [row for row in self.rows if row.get("battle_eligible")]
        if category:
            rows = [row for row in rows if str(row.get("category") or "").casefold() == category.casefold()]
        if franchise:
            rows = [row for row in rows if str(row.get("franchise") or "").casefold() == franchise.casefold()]
        return sorted(
            rows,
            key=lambda row: (
                str(row.get("franchise") or "").casefold(),
                str(row.get("canonical_name") or "").casefold(),
                str(row.get("character_id") or ""),
            ),
        )

    async def fetchval(self, sql, category, franchise):
        return len(self.filtered_rows(category, franchise))

    async def fetch(self, sql, category, franchise, limit, offset):
        return self.filtered_rows(category, franchise)[offset : offset + limit]


def catalog_row(index, *, category="anime", franchise="Dragon Ball", name=None):
    name = name or f"Character {index:02d}"
    return {
        "character_id": f"internal-{index:02d}",
        "canonical_name": name,
        "franchise": franchise,
        "category": category,
        "profile_id": f"profile-{index:02d}",
        "profile_json": {"name": name},
        "battle_eligible": True,
    }


class CharacterCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_page_uses_twenty_item_limit_and_metadata(self):
        connection = FakeCatalogConnection([catalog_row(index) for index in range(1, 31)])

        page = await browse_character_catalog(connection)
        text = format_character_catalog(page)

        self.assertEqual(page["limit"], 20)
        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_count"], 2)
        self.assertEqual(len(page["rows"]), 20)
        self.assertIn("Total matching characters: 30", text)
        self.assertIn("Page: 1 of 2", text)
        self.assertIn("Filters: category=all, franchise=all", text)
        self.assertIn("/characters category:anime franchise:Dragon Ball page:2", text)
        self.assertNotIn("internal-01", text)

    async def test_page_two_returns_next_catalog_slice(self):
        connection = FakeCatalogConnection([catalog_row(index) for index in range(1, 31)])

        page = await browse_character_catalog(connection, page=2)

        self.assertEqual(page["page"], 2)
        self.assertEqual(len(page["rows"]), 10)
        self.assertEqual(page["rows"][0]["canonical_name"], "Character 21")

    async def test_category_filter_limits_matches(self):
        rows = [
            catalog_row(1, category="anime", franchise="Dragon Ball", name="Son Goku"),
            catalog_row(2, category="comic", franchise="Marvel", name="Iron Man"),
        ]
        page = await browse_character_catalog(FakeCatalogConnection(rows), category="anime")
        text = format_character_catalog(page)

        self.assertEqual(page["total"], 1)
        self.assertIn("Son Goku", text)
        self.assertNotIn("Iron Man", text)
        self.assertIn("Filters: category=anime, franchise=all", text)

    async def test_franchise_filter_limits_matches(self):
        rows = [
            catalog_row(1, category="anime", franchise="Dragon Ball", name="Son Goku"),
            catalog_row(2, category="anime", franchise="Naruto", name="Naruto Uzumaki"),
        ]
        page = await browse_character_catalog(FakeCatalogConnection(rows), franchise="Dragon Ball")
        text = format_character_catalog(page)

        self.assertEqual(page["total"], 1)
        self.assertIn("Son Goku", text)
        self.assertNotIn("Naruto Uzumaki", text)
        self.assertIn("Filters: category=all, franchise=Dragon Ball", text)

    async def test_limit_is_capped_at_twenty_five(self):
        connection = FakeCatalogConnection([catalog_row(index) for index in range(1, 31)])

        page = await browse_character_catalog(connection, limit=100)

        self.assertEqual(page["limit"], 25)
        self.assertEqual(len(page["rows"]), 25)

    async def test_empty_result_message_keeps_navigation_context(self):
        page = await browse_character_catalog(FakeCatalogConnection([]), category="game", franchise="Missing")
        text = format_character_catalog(page)

        self.assertEqual(page["total"], 0)
        self.assertIn("Total matching characters: 0", text)
        self.assertIn("Page: 1 of 0", text)
        self.assertIn("Filters: category=game, franchise=Missing", text)
        self.assertIn("No characters found for these filters.", text)


if __name__ == "__main__":
    unittest.main()
