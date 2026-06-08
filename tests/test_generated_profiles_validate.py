import unittest
from pathlib import Path

import yaml

from battlebot.schemas.profile import CharacterProfile


class GeneratedProfilesValidateTests(unittest.TestCase):
    def validate_profile(self, path: str):
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return CharacterProfile.model_validate(data)

    def test_generated_goku_profile_validates(self):
        profile = self.validate_profile("profiles/generated/anime/dragon-ball/son-goku.yaml")

        self.assertTrue(profile.battle_eligible)
        self.assertTrue(profile.power_scale.attack_potency.text)
        self.assertTrue(profile.power_scale.speed.text)
        self.assertTrue(profile.power_scale.durability.text)
        self.assertGreater(len(profile.abilities), 0)

    def test_generated_naruto_profile_validates(self):
        profile = self.validate_profile("profiles/generated/anime/naruto/naruto-uzumaki.yaml")

        self.assertTrue(profile.battle_eligible)
        self.assertTrue(profile.power_scale.attack_potency.text)
        self.assertTrue(profile.power_scale.speed.text)
        self.assertTrue(profile.power_scale.durability.text)
        self.assertGreater(len(profile.abilities), 0)


if __name__ == "__main__":
    unittest.main()
