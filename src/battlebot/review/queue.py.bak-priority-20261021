"""PostgreSQL-backed review job queue helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any


CLAIM_JOBS_SQL = """
WITH claimed AS (
    SELECT id
    FROM profile_jobs
    WHERE status IN ('pending', 'retry')
      AND next_attempt_at <= now()
    ORDER BY priority ASC, next_attempt_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT $2
)
UPDATE profile_jobs AS job
SET status = 'running',
    attempts = job.attempts + 1,
    locked_at = now(),
    worker_id = $1,
    updated_at = now()
FROM claimed
WHERE job.id = claimed.id
RETURNING job.*
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


async def claim_jobs(connection: Any, *, worker_id: str, limit: int) -> list[dict[str, Any]]:
    async with connection.transaction():
        rows = await connection.fetch(CLAIM_JOBS_SQL, worker_id, max(1, limit))
    return [dict(row) for row in rows]


async def enqueue_job(
    connection: Any,
    *,
    profile_path: str,
    target: str,
    providers: str,
    priority: int,
    max_attempts: int = 3,
    requeue: bool = False,
) -> bool:
    # requeue=True lets a terminal job (needs_review/failed) whose inputs
    # changed be reset to 'retry' with a fresh attempt budget; without it
    # the insert stays a no-op for any existing row, exactly as before.
    row = await connection.fetchrow(
        """
INSERT INTO profile_jobs (profile_path, target, providers, priority, max_attempts)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (profile_path) DO UPDATE
SET status = 'retry',
    attempts = 0,
    locked_at = NULL,
    worker_id = NULL,
    next_attempt_at = now(),
    last_error = 'Requeued: profile changed since last attempt',
    updated_at = now()
WHERE profile_jobs.status IN ('needs_review', 'failed') AND $6
RETURNING id
""",
        profile_path,
        target,
        providers,
        priority,
        max_attempts,
        requeue,
    )
    return row is not None


async def mark_job(
    connection: Any,
    job_id: int,
    *,
    status: str,
    summary: dict[str, Any] | None = None,
    error: str | None = None,
    next_attempt_at: datetime | None = None,
) -> None:
    await connection.execute(
        """
UPDATE profile_jobs
SET status = $2,
    locked_at = NULL,
    worker_id = NULL,
    last_error = $3,
    last_summary = $4::jsonb,
    next_attempt_at = COALESCE($5, next_attempt_at),
    updated_at = now()
WHERE id = $1
""",
        job_id,
        status,
        error,
        json.dumps(summary or {}),
        next_attempt_at,
    )


def retry_backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(60, 2 ** max(0, attempts - 1)))


async def mark_retry(connection: Any, job: dict[str, Any], *, summary: dict[str, Any], error: str) -> str:
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or 3)
    if attempts >= max_attempts:
        await mark_job(connection, int(job["id"]), status="failed", summary=summary, error=error)
        return "failed"
    await mark_job(
        connection,
        int(job["id"]),
        status="retry",
        summary=summary,
        error=error,
        next_attempt_at=utc_now() + retry_backoff(attempts),
    )
    return "retry"
