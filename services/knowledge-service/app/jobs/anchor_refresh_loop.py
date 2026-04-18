"""K13.1 — background loop that wakes once per day to refresh anchor scores.

Wraps `refresh_anchor_scores` in an asyncio loop that sleeps for
`interval_s` (default 24h) between runs. Designed to be started from
the FastAPI lifespan as a `asyncio.create_task(...)` background task,
mirroring the K14 event consumer pattern in `app/main.py`.

Shutdown: cancelling the task raises `asyncio.CancelledError` from the
sleep, which this loop handles cleanly so lifespan teardown doesn't
emit a traceback.

Failure handling: the job itself already per-project-isolates errors
via its `projects_failed` counter. The loop additionally catches any
unexpected exception at the sweep level, logs it, bumps the `error`
outcome metric, and sleeps until the next cycle — one bad night
shouldn't prevent tomorrow's run.
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from app.jobs.compute_anchor_score import SessionFactory, refresh_anchor_scores
from app.metrics import anchor_refresh_runs_total

__all__ = ["run_anchor_refresh_loop", "DEFAULT_INTERVAL_S", "DEFAULT_STARTUP_DELAY_S"]

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 24 * 60 * 60  # 24h
DEFAULT_STARTUP_DELAY_S = 300  # 5 min — let the service warm up before first run


async def run_anchor_refresh_loop(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    *,
    interval_s: int = DEFAULT_INTERVAL_S,
    startup_delay_s: int = DEFAULT_STARTUP_DELAY_S,
) -> None:
    """Infinite loop: sleep, refresh, repeat.

    Args:
        pool: asyncpg pool (advisory-lock scope)
        session_factory: zero-arg callable returning an async-CM
            wrapping a CypherSession, per-project-fresh
        interval_s: seconds between refreshes; default 24h
        startup_delay_s: seconds to wait before the first run; default
            5 min so the service is warm and migrations are done
    """
    if startup_delay_s > 0:
        logger.info(
            "K13.1: anchor-refresh loop scheduled in %ds, then every %ds",
            startup_delay_s, interval_s,
        )
        try:
            await asyncio.sleep(startup_delay_s)
        except asyncio.CancelledError:
            logger.info("K13.1: anchor-refresh loop cancelled during startup delay")
            raise

    while True:
        try:
            result = await refresh_anchor_scores(pool, session_factory)
            outcome = "lock_skipped" if result.lock_skipped else "ok"
            anchor_refresh_runs_total.labels(outcome=outcome).inc()
            logger.info(
                "K13.1: refresh outcome=%s processed=%d updated=%d failed=%d",
                outcome,
                result.projects_processed,
                result.entities_updated,
                result.projects_failed,
            )
        except asyncio.CancelledError:
            logger.info("K13.1: anchor-refresh loop cancelled during run")
            raise
        except Exception:
            anchor_refresh_runs_total.labels(outcome="error").inc()
            logger.exception("K13.1: anchor-refresh loop run errored (non-fatal)")

        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            logger.info("K13.1: anchor-refresh loop cancelled during sleep")
            raise
