import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

from battlebot.review import auto_repair, batch_promote, service


def write_profile(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def generated_fixture_as_review() -> dict:
    data = yaml.safe_load(Path("profiles/generated/anime/naruto/naruto-uzumaki.yaml").read_text(encoding="utf-8"))
    data["profile_type"] = "needs_review"
    data["status"] = "needs_review"
    data["battle_eligible"] = False
    data["generation"]["confidence"] = 0.35
    data["generation"]["ineligible_reasons"] = ["needs_review"]
    data["repair"] = {"source_attempts": []}
    return data


def args_for(root: Path, *, dry_run=False, keep_review_copy=False, max_attempts=3) -> argparse.Namespace:
    needs_review = root / "profiles" / "needs_review"
    return argparse.Namespace(
        target=needs_review,
        max_profiles=0,
        dry_run=dry_run,
        overwrite=False,
        move=False,
        needs_review_dir=needs_review,
        generated_dir=root / "profiles" / "generated",
        review_archive_dir=root / "profiles" / "review_archive",
        quarantine_dir=root / "profiles" / "quarantined",
        keep_review_copy=keep_review_copy,
        max_attempts=max_attempts,
        roster_dir=root / "profiles" / "rosters",
        notes_path=root / "profiles" / "review_notes.yaml",
        source_timeout_seconds=1.0,
        verbose=False,
        debug_dir=root / "data" / "repair_debug",
        max_source_candidates=1,
        providers="vsbattles",
        fetch_in_dry_run=False,
    )


async def promoted_repair(path: Path, **kwargs):
    generated = service.destination_for(path, kwargs["needs_review_dir"], kwargs["generated_dir"])
    profile = generated_fixture_as_review()
    profile["profile_type"] = "auto_evidence_profile"
    profile["status"] = "provisional"
    profile["battle_eligible"] = True
    profile["generation"]["confidence"] = 0.60
    profile["generation"]["ineligible_reasons"] = []
    profile.pop("repair", None)
    service.write_yaml(generated, profile)
    attempt = auto_repair.SourceAttempt(
        "source-1",
        "https://vsbattles.fandom.com/wiki/Naruto_Uzumaki",
        True,
        "ok",
        ["attack_potency", "speed", "durability", "powers_and_abilities"],
        normalized_page_title="Naruto Uzumaki",
        fetch_status="fetched",
        provider_id="vsbattles",
        authority="high",
        promotion_allowed=True,
        identity_match=True,
        core_field_count=3,
        ability_count=1,
    )
    return auto_repair.RepairResult(
        path=path,
        changed=True,
        promoted=True,
        repaired_fields=["attack_potency", "speed", "durability", "abilities"],
        unresolved_fields=[],
        source_attempts=[attempt],
    )


class BatchPromoteTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_promotion_archives_review_file_by_default(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "anime" / "naruto" / "naruto-uzumaki.yaml"
            write_profile(path, generated_fixture_as_review())
            args = args_for(root)

            with patch("battlebot.review.enrich_sources.enrich_path"), patch(
                "battlebot.review.auto_repair.repair_profile",
                promoted_repair,
            ):
                summary = await batch_promote.batch_promote(args)

            archive = root / "profiles" / "review_archive" / "anime" / "naruto" / "naruto-uzumaki.yaml"
            source_exists = path.exists()
            archive_exists = archive.exists()

        self.assertEqual(summary.promoted, 1)
        self.assertEqual(summary.provisional, 1)
        self.assertEqual(summary.archived, 1)
        self.assertFalse(source_exists)
        self.assertTrue(archive_exists)

    async def test_keep_review_copy_preserves_needs_review_file(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "anime" / "naruto" / "naruto-uzumaki.yaml"
            write_profile(path, generated_fixture_as_review())
            args = args_for(root, keep_review_copy=True)

            with patch("battlebot.review.enrich_sources.enrich_path"), patch(
                "battlebot.review.auto_repair.repair_profile",
                promoted_repair,
            ):
                summary = await batch_promote.batch_promote(args)
            source_exists = path.exists()

        self.assertEqual(summary.promoted, 1)
        self.assertEqual(summary.archived, 0)
        self.assertTrue(source_exists)

    async def test_dry_run_does_not_archive(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "anime" / "naruto" / "naruto-uzumaki.yaml"
            write_profile(path, generated_fixture_as_review())
            args = args_for(root, dry_run=True)

            with patch("battlebot.review.auto_repair.repair_profile", promoted_repair):
                summary = await batch_promote.batch_promote(args)
            source_exists = path.exists()

        self.assertEqual(summary.promoted, 1)
        self.assertEqual(summary.archived, 0)
        self.assertTrue(source_exists)

    async def test_three_deterministic_failures_quarantine_profile(self):
        async def broken_repair(*args, **kwargs):
            raise AttributeError("'NoneType' object has no attribute 'get'")

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "anime" / "naruto" / "naruto-uzumaki.yaml"
            profile = generated_fixture_as_review()
            profile["repair"] = {"attempts": 2}
            write_profile(path, profile)
            args = args_for(root)

            with patch("battlebot.review.enrich_sources.enrich_path"), patch(
                "battlebot.review.auto_repair.repair_profile",
                broken_repair,
            ):
                summary = await batch_promote.batch_promote(args)

            quarantine = root / "profiles" / "quarantined" / "anime" / "naruto" / "naruto-uzumaki.yaml"
            quarantine_exists = quarantine.exists()

        self.assertEqual(summary.quarantined, 1)
        self.assertEqual(summary.deterministic_failures, 1)
        self.assertTrue(quarantine_exists)

    async def test_transient_failure_is_retryable(self):
        async def broken_repair(*args, **kwargs):
            raise TimeoutError("timeout")

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "anime" / "naruto" / "naruto-uzumaki.yaml"
            write_profile(path, generated_fixture_as_review())
            args = args_for(root)

            with patch("battlebot.review.enrich_sources.enrich_path"), patch(
                "battlebot.review.auto_repair.repair_profile",
                broken_repair,
            ):
                summary = await batch_promote.batch_promote(args)
            source_exists = path.exists()

        self.assertEqual(summary.retry, 1)
        self.assertEqual(summary.retryable_failures, 1)
        self.assertTrue(source_exists)


if __name__ == "__main__":
    unittest.main()
