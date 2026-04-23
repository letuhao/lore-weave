"""C3 (D-K19b.8-01) — job_logs retention sweep.

Periodic cron that deletes `job_logs` rows older than a retention
window (default 90 days). Keeps the table from growing unboundedly
across long-running deploys; FK CASCADE on ``extraction_jobs`` already
deletes logs when a job is deleted, so this only cleans up rows where
the parent job itself is still around (completed jobs users haven't
archived).

Module shape mirrors K20.3 ``summary_regen_scheduler``:
  - ``sweep_job_logs_once`` is the pure sweep function (pg_advisory_lock
    + DELETE with make_interval parameter + result parsing), suitable
    for unit testing with a mocked ``asyncpg.Pool``.
  - ``run_job_logs_retention_loop`` wraps it in an asyncio loop with
    startup delay + interval sleep, registered via the FastAPI
    lifespan as ``asyncio.create_task(...)``.

Advisory lock key ``20_310_003`` is sequential with K20.3's
``_001`` (project regen) + ``_002`` (global regen) so all three
background loops have distinct lock keys and can run on the same
Postgres without cross-blocking.

Cadence: daily sweep with a 20-min startup delay, offset from K20.3's
10/15-min delays so the three loops don't converge at startup.

**Platform-wide retention, not per-tenant** (/review-impl L7): the
DELETE runs cross-tenant with a single global window. Hobby-scale
Track 1 accepts this — power users wanting longer retention can
export via the `GET /v1/knowledge/extraction/jobs/{id}/logs`
endpoint inside the window. At commercial scale (paid tiers with
contractually different retention), add a ``retention_days`` column
to a per-user settings table and switch the DELETE to iterate per
user — out of C3 scope.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import asyncpg

__all__ = [
    "RetentionResult",
    "sweep_job_logs_once",
    "run_job_logs_retention_loop",
    "DEFAULT_INTERVAL_S",
    "DEFAULT_STARTUP_DELAY_S",
    "DEFAULT_RETAIN_DAYS",
]

logger = logging.getLogger(__name__)

_RETENTION_LOCK_KEY = 20_310_003

DEFAULT_INTERVAL_S = 24 * 60 * 60  # daily
DEFAULT_STARTUP_DELAY_S = 1200  # 20 min — offset from K20.3 loops
DEFAULT_RETAIN_DAYS = 90

# make_interval is the safest way to parameterize an interval without
# stringifying into the SQL (which would expose injection risk if the
# value ever became user-driven).
_DELETE_SQL = """
DELETE FROM job_logs
WHERE created_at < now() - make_interval(days => $1)
"""


@dataclass
class RetentionResult:
    """Aggregate stats from a single sweep. Mirrors
    ``summary_regen_scheduler.SweepResult`` shape so operators reading
    the logs see familiar output across background loops."""

    deleted: int = 0
    lock_skipped: bool = False


def _parse_delete_count(tag: str) -> int:
    """asyncpg's ``pool.execute``/``conn.execute`` returns the Postgres
    command tag as a string. For DELETE this is ``'DELETE N'`` where N
    is the number of rows affected. We extract the trailing int.

    Defensive: if the tag is missing or malformed (shouldn't happen in
    practice — Postgres always returns one), return 0 rather than raise.
    A sweep with a bad parse still shouldn't crash the scheduler loop.
    """
    if not tag:
        return 0
    parts = tag.split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except ValueError:
        return 0


async def sweep_job_logs_once(
    pool: asyncpg.Pool,
    *,
    retain_days: int = DEFAULT_RETAIN_DAYS,
) -> RetentionResult:
    """Run one retention sweep: acquire advisory lock, DELETE old rows,
    release lock. Returns aggregate counts.

    Lock acquisition uses ``pg_try_advisory_lock`` so a second process
    (or replica) hitting the sweep mid-run bails out with
    ``lock_skipped=True`` rather than double-deleting. Single-worker
    dev deploys always acquire the lock.

    Release happens under ``try/finally`` so even a DELETE failure
    (shouldn't happen — plain DELETE, no CHECK constraints) returns
    the lock to the pool.
    """
    result = RetentionResult()

    async with pool.acquire() as conn:
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", _RETENTION_LOCK_KEY,
        )
        if not locked:
            logger.info(
                "C3: job_logs retention sweep already running on another "
                "worker — skipping this cycle"
            )
            result.lock_skipped = True
            return result

        try:
            tag = await conn.execute(_DELETE_SQL, retain_days)
            result.deleted = _parse_delete_count(tag)
            logger.info(
                "C3: job_logs retention sweep deleted %d rows older "
                "than %d days",
                result.deleted, retain_days,
            )
            return result
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock($1)", _RETENTION_LOCK_KEY,
            )


async def run_job_logs_retention_loop(
    pool: asyncpg.Pool,
    *,
    interval_s: int = DEFAULT_INTERVAL_S,
    startup_delay_s: int = DEFAULT_STARTUP_DELAY_S,
    retain_days: int = DEFAULT_RETAIN_DAYS,
) -> None:
    """Infinite loop: startup-delay, sweep, sleep interval, repeat.

    Mirrors K20.3 ``run_project_regen_loop`` shape so operators have
    one mental model across all background schedulers.

    Cancellation: re-raise ``asyncio.CancelledError`` at each sleep /
    await boundary so FastAPI lifespan teardown sees the cancellation
    cleanly. Non-Cancelled sweep exceptions are logged + swallowed so
    one bad sweep doesn't kill the loop.
    """
    if startup_delay_s > 0:
        logger.info(
            "C3: job_logs retention loop scheduled in %ds, then every %ds",
            startup_delay_s, interval_s,
        )
        try:
            await asyncio.sleep(startup_delay_s)
        except asyncio.CancelledError:
            logger.info(
                "C3: job_logs retention loop cancelled during startup delay"
            )
            raise

    while True:
        try:
            await sweep_job_logs_once(pool, retain_days=retain_days)
        except asyncio.CancelledError:
            logger.info(
                "C3: job_logs retention loop cancelled during sweep"
            )
            raise
        except Exception:
            logger.exception(
                "C3: job_logs retention sweep errored (non-fatal) — "
                "continuing loop"
            )

        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            logger.info(
                "C3: job_logs retention loop cancelled during sleep"
            )
            raise
