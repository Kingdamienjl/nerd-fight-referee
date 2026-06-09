import os
import tempfile
import unittest
from pathlib import Path

import yaml

from battlebot.ingest.import_profiles import (
    ImportOptions,
    build_import_plan,
    compile_profile,
    find_profile_paths,
    import_compiled_profiles,
    validate_profile_path,
)


GENERATED_DIR = Path("profiles/generated")
GOKU_PATH = Path("profiles/generated/anime/dragon-ball/son-goku.yaml")
NARUTO_PATH = Path("profiles/generated/anime/naruto/naruto-uzumaki.yaml")


class ProfileImportCompileTests(unittest.TestCase):
    def test_import_compiler_scans_generated_yaml_files(self):
        paths = find_profile_paths(GENERATED_DIR)

        self.assertIn(GOKU_PATH, paths)
        self.assertIn(NARUTO_PATH, paths)

    def test_import_compiler_validates_goku_naruto_profiles(self):
        self.assertTrue(validate_profile_path(GOKU_PATH).battle_eligible)
        self.assertTrue(validate_profile_path(NARUTO_PATH).battle_eligible)

    def test_dry_run_reports_imports_without_db_write(self):
        compiled, summary = build_import_plan(GENERATED_DIR)

        self.assertEqual(summary.scanned, 2)
        self.assertEqual(summary.imported, 2)
        self.assertEqual(summary.skipped_invalid, 0)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(len(compiled), 2)

    def test_flatten_compile_profile_produces_expected_rows(self):
        profile = validate_profile_path(GOKU_PATH)
        compiled = compile_profile(profile, GOKU_PATH)

        self.assertEqual(compiled.character["id"], "anime-dragon-ball-son-goku")
        self.assertGreaterEqual(len(compiled.aliases), 1)
        self.assertGreaterEqual(len(compiled.sources), 1)
        self.assertGreaterEqual(len(compiled.power_scale), 9)
        self.assertGreater(len(compiled.abilities), 0)
        self.assertGreater(len(compiled.equipment), 0)
        self.assertGreater(len(compiled.weaknesses), 0)

    def test_profile_import_plan_includes_required_power_axes(self):
        profile = validate_profile_path(NARUTO_PATH)
        compiled = compile_profile(profile, NARUTO_PATH)
        axes = {row["axis"]: row for row in compiled.power_scale}

        for axis in ("attack_potency", "speed", "durability"):
            self.assertIn(axis, axes)
            self.assertTrue(axes[axis]["text"])

    def test_invalid_profile_is_skipped_unless_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "invalid.yaml"
            invalid_path.write_text(yaml.safe_dump({"name": "Invalid"}), encoding="utf-8")

            compiled, summary = build_import_plan(Path(tmpdir))
            self.assertEqual(compiled, [])
            self.assertEqual(summary.scanned, 1)
            self.assertEqual(summary.skipped_invalid, 1)

            with self.assertRaises(Exception):
                build_import_plan(Path(tmpdir), ImportOptions(fail_fast=True))

    @unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not set")
    def test_optional_postgres_import(self):
        compiled, summary = build_import_plan(GENERATED_DIR)
        self.assertEqual(summary.imported, 2)

        import asyncio

        asyncio.run(
            import_compiled_profiles(
                compiled,
                database_url=os.environ["TEST_DATABASE_URL"],
                wipe_profiles=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
