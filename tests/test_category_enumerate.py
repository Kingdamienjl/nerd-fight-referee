import json
import unittest

from battlebot.harvest.category_enumerate import (
    dedupe_rows,
    fetch_category_members,
    filter_members,
    is_candidate_title,
    roster_rows,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload


class CategoryEnumerateTests(unittest.TestCase):
    def test_is_candidate_title(self):
        self.assertTrue(is_candidate_title("Gon Freecss"))
        self.assertTrue(is_candidate_title("Abomination (Marvel Comics)"))
        self.assertTrue(is_candidate_title("007"))
        self.assertFalse(is_candidate_title(""))
        self.assertFalse(is_candidate_title("   "))
        self.assertFalse(is_candidate_title("User blog:Arkenis/HXH - Netero Slaps Pitou"))
        self.assertFalse(is_candidate_title("File:SomeImage.png"))
        self.assertFalse(is_candidate_title("Category:Marvel Characters"))
        self.assertFalse(is_candidate_title("Son Goku (Canon, Dragon Ball Z)/ObberGobb"))
        self.assertFalse(is_candidate_title("Marvel Comics", exclude=("Marvel Comics",)))
        self.assertTrue(is_candidate_title("Marvel Comics"))

    def test_filter_members_dedupes_and_filters(self):
        titles = ["Gon Freecss", "gon freecss", "User blog:X/Y", "Killua Zoldyck", "Killua Zoldyck"]
        self.assertEqual(filter_members(titles), ["Gon Freecss", "Killua Zoldyck"])

    def test_fetch_category_members_follows_continue(self):
        pages = [
            {"query": {"categorymembers": [{"title": "A"}, {"title": "B"}]}, "continue": {"cmcontinue": "tok1"}},
            {"query": {"categorymembers": [{"title": "C"}]}},
        ]
        calls = []

        def opener(request):
            calls.append(request.full_url)
            return FakeResponse(pages[len(calls) - 1])

        self.assertEqual(fetch_category_members("Marvel_Comics", opener=opener), ["A", "B", "C"])
        self.assertNotIn("cmcontinue", calls[0])
        self.assertIn("cmcontinue=tok1", calls[1])

    def test_roster_rows(self):
        rows = roster_rows("anime", "Hunter x Hunter", ["Gon Freecss", "JoJo's Bizarre Adventure"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["category"], "anime")
        self.assertEqual(rows[0]["franchise"], "Hunter x Hunter")
        self.assertEqual(rows[0]["name"], "Gon Freecss")
        self.assertEqual(rows[0]["wiki_title"], "Gon Freecss")
        self.assertEqual(rows[0]["wiki_url"], "https://vsbattles.fandom.com/wiki/Gon_Freecss")
        self.assertEqual(rows[0]["aliases"], "")
        # Apostrophes are percent-encoded in the URL.
        self.assertEqual(
            rows[1]["wiki_url"],
            "https://vsbattles.fandom.com/wiki/JoJo%27s_Bizarre_Adventure",
        )

    def test_dedupe_rows(self):
        rows = roster_rows("anime", "Hunter x Hunter", ["Gon Freecss", "Killua Zoldyck", "Meruem"])
        existing = {("anime", "hunter x hunter", "gon freecss")}
        db_names = {"killua zoldyck"}
        kept = dedupe_rows(rows, existing, db_names)
        self.assertEqual([row["name"] for row in kept], ["Meruem"])


if __name__ == "__main__":
    unittest.main()
