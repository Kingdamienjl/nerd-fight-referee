import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from battlebot.review import auto_repair, source_registry
from battlebot.review.providers import comicvine, kaggle_superherodb, powerlisting, superherodb
from tests.test_auto_repair import fake_fetch_source_fields, profile_data, write_profile


FIXTURE_DIR = Path("tests/fixtures/providers")


class SourceRegistryTests(unittest.IsolatedAsyncioTestCase):
    def test_registry_loads_providers(self):
        providers = source_registry.load_registry()

        self.assertIn("vsbattles", providers)
        self.assertEqual(providers["vsbattles"].authority, "high")

    def test_disabled_providers_are_skipped(self):
        providers = source_registry.enabled_providers(["kaggle_superherodb", "vsbattles"])

        self.assertIn("vsbattles", providers)
        self.assertNotIn("kaggle_superherodb", providers)

    def test_allowed_fields_blocks_unsupported_writes(self):
        provider = source_registry.load_registry()["powerlisting"]
        fields = {
            "attack_potency": "Planet level",
            "powers_and_abilities": "Flight",
            "ability_definitions": "Flight is movement through air.",
        }

        filtered = source_registry.filter_allowed_fields(fields, provider)

        self.assertEqual(filtered, {"ability_definitions": "Flight is movement through air."})

    async def test_low_authority_source_cannot_promote_alone(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            profile = profile_data(missing_core=True)
            profile["sources"] = [
                {
                    "id": "powerlisting-batman",
                    "title": "Batman",
                    "url": "https://powerlisting.fandom.com/wiki/Batman",
                    "source_type": "mediawiki",
                    "provider_id": "powerlisting",
                }
            ]
            write_profile(path, profile)

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    provider_ids=["powerlisting"],
                    max_source_candidates=1,
                )

        self.assertFalse(result.promoted)
        self.assertFalse(result.source_attempts[0].promotion_allowed)

    async def test_high_authority_source_can_promote_when_blockers_are_gone(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "profiles"
            needs_review = root / "needs_review"
            generated = root / "generated"
            path = needs_review / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                result = await auto_repair.repair_profile(
                    path,
                    promote_if_valid=True,
                    needs_review_dir=needs_review,
                    generated_dir=generated,
                    notes_path=root / "review_notes.yaml",
                    provider_ids=["vsbattles"],
                    max_source_candidates=1,
                )

        self.assertTrue(result.promoted)
        self.assertEqual(result.source_attempts[0].authority, "high")

    def test_character_stats_profiles_provider_generates_mediawiki_candidates(self):
        providers = source_registry.enabled_providers(["character_stats_profiles"])
        candidates = source_registry.provider_candidates(profile_data(missing_core=True), providers)

        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["provider_id"], "character_stats_profiles")
        self.assertIn("character-stats-and-profiles.fandom.com", candidates[0]["url"])

    def test_character_stats_profile_sample_uses_battle_stat_parser(self):
        fields = auto_repair.parse_source_content((FIXTURE_DIR / "character_stats_profile_sample.wikitext").read_text())

        self.assertEqual(fields["attack_potency"], "Solar System level")
        self.assertEqual(fields["speed"], "Massively FTL+")
        self.assertEqual(fields["durability"], "Solar System level")

    def test_powerlisting_cannot_write_attack_potency(self):
        provider = source_registry.load_registry()["powerlisting"]
        fields = source_registry.filter_allowed_fields(
            {"attack_potency": "Planet level", **powerlisting.parse_ability_taxonomy("Flight definition")},
            provider,
        )

        self.assertNotIn("attack_potency", fields)
        self.assertIn("ability_definitions", fields)

    def test_kaggle_adapter_skips_cleanly_when_dataset_missing(self):
        with TemporaryDirectory() as temp_dir:
            fields, metadata = kaggle_superherodb.load_local_fields("Batman", Path(temp_dir) / "missing")

        self.assertEqual(fields, {})
        self.assertEqual(metadata["note"], "local_dataset_missing")

    def test_kaggle_adapter_extracts_sample_aliases_and_stats(self):
        fields, metadata = kaggle_superherodb.load_local_fields("Batman", FIXTURE_DIR)

        self.assertEqual(metadata["note"], "ok")
        self.assertIn("Dark Knight", fields["aliases"])
        self.assertIn("intelligence: 100", fields["stat_notes"])

    def test_superherodb_parser_extracts_sample_powers(self):
        fields = superherodb.parse_superherodb_html((FIXTURE_DIR / "superherodb_batman.html").read_text())

        self.assertIn("Bruce Wayne", fields["aliases"])
        self.assertIn("Detective Skills", fields["powers_and_abilities"])
        self.assertIn("Intelligence: 100", fields["stat_notes"])

    def test_comicvine_adapter_reports_missing_api_key_cleanly(self):
        with patch.dict("os.environ", {}, clear=True):
            fields, metadata = comicvine.missing_api_key_metadata()

        self.assertEqual(fields, {})
        self.assertEqual(metadata["note"], "missing_api_key_env: COMICVINE_API_KEY")

    async def test_debug_report_records_provider_authority(self):
        with TemporaryDirectory() as temp_dir:
            debug_dir = Path(temp_dir) / "debug"
            path = Path(temp_dir) / "profiles" / "needs_review" / "comic" / "dc" / "batman.yaml"
            write_profile(path, profile_data(missing_core=True))

            with patch("battlebot.review.auto_repair.fetch_source_fields", fake_fetch_source_fields):
                await auto_repair.repair_profile(
                    path,
                    debug_dir=debug_dir,
                    notes_path=Path(temp_dir) / "notes.yaml",
                    provider_ids=["vsbattles"],
                    max_source_candidates=1,
                )
            report = yaml.safe_load((debug_dir / "batman.json").read_text(encoding="utf-8"))

        self.assertEqual(report["source_attempts"][0]["provider_id"], "vsbattles")
        self.assertEqual(report["source_attempts"][0]["authority"], "high")
        self.assertTrue(report["source_attempts"][0]["promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
