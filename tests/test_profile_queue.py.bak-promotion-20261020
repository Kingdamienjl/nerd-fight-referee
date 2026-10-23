import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import yaml

from battlebot.review import batch_promote
from battlebot.review.queue import CLAIM_JOBS_SQL
from battlebot.review.requeue_source_choice import SOURCE_CHOICE_FILTER_SQL, requeue_needs_human_source_choice
from battlebot.review.queue_seed import seed_queue
from battlebot.review.queue_worker import process_job, run_worker


class FakeConnection:
    def __init__(self):
        self.inserted = []
        self.executed = []
        self.fetch_values = []

    async def fetchrow(self, sql, *args):
        self.inserted.append(args)
        return {"id": len(self.inserted)}

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchval(self, sql, *args):
        self.executed.append((sql, args))
        return self.fetch_values.pop(0) if self.fetch_values else 0


def write_profile(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("name: Test\n", encoding="utf-8")


def worker_args(root: Path, *, import_every=5):
    return argparse.Namespace(
        worker_id="worker-1",
        limit=10,
        import_every=import_every,
        sleep_seconds=0.0,
        database_url=None,
        overwrite=False,
        move=False,
        needs_review_dir=root / "profiles" / "needs_review",
        generated_dir=root / "profiles" / "generated",
        review_archive_dir=root / "profiles" / "review_archive",
        quarantine_dir=root / "profiles" / "quarantined",
        keep_review_copy=False,
        max_attempts=3,
        roster_dir=root / "profiles" / "rosters",
        notes_path=root / "profiles" / "review_notes.yaml",
        source_timeout_seconds=1.0,
        verbose=False,
        debug_dir=root / "data" / "repair_debug",
        max_source_candidates=1,
    )


def job(path: Path, *, attempts=1, max_attempts=3):
    return {
        "id": 1,
        "profile_path": str(path),
        "target": str(path),
        "providers": "vsbattles",
        "attempts": attempts,
        "max_attempts": max_attempts,
    }


class ProfileQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_seed_skips_generated_and_archive_outputs(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            needs = root / "profiles" / "needs_review"
            generated = root / "profiles" / "generated"
            archive = root / "profiles" / "review_archive"
            seed_path = needs / "anime" / "x" / "seed.yaml"
            generated_path = needs / "anime" / "x" / "done.yaml"
            archived_path = needs / "anime" / "x" / "archived.yaml"
            write_profile(seed_path)
            write_profile(generated_path)
            write_profile(archived_path)
            write_profile(generated / "anime" / "x" / "done.yaml")
            write_profile(archive / "anime" / "x" / "archived.yaml")
            connection = FakeConnection()

            summary = await seed_queue(
                connection,
                target=needs,
                providers="vsbattles",
                priority=50,
                needs_review_dir=needs,
                generated_dir=generated,
                review_archive_dir=archive,
            )

        self.assertEqual(summary.scanned, 3)
        self.assertEqual(summary.seeded, 1)
        self.assertEqual(summary.skipped_existing_output, 2)
        self.assertEqual(len(connection.inserted), 1)
        self.assertEqual(connection.inserted[0][0], str(seed_path))

    def test_claim_query_uses_skip_locked(self):
        self.assertIn("FOR UPDATE SKIP LOCKED", CLAIM_JOBS_SQL)
        self.assertIn("LIMIT $2", CLAIM_JOBS_SQL)

    async def test_worker_marks_promoted(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "a.yaml"
            connection = FakeConnection()
            summary = batch_promote.BatchSummary(promoted=1)

            with patch("battlebot.review.queue_worker.batch_promote.batch_promote", AsyncMock(return_value=summary)):
                status = await process_job(connection, job(path), worker_args(root))

        self.assertEqual(status, "promoted")
        self.assertEqual(connection.executed[-1][1][1], "promoted")

    async def test_worker_retries_transient_failure(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "a.yaml"
            connection = FakeConnection()

            with patch(
                "battlebot.review.queue_worker.batch_promote.batch_promote",
                AsyncMock(side_effect=TimeoutError("timeout")),
            ):
                status = await process_job(connection, job(path, attempts=1, max_attempts=3), worker_args(root))

        self.assertEqual(status, "retry")
        self.assertEqual(connection.executed[-1][1][1], "retry")

    async def test_worker_fails_deterministic_failure_after_max_attempts(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "a.yaml"
            connection = FakeConnection()

            with patch(
                "battlebot.review.queue_worker.batch_promote.batch_promote",
                AsyncMock(side_effect=ValueError("bad profile")),
            ):
                status = await process_job(connection, job(path, attempts=3, max_attempts=3), worker_args(root))

        self.assertEqual(status, "failed")
        self.assertEqual(connection.executed[-1][1][1], "failed")

    async def test_worker_quarantines_yaml_parse_failure_without_retry(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "a.yaml"
            path.parent.mkdir(parents=True)
            path.write_text("name: [unterminated\n", encoding="utf-8")
            connection = FakeConnection()

            with patch(
                "battlebot.review.queue_worker.batch_promote.batch_promote",
                AsyncMock(side_effect=yaml.YAMLError("bad yaml")),
            ):
                status = await process_job(connection, job(path, attempts=1, max_attempts=3), worker_args(root))

        self.assertEqual(status, "quarantined")
        self.assertEqual(connection.executed[-1][1][1], "quarantined")
        self.assertFalse(path.exists())

    async def test_import_is_called_after_promotion_threshold(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            connection = FakeConnection()
            jobs = [
                job(root / "profiles" / "needs_review" / "a.yaml"),
                {**job(root / "profiles" / "needs_review" / "b.yaml"), "id": 2},
            ]
            summary = batch_promote.BatchSummary(promoted=1)

            with patch("battlebot.review.queue_worker.claim_jobs", AsyncMock(return_value=jobs)), patch(
                "battlebot.review.queue_worker.batch_promote.batch_promote",
                AsyncMock(return_value=summary),
            ), patch(
                "battlebot.review.queue_worker.import_generated_profiles",
                AsyncMock(return_value=2),
            ) as imported:
                result = await run_worker(connection, worker_args(root, import_every=2))

        self.assertEqual(result.promoted, 2)
        self.assertEqual(result.imported, 2)
        imported.assert_awaited_once()

    async def test_requeue_source_choice_updates_only_matching_needs_review_jobs(self):
        connection = FakeConnection()
        connection.fetch_values = [3, 3]

        result = await requeue_needs_human_source_choice(
            connection,
            providers="vsbattles",
            priority=5,
        )

        self.assertEqual(result.matched, 3)
        self.assertEqual(result.requeued, 3)
        update_sql, update_args = connection.executed[-1]
        self.assertIn("needs_human_source_choice", update_sql)
        self.assertIn("status = 'needs_review'", update_sql)
        self.assertIn("last_summary", update_sql)
        self.assertIn("top_missing_fields", update_sql)
        self.assertIn("failure_reasons", update_sql)
        self.assertNotIn("error_code", update_sql)
        self.assertNotIn("attempts =", update_sql)
        self.assertIn("position('/user-requests/' in profile_path) = 0", update_sql)
        self.assertIn("/profiles/quarantined/", update_sql)
        self.assertIn("last_error = NULL", update_sql)
        self.assertEqual(update_args, ("vsbattles", 5))

    async def test_requeue_source_choice_dry_run_does_not_update(self):
        connection = FakeConnection()
        connection.fetch_values = [2]

        result = await requeue_needs_human_source_choice(connection, dry_run=True)

        self.assertEqual(result.matched, 2)
        self.assertEqual(result.requeued, 0)
        self.assertEqual(len(connection.executed), 1)

    def test_requeue_source_choice_filter_excludes_runtime_skeleton_and_quarantine_paths(self):
        self.assertIn("profile_path LIKE 'profiles/needs_review/%'", SOURCE_CHOICE_FILTER_SQL)
        self.assertNotIn("error_code", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("last_summary", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("top_missing_fields", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("failure_reasons", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("last_summary::text LIKE '%needs_human_source_choice%'", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("position('/user-requests/' in profile_path) = 0", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("target NOT ILIKE '%user request%'", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("position('/profiles/quarantined/' in profile_path) = 0", SOURCE_CHOICE_FILTER_SQL)

    def test_requeue_source_choice_filter_does_not_touch_unrelated_needs_review_jobs(self):
        self.assertIn("status = 'needs_review'", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("needs_human_source_choice", SOURCE_CHOICE_FILTER_SQL)
        self.assertIn("last_summary", SOURCE_CHOICE_FILTER_SQL)

    async def test_user_request_skeleton_job_is_not_auto_promoted(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "profiles" / "needs_review" / "mixed" / "user-requests" / "homelander.yaml"
            connection = FakeConnection()
            summary = batch_promote.BatchSummary(promoted=1)

            with patch("battlebot.review.queue_worker.batch_promote.batch_promote", AsyncMock(return_value=summary)):
                status = await process_job(connection, job(path), worker_args(root))

        self.assertEqual(status, "needs_review")
        update_sql, update_args = connection.executed[-1]
        self.assertIn("UPDATE profile_jobs", update_sql)
        self.assertEqual(update_args[1], "needs_review")
        self.assertEqual(update_args[2], "user_request_skeleton_schema_incomplete")


if __name__ == "__main__":
    unittest.main()
