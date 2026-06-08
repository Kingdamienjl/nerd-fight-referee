import copy
import unittest

from pydantic import ValidationError

from battlebot.harvest.auto_profile_harvester import RosterRow, build_profile
from battlebot.schemas.profile import CharacterProfile


def valid_profile_dict():
    return build_profile(
        row=RosterRow(category="anime", franchise="Test", name="Valid Fighter"),
        anilist_identity=None,
        igdb_identity=None,
        wiki_source={
            "fields": {
                "tier": "5-B",
                "attack_potency": "Planet level",
                "speed": "Relativistic",
                "durability": "Planet level",
                "powers_and_abilities": "Flight, energy projection",
                "standard_equipment": "Staff",
                "weaknesses": "Requires focus",
            },
            "revision_id": "123",
            "revision_timestamp": "2026-01-01T00:00:00Z",
            "source_id": "mediawiki-123",
            "title": "Valid Fighter",
            "full_url": "https://example.com/wiki/Valid_Fighter",
            "page_id": "1",
            "retrieved_at": "2026-01-01T00:00:00Z",
            "cache_key": "cache",
        },
        errors=[],
    )


class ProfileSchemaTests(unittest.TestCase):
    def test_profile_schema_accepts_generated_profile(self):
        profile = valid_profile_dict()

        validated = CharacterProfile.model_validate(profile)

        self.assertTrue(validated.battle_eligible)
        self.assertEqual(validated.power_scale.attack_potency.text, "Planet level")

    def test_power_scale_requires_nested_text_shape(self):
        profile = valid_profile_dict()
        profile["power_scale"]["attack_potency"] = "Planet level"

        with self.assertRaises(ValidationError):
            CharacterProfile.model_validate(profile)

    def test_battle_eligible_requires_core_fields(self):
        profile = valid_profile_dict()
        profile["power_scale"]["attack_potency"]["text"] = None

        with self.assertRaisesRegex(ValidationError, "missing_attack_potency"):
            CharacterProfile.model_validate(profile)

    def test_battle_eligible_requires_non_empty_abilities(self):
        profile = valid_profile_dict()
        profile["abilities"] = []

        with self.assertRaisesRegex(ValidationError, "missing_powers_and_abilities"):
            CharacterProfile.model_validate(profile)

    def test_ineligible_profile_requires_reasons(self):
        profile = copy.deepcopy(valid_profile_dict())
        profile["battle_eligible"] = False
        profile["profile_type"] = "needs_review"
        profile["status"] = "needs_review"
        profile["generation"]["ineligible_reasons"] = []

        with self.assertRaisesRegex(ValidationError, "ineligible profile requires"):
            CharacterProfile.model_validate(profile)


if __name__ == "__main__":
    unittest.main()
