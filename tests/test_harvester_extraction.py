import unittest

from battlebot.harvest.auto_profile_harvester import (
    RosterRow,
    build_profile,
    extract_vsbattles_fields,
)


class HarvesterExtractionTests(unittest.TestCase):
    def test_pipe_field_extraction(self):
        fields = extract_vsbattles_fields(
            """
            | Tier = 4-B
            | AP = Solar System level
            | Speed = Massively FTL+
            | Durability = Solar System level
            | P&A = Flight, Ki Manipulation
            """
        )
        self.assertEqual(fields["tier"], "4-B")
        self.assertEqual(fields["attack_potency"], "Solar System level")
        self.assertEqual(fields["powers_and_abilities"], "Flight, Ki Manipulation")

    def test_bold_label_extraction(self):
        fields = extract_vsbattles_fields(
            "'''Attack Potency''': Planet level\n'''Speed''': Relativistic"
        )
        self.assertEqual(fields["attack_potency"], "Planet level")
        self.assertEqual(fields["speed"], "Relativistic")

    def test_plain_label_extraction(self):
        fields = extract_vsbattles_fields("Durability: City level\nWeakness: Fire")
        self.assertEqual(fields["durability"], "City level")
        self.assertEqual(fields["weaknesses"], "Fire")

    def test_section_heading_extraction(self):
        fields = extract_vsbattles_fields(
            """
            == Powers and Abilities ==
            Magic, teleportation, summoning
            == Standard Equipment ==
            Sword and shield
            """
        )
        self.assertIn("summoning", fields["powers_and_abilities"])
        self.assertEqual(fields["standard_equipment"], "Sword and shield")

    def test_ineligible_profile_has_generation_reasons(self):
        profile = build_profile(
            row=RosterRow(category="anime", franchise="Test", name="No Fields"),
            anilist_identity=None,
            igdb_identity=None,
            wiki_source={
                "fields": {},
                "revision_id": "123",
                "revision_timestamp": "2026-01-01T00:00:00Z",
                "source_id": "src",
                "title": "No Fields",
                "full_url": "https://example.com",
                "page_id": "1",
                "retrieved_at": "2026-01-01T00:00:00Z",
                "cache_key": "cache",
            },
            errors=[],
        )
        self.assertFalse(profile["battle_eligible"])
        self.assertEqual(profile["profile_type"], "needs_review")
        self.assertEqual(profile["status"], "needs_review")
        self.assertTrue(profile["generation"]["ineligible_reasons"])


if __name__ == "__main__":
    unittest.main()
