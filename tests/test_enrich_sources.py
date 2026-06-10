import unittest

from battlebot.review import enrich_sources


def profile(name: str, franchise: str, category: str, aliases=None):
    return {
        "name": name,
        "franchise": franchise,
        "category": category,
        "aliases": aliases or [],
        "sources": [],
    }


class EnrichSourcesTests(unittest.TestCase):
    def test_iron_man_gets_marvel_candidates(self):
        data, added, _ = enrich_sources.enrich_profile_sources(
            profile("Iron Man", "Marvel", "comic", ["Tony Stark"])
        )
        titles = {source["title"] for source in data["sources"]}

        self.assertGreater(added, 0)
        self.assertIn("Iron Man", titles)
        self.assertIn("Iron Man (Marvel Comics)", titles)
        self.assertIn("Iron Man (Earth-616)", titles)
        self.assertNotIn("Iron Man (DC Comics)", titles)

    def test_cloud_strife_gets_game_candidates(self):
        data, _, _ = enrich_sources.enrich_profile_sources(
            profile("Cloud Strife", "Final Fantasy", "game")
        )
        titles = {source["title"] for source in data["sources"]}

        self.assertIn("Cloud Strife", titles)
        self.assertIn("Cloud Strife (Final Fantasy)", titles)
        self.assertIn("Cloud Strife (Game)", titles)
        self.assertNotIn("Cloud Strife (Marvel Comics)", titles)
        self.assertNotIn("Cloud Strife (DC Comics)", titles)

    def test_anime_profile_does_not_get_comic_variants(self):
        data, _, _ = enrich_sources.enrich_profile_sources(
            profile("Son Goku", "Dragon Ball", "anime", ["Goku"])
        )
        titles = {source["title"] for source in data["sources"]}

        self.assertIn("Son Goku", titles)
        self.assertIn("Son Goku (Dragon Ball)", titles)
        self.assertNotIn("Son Goku (Marvel Comics)", titles)
        self.assertNotIn("Son Goku (DC Comics)", titles)

    def test_dc_profile_does_not_get_marvel_variants(self):
        data, _, _ = enrich_sources.enrich_profile_sources(profile("Batman", "DC", "comic"))
        titles = {source["title"] for source in data["sources"]}

        self.assertIn("Batman (DC Comics)", titles)
        self.assertIn("Batman (Prime Earth)", titles)
        self.assertNotIn("Batman (Marvel Comics)", titles)

    def test_duplicates_are_not_added(self):
        data = profile("Iron Man", "Marvel", "comic")
        data["sources"] = [enrich_sources.source_candidate("vsbattles", "Iron Man")]

        _, added, skipped = enrich_sources.enrich_profile_sources(data)

        keys = [(source["provider_id"], source["title"]) for source in data["sources"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(skipped, 1)
        self.assertGreater(added, 0)

    def test_source_candidates_are_internal_only(self):
        data, _, _ = enrich_sources.enrich_profile_sources(profile("Iron Man", "Marvel", "comic"))
        source = data["sources"][0]

        self.assertEqual(source["source_type"], "mediawiki")
        self.assertEqual(source["authority"], "high")
        self.assertEqual(source["notes"], "enrich_sources_candidate")
        self.assertIn(source["provider_id"], {"vsbattles", "character_stats_profiles"})
        self.assertIn("fandom.com/wiki/Iron_Man", source["url"])
        self.assertNotIn("revision_id", source)


if __name__ == "__main__":
    unittest.main()
