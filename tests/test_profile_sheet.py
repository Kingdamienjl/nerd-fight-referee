import unittest

from battlebot.profiles.sheet import format_profile_data, profile_sheet


class ProfileSheetTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_batman_includes_core_fields(self):
        text = await profile_sheet("Batman")

        self.assertIn("Name: Batman", text)
        self.assertIn("Damage Class:", text)
        self.assertIn("Footprint:", text)
        self.assertIn("Source Tier:", text)
        self.assertIn("Attack summary:", text)
        self.assertIn("Speed summary:", text)
        self.assertIn("Durability summary:", text)
        self.assertIn("Source-backed:", text)
        self.assertIn("Source count:", text)

    async def test_profile_sheet_for_alias(self):
        text = await profile_sheet("superman")

        self.assertIn("Name: Superman", text)
        self.assertIn("Source count:", text)
        self.assertNotIn("Sources:", text)
        self.assertNotIn("provider=", text)
        self.assertNotIn(" rev=", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)

    def test_profile_sheet_public_power_scale_cleans_raw_tier_markup(self):
        text = format_profile_data(
            {
                "name": "Form Fighter",
                "franchise": "Example",
                "category": "anime",
                "battle_eligible": True,
                "sources": [{"url": "https://example.invalid/source"}],
                "abilities": [{"name": "[[Power Strike]]", "description": "{{8-B}} force"}],
                "weaknesses": [],
                "power_scale": {
                    "tier": {"text": "{{Varies}}, [[High 8-C]], [[8-B]]"},
                    "attack_potency": {"text": "Large building to [[8-B]] strikes"},
                    "speed": {"text": "[[Supersonic]]"},
                    "durability": {"text": "{{High 8-C}} armor"},
                },
            },
            status="imported",
        )

        self.assertIn("Damage Class: Skyscraper-Buster → Block-Buster", text)
        self.assertIn("Footprint: large building / skyscraper → city block", text)
        self.assertIn("Source Tier: High 8-C → 8-B", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("}}", text)
        self.assertNotIn("[[", text)
        self.assertNotIn("]]", text)
        self.assertNotIn("https://", text)


if __name__ == "__main__":
    unittest.main()
