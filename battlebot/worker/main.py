"""Persistent, single-consumer profile repair and promotion worker."""
import asyncio
import json
import logging
import os

from battlebot.common.db import apply_schema, connect_database
from battlebot.review import queue_seed, queue_worker

LOCK_ID = 73190601
LOG = logging.getLogger(__name__)


async def run() -> None:
    args = queue_worker.build_arg_parser().parse_args([
        "--limit", "1", "--import-every", "1", "--max-attempts", "5", "--overwrite",
        "--source-timeout-seconds", "15", "--sleep-seconds", "2",
    ])
    seed = queue_seed.build_arg_parser().parse_args(["--max-attempts", "5"])
    interval = max(10, int(os.getenv("REFEREE_WORKER_INTERVAL", "60")))
    async with connect_database(args.database_url) as connection:
        await apply_schema(connection)
        if not await connection.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_ID):
            raise RuntimeError("Another persistent referee worker owns the queue")
        # The global session lock means no other supervised consumer is active.
        # Recover interrupted jobs, preserving attempt limits and retry history.
        await connection.execute("""
            UPDATE profile_jobs SET
              status=CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'retry' END,
              locked_at=NULL, worker_id=NULL, next_attempt_at=now(), updated_at=now(),
              last_error='Recovered interrupted worker job'
            WHERE status='running'
        """)
        while True:
            summary = await queue_seed.seed_queue(
                connection, target=seed.target, providers=seed.providers,
                priority=seed.priority, needs_review_dir=seed.needs_review_dir,
                generated_dir=seed.generated_dir, review_archive_dir=seed.review_archive_dir,
                max_attempts=5,
            )
            LOG.info("seed %s", json.dumps(summary.as_dict()))
            result = await queue_worker.run_worker(connection, args)
            LOG.info("repair %s", json.dumps(result.as_dict()))
            await asyncio.sleep(2 if result.claimed else interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
