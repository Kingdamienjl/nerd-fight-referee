import unittest

from battlebot.profiles.sheet import profile_sheet


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


if __name__ == "__main__":
    unittest.main()
