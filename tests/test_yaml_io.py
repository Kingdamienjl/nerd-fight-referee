import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from battlebot.profiles import yaml_io
from battlebot.schemas.profile import CharacterProfile


def generated_profile() -> dict:
    return yaml.safe_load(Path("profiles/generated/anime/naruto/naruto-uzumaki.yaml").read_text(encoding="utf-8"))


class YAMLIOTests(unittest.TestCase):
    def test_multiline_wiki_fragment_dumps_and_reloads_safely(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "generated" / "anime" / "naruto" / "naruto.yaml"
            profile = generated_profile()
            fragment = "first line\n{{6-A}}\nraw wiki fragment: [[Naruto]]"
            profile.setdefault("review", {})["raw_fragment"] = fragment

            loaded = yaml_io.write_yaml(path, profile, validate=CharacterProfile.model_validate)

        self.assertEqual(loaded["review"]["raw_fragment"], fragment)

    def test_manual_corrupted_yaml_is_quarantined(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "comic" / "dc" / "bad.yaml"
            path.parent.mkdir(parents=True)
            path.write_text("name: [unterminated\n", encoding="utf-8")
            result = None

            try:
                yaml_io.load_yaml(path)
            except yaml.YAMLError as exc:
                result = yaml_io.quarantine_file(
                    path,
                    error=exc,
                    quarantine_dir=root / "profiles" / "quarantined" / "malformed_yaml",
                )
            self.assertIsNotNone(result)

            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertFalse(path.exists())
            self.assertTrue(result.quarantine_path.exists())
            self.assertEqual(report["source_path"], str(path))
            self.assertIn("error", report)

    def test_generated_profile_write_validates_after_safe_write(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profiles" / "generated" / "anime" / "naruto" / "naruto.yaml"
            profile = generated_profile()

            yaml_io.write_yaml(path, profile, validate=CharacterProfile.model_validate)
            loaded = yaml_io.load_yaml(path)

        self.assertEqual(loaded["name"], profile["name"])
        CharacterProfile.model_validate(loaded)


if __name__ == "__main__":
    unittest.main()
