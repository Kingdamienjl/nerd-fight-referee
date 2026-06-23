import unittest

from battlebot.profiles.aliases import compact_alias_key, resolve_alias
from battlebot.profiles.variants import split_variant_name, variant_metadata


class AliasTests(unittest.TestCase):
    def test_ironman_variants_resolve_to_iron_man(self):
        for query in ("ironman", "iron-man", "iron man", "Tony Stark"):
            self.assertEqual(resolve_alias(query).canonical, "Iron Man")

    def test_sailor_moon_resolves_to_usagi(self):
        self.assertEqual(resolve_alias("sailor moon").canonical, "Usagi Tsukino")

    def test_requested_obvious_aliases_resolve(self):
        cases = {
            "thor": "Thor",
            "hulk": "Hulk",
            "wolverine": "Wolverine",
            "flash": "The Flash",
            "green lantern": "Green Lantern",
            "wonder woman": "Wonder Woman",
            "doom slayer": "Doom Slayer",
            "dante": "Dante",
            "vergil": "Vergil",
            "samus": "Samus Aran",
            "link": "Link",
        }
        for query, canonical in cases.items():
            with self.subTest(query=query):
                self.assertEqual(resolve_alias(query).canonical, canonical)

    def test_hyphen_and_space_compact_equivalent(self):
        self.assertEqual(compact_alias_key("iron-man"), compact_alias_key("iron man"))

    def test_curated_variant_metadata(self):
        parent, variant = split_variant_name("Iron Man (Hulkbuster)")

        self.assertEqual(parent, "Iron Man")
        self.assertEqual(variant, "Hulkbuster")
        self.assertEqual(variant_metadata("Iron Man (Hulkbuster)")["variant_type"], "armor")


if __name__ == "__main__":
    unittest.main()

def test_dragon_ball_form_variants_are_curated():
    from battlebot.profiles.variants import variant_metadata, variant_search_queries

    frieza = variant_metadata("Frieza (Final Form)")
    assert frieza["variant_name"] == "Final Form"
    assert frieza["variant_type"] == "form"

    goku = variant_metadata("Son Goku (Super Saiyan Blue Kaioken)")
    assert goku["variant_name"] == "Super Saiyan Blue Kaioken"
    assert goku["variant_type"] == "form"

    queries = variant_search_queries("Frieza (Golden)", "Dragon Ball")
    assert "Frieza Golden" in queries
    assert "Frieza Golden Dragon Ball" in queries

