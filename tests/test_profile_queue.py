import argparse
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from battlebot.review import batch_promote
from battlebot.review.queue import CLAIM_JOBS_SQL
from battlebot.review.queue_seed import seed_queue
from battlebot.review.queue_worker import process_job, run_worker


class FakeConnection:
    def __init__(self):
        self.inserted = []
        self.executed = []

    async def fetchrow(self, sql, *args):
        self.inserted.append(args)
        return {"id": len(self.inserted)}

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


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


if __name__ == "__main__":
    unittest.main()
