import unittest

from battlebot.profiles.aliases import compact_alias_key, resolve_alias


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


if __name__ == "__main__":
    unittest.main()
