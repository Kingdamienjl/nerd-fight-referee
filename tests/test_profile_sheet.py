import unittest

from battlebot.profiles.sheet import format_profile_data, profile_sheet


class ProfileSheetTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_batman_includes_core_fields(self):
        text = await profile_sheet("Batman")

        self.assertIn("Name: Batman", text)
        self.assertIn("- Attack:", text)
        self.assertIn("- Speed:", text)
        self.assertIn("- Durability:", text)
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

    def test_variant_profile_sheet_shows_parent_and_type(self):
        text = format_profile_data(
            {
                "name": "Iron Man (Hulkbuster)",
                "franchise": "Marvel",
                "category": "comic",
                "battle_eligible": False,
                "sources": [],
                "abilities": [],
                "weaknesses": [],
                "power_scale": {},
                "variant": {
                    "parent_character_id": "comic-marvel-iron-man",
                    "variant_name": "Hulkbuster",
                    "variant_type": "armor",
                    "default_variant": False,
                    "battle_notes": "",
                },
            },
            status="roster_stub",
        )

        self.assertIn("Variant: Hulkbuster", text)
        self.assertIn("Variant Type: armor", text)
        self.assertIn("Parent: comic-marvel-iron-man", text)


if __name__ == "__main__":
    unittest.main()
