"""C14a — scheduled per-user evidence-count reconciliation.

Periodic asyncio loop that walks every non-archived user and calls
``reconcile_evidence_count`` so the K11.9 drift safety net runs on a
schedule, not just on manual admin trigger.

Module shape mirrors K20.3 ``summary_regen_scheduler``:
  - ``sweep_reconcile_once`` is the pure sweep function (easy to
    unit-test with mocked collaborators)
  - ``run_reconcile_loop`` wraps the sweep in an infinite asyncio loop
    with startup delay + interval sleep, registered from the FastAPI
    lifespan as ``asyncio.create_task(...)``.

Advisory lock: a second process (or a replica) trying to run the sweep
concurrently bails out with ``lock_skipped=True`` rather than
double-reconciling every user. Single-worker dev deploys always take
the lock.

/review-impl MED#2 (pre-existing K20.3 pattern) — ``pg_try_advisory_lock``
locks at the SESSION level, held until ``pg_advisory_unlock`` or
session termination. The ``async with pool.acquire() as conn`` idiom
uses a pooled connection; if an exception bypasses the ``finally``
(hard process crash, SIGKILL), the connection returns to the pool
with the lock still held on that session. Next caller who reuses
the same pool connection would observe the lock as "already held"
from their own session. Normal ``try/finally`` handles exceptions
reliably; only non-graceful shutdown exposes this. In practice
process termination also closes the Postgres backend session, which
implicitly releases all its advisory locks — so the edge is narrow.
Shared with K20.3 summary_regen_scheduler, K19b.8 retention loop.

Iteration granularity: per-user (not per-project). The K11.9 helper
already iterates the three labels (Entity, Event, Fact) inside a single
call; passing ``project_id=None`` reconciles all of a user's projects
in one call, one round trip for the whole tenant.

Scope (C14a):
  - Functional scheduler — create, execute, sleep, repeat
  - Cursor-state (resumable-from-mid-user) deferred to **C14b**

Behaviour contract:
  - per-user reconcile returns ``ReconcileResult`` with per-label
    counts — we aggregate into sweep totals
  - per-user errors logged + counted (``errored``) + skipped — one
    bad user doesn't poison the whole sweep
  - missing Neo4j connection at sweep start: the lifespan guard in
    ``main.py`` gates this loop on ``settings.neo4j_uri``, so we never
    enter the sweep without a working session factory
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

import asyncpg

from app.jobs.reconcile_evidence_count import (
    ReconcileResult,
    reconcile_evidence_count,
)
from app.metrics import reconcile_sweep_total

__all__ = [
    "ReconcileSweepResult",
    "sweep_reconcile_once",
    "run_reconcile_loop",
    "DEFAULT_INTERVAL_S",
    "DEFAULT_STARTUP_DELAY_S",
]

logger = logging.getLogger(__name__)

# C14a — distinct from 20_310_001/002 (K20.3) + 20_310_003 (K19b.8).
_RECONCILE_LOCK_KEY = 20_310_004

DEFAULT_INTERVAL_S = 24 * 60 * 60  # daily — drift accrues at fact-creation rate
# 25-min startup offset stagger from K20.3 (10/15) + K19b.8 (20) so
# none of the four loops burst at the same boot second.
DEFAULT_STARTUP_DELAY_S = 25 * 60


# /review-impl LOW#4 — no `is_archived = false` filter, unlike K20.3
# which gates on it to avoid regen $ cost. Reconciler fixes cached
# counter drift (no LLM, no $ cost); archived projects still have
# drift-prone :Entity/:Event/:Fact nodes that silently corrupt if
# un-archived later. Cover every user who ever had a project.
_LIST_USERS_SQL = """
SELECT DISTINCT user_id::text AS user_id
FROM knowledge_projects
ORDER BY user_id
"""


@dataclass
class ReconcileSweepResult:
    """Aggregate stats from a single sweep. Mirrors
    K20.3 ``SweepResult`` so operators see familiar shape across the
    five background schedulers."""

    users_considered: int = 0
    entities_fixed: int = 0
    events_fixed: int = 0
    facts_fixed: int = 0
    errored: int = 0
    lock_skipped: bool = False


# Zero-arg callable returning an async-CM wrapping a Neo4j CypherSession.
SessionFactory = Callable[[], Any]


async def sweep_reconcile_once(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
) -> ReconcileSweepResult:
    """Iterate every non-archived user and fire a reconcile for each.
    Returns aggregate counts for logging + metrics.

    Concurrent-run safety via ``pg_try_advisory_lock``. A second
    process hitting the sweep while the first holds the lock returns
    immediately with ``lock_skipped=True``.

    Per-user errors are logged + counted (``errored``) + skipped — one
    bad user doesn't poison the whole sweep.
    """
    result = ReconcileSweepResult()

    async with pool.acquire() as conn:
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", _RECONCILE_LOCK_KEY,
        )
        if not locked:
            logger.info(
                "C14a: reconcile sweep already running on another "
                "worker — skipping this cycle"
            )
            result.lock_skipped = True
            reconcile_sweep_total.labels(outcome="lock_skipped").inc()
            return result

        try:
            rows = await conn.fetch(_LIST_USERS_SQL)
            result.users_considered = len(rows)

            for row in rows:
                user_id = row["user_id"]
                try:
                    async with session_factory() as session:
                        reconcile_result: ReconcileResult = (
                            await reconcile_evidence_count(
                                session,
                                user_id=user_id,
                                project_id=None,
                                limit_per_label=None,
                            )
                        )
                    # Direct attribute access — if K11.9's ReconcileResult
                    # Pydantic model renames a field, this crashes loudly
                    # at sweep time instead of silently reporting 0.
                    # Safer than getattr() which would mask schema drift.
                    result.entities_fixed += reconcile_result.entities_fixed
                    result.events_fixed += reconcile_result.events_fixed
                    result.facts_fixed += reconcile_result.facts_fixed
                except Exception:
                    logger.exception(
                        "C14a: reconcile_evidence_count raised user=%s",
                        user_id,
                    )
                    result.errored += 1
                    continue

            logger.info(
                "C14a: reconcile sweep complete — users=%d "
                "entities_fixed=%d events_fixed=%d facts_fixed=%d "
                "errored=%d",
                result.users_considered,
                result.entities_fixed,
                result.events_fixed,
                result.facts_fixed,
                result.errored,
            )
            reconcile_sweep_total.labels(outcome="completed").inc()
            if result.errored:
                reconcile_sweep_total.labels(outcome="errored").inc()
            return result
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock($1)", _RECONCILE_LOCK_KEY,
            )


async def run_reconcile_loop(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    *,
    interval_s: int = DEFAULT_INTERVAL_S,
    startup_delay_s: int = DEFAULT_STARTUP_DELAY_S,
) -> None:
    """Infinite loop: startup-delay, sweep, sleep interval, repeat.

    Mirrors K20.3 ``run_project_regen_loop`` shape so operators have
    one mental model for "background scheduler" across the service.

    Cancellation: re-raise ``asyncio.CancelledError`` at each sleep /
    await boundary so FastAPI lifespan teardown sees the cancellation
    and exits cleanly without a dangling background task.
    """
    logger.info(
        "C14a: reconcile loop starting (startup_delay=%ds interval=%ds)",
        startup_delay_s, interval_s,
    )
    try:
        await asyncio.sleep(startup_delay_s)
        while True:
            try:
                await sweep_reconcile_once(pool, session_factory)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Sweep-level unhandled errors shouldn't take down the
                # scheduler. Log + sleep + retry on the next cycle.
                logger.exception(
                    "C14a: reconcile sweep failed — continuing next cycle"
                )
                reconcile_sweep_total.labels(outcome="errored").inc()
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        logger.info("C14a: reconcile loop stopping (cancelled)")
        raise
