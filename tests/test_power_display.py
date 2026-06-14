import unittest

from battlebot.profiles.power_display import extract_tier_tokens, public_power_scale


class PowerDisplayTests(unittest.TestCase):
    def test_cleans_template_and_wikilink_tiers(self):
        tiers = extract_tier_tokens("{{8-C}}, [[High 8-C]], [[8-B]]")

        self.assertEqual(tiers, ["8-C", "High 8-C", "8-B"])

    def test_repeated_tiers_are_deduplicated(self):
        tiers = extract_tier_tokens("{{8-C}}, [[8-C]], 8-C, [[High 8-C]], {{High 8-C}}")

        self.assertEqual(tiers, ["8-C", "High 8-C"])

    def test_high_8c_maps_to_skyscraper_buster(self):
        scale = public_power_scale("[[High 8-C]]")

        self.assertEqual(scale.damage_class, "Skyscraper-Buster")
        self.assertEqual(scale.footprint, "large building / skyscraper")
        self.assertEqual(scale.source_tier, "High 8-C")

    def test_8b_maps_to_block_buster(self):
        scale = public_power_scale("[[8-B]]")

        self.assertEqual(scale.damage_class, "Block-Buster")
        self.assertEqual(scale.footprint, "city block")
        self.assertEqual(scale.source_tier, "8-B")

    def test_high_8c_and_8b_display_damage_chain(self):
        scale = public_power_scale("[[High 8-C]], [[8-B]]")

        self.assertEqual(scale.damage_class, "Skyscraper-Buster → Block-Buster")
        self.assertEqual(scale.footprint, "large building / skyscraper → city block")
        self.assertEqual(scale.source_tier, "High 8-C → 8-B")

    def test_5b_becomes_planetary_class(self):
        scale = public_power_scale("{{5-B}}")

        self.assertEqual(scale.damage_class, "Planetary Threat")
        self.assertEqual(scale.footprint, "Planet-level")

    def test_2c_becomes_multiverse_class(self):
        scale = public_power_scale("[[2-C]]")

        self.assertEqual(scale.damage_class, "Multiversal Threat")
        self.assertEqual(scale.footprint, "multiple universes / timelines")

    def test_unknown_tier_falls_back_gracefully(self):
        scale = public_power_scale("Varies by form")

        self.assertEqual(scale.damage_class, "Unknown")
        self.assertEqual(scale.footprint, "Unknown")
        self.assertEqual(scale.source_tier, "Varies by form")


if __name__ == "__main__":
    unittest.main()
