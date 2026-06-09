import os
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from battlebot.ingest.import_profiles import (
    ImportOptions,
    build_import_plan,
    compile_profile,
    find_profile_paths,
    profile_file_fingerprint,
    import_compiled_profiles,
    update_import_state_for_compiled,
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

        self.assertGreaterEqual(summary.scanned, 2)
        self.assertGreaterEqual(summary.imported, 2)
        self.assertEqual(summary.skipped_invalid, 0)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(len(compiled), summary.imported)

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

    def test_changed_only_importer_imports_new_files(self):
        state = {"profiles": {}}

        compiled, summary = build_import_plan(
            GOKU_PATH,
            ImportOptions(changed_only=True, import_state=state),
        )

        self.assertEqual(summary.scanned, 1)
        self.assertEqual(summary.changed, 1)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(summary.skipped_unchanged, 0)
        self.assertEqual(len(compiled), 1)

    def test_changed_only_importer_skips_unchanged_files(self):
        profile = validate_profile_path(GOKU_PATH)
        compiled = [compile_profile(profile, GOKU_PATH)]
        state = {"profiles": {}}
        update_import_state_for_compiled(state, compiled)

        compiled_again, summary = build_import_plan(
            GOKU_PATH,
            ImportOptions(changed_only=True, import_state=state),
        )

        self.assertEqual(compiled_again, [])
        self.assertEqual(summary.changed, 0)
        self.assertEqual(summary.skipped_unchanged, 1)

    def test_changed_only_importer_reimports_changed_profile_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "son-goku.yaml"
            shutil.copy2(GOKU_PATH, path)
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            state = {
                "profiles": {
                    path.as_posix(): profile_file_fingerprint(path, data["profile_hash"]),
                }
            }
            data["profile_hash"] = "changed-profile-hash"
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

            compiled, summary = build_import_plan(
                path,
                ImportOptions(changed_only=True, import_state=state),
            )

            self.assertEqual(summary.changed, 1)
            self.assertEqual(summary.imported, 1)
            self.assertEqual(compiled[0].profile["profile_hash"], "changed-profile-hash")

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
