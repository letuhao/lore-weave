"""C14a — scheduled quarantine-cleanup sweep.

Periodic asyncio loop that runs ``run_quarantine_cleanup`` globally
(``user_id=None``) so the K15.10 TTL-based auto-invalidator runs on a
schedule, not just on manual admin trigger.

Module shape mirrors K20.3 ``summary_regen_scheduler`` and C14a
``reconcile_evidence_count_scheduler``.

Advisory lock: a second process trying to run the sweep concurrently
bails out with ``lock_skipped=True``.

Iteration granularity: **global sweep** (single Cypher call per
sweep). ``run_quarantine_cleanup(user_id=None)`` filter already
cross-cuts all users — per-user iteration would add N round trips for
no benefit. The per-call LIMIT caps the max facts invalidated per
sweep; if the backlog exceeds the cap, the next sweep (12 hours later)
catches the remainder.

Cadence: 12h (twice-daily) — quarantine TTL is 24h per K15.10, so a
12h sweep cadence ensures every stale fact hits invalidation before
ageing past 48h. Could be daily but 12h gives reviewers a faster
signal when auto-invalidation fires on their curation backlog.

Scope (C14a):
  - Functional scheduler — create, execute, sleep, repeat
  - Cursor-state (resumable-from-mid-backlog) deferred to **C14b**
  - The natural filter ``pending_validation=true`` advances the state
    on its own (invalidated facts drop out of the filter on the next
    run), so cursor state is nice-to-have not required.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

import asyncpg

from app.jobs.quarantine_cleanup import (
    DEFAULT_TTL_HOURS,
    run_quarantine_cleanup,
)
from app.metrics import quarantine_sweep_total

__all__ = [
    "QuarantineSweepResult",
    "sweep_quarantine_once",
    "run_quarantine_loop",
    "DEFAULT_INTERVAL_S",
    "DEFAULT_STARTUP_DELAY_S",
    "DEFAULT_LIMIT_PER_SWEEP",
    "DEFAULT_MAX_DRAIN_ITERATIONS",
]

logger = logging.getLogger(__name__)

# C14a — distinct from 20_310_001/002 (K20.3) + 20_310_003 (K19b.8) +
# 20_310_004 (C14a reconcile).
_QUARANTINE_LOCK_KEY = 20_310_005

DEFAULT_INTERVAL_S = 12 * 60 * 60  # 12h — twice-daily, under 24h TTL
# 30-min startup offset stagger from K20.3 (10/15) + K19b.8 (20) +
# C14a reconcile (25) so none of the five loops burst at boot.
DEFAULT_STARTUP_DELAY_S = 30 * 60

# Per-call safety cap. At hobby scale the quarantine backlog is
# small; a 1000-row cap prevents one Cypher call holding a transaction
# too long if a large backlog accumulates (e.g. extraction burst
# without validation). Multiple calls inside one sweep drain bursts.
DEFAULT_LIMIT_PER_SWEEP = 1000

# /review-impl MED#1 — inner-loop drain cap. Each sweep loops
# `run_quarantine_cleanup` until it returns < DEFAULT_LIMIT_PER_SWEEP
# (meaning no more stale facts) OR this iteration cap fires (safety
# net against a BE regression that keeps returning the cap). 10
# iterations × 1000/call = 10k facts drained per sweep, 20k/day at
# the 12h cadence. Larger bursts split across sweeps.
DEFAULT_MAX_DRAIN_ITERATIONS = 10


# Zero-arg callable returning an async-CM wrapping a Neo4j CypherSession.
SessionFactory = Callable[[], Any]


@dataclass
class QuarantineSweepResult:
    """Aggregate stats from a single sweep (may drain multiple
    iterations internally — see /review-impl MED#1)."""

    invalidated: int = 0  # total across all drain iterations
    iterations: int = 0   # number of inner-loop drain calls
    errored: bool = False
    lock_skipped: bool = False


async def sweep_quarantine_once(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    *,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    limit: int | None = DEFAULT_LIMIT_PER_SWEEP,
    max_drain_iterations: int = DEFAULT_MAX_DRAIN_ITERATIONS,
) -> QuarantineSweepResult:
    """Run a global quarantine-cleanup sweep under an advisory lock.
    Inner-loop drains the backlog up to ``max_drain_iterations`` calls
    so bursts don't wait for the next interval cycle.

    Stop conditions:
      - ``run_quarantine_cleanup`` returns < ``limit`` (no more stale)
      - ``limit is None`` (helper already drained everything in one call)
      - ``max_drain_iterations`` fires (safety cap)
    """
    result = QuarantineSweepResult()

    async with pool.acquire() as conn:
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", _QUARANTINE_LOCK_KEY,
        )
        if not locked:
            logger.info(
                "C14a: quarantine sweep already running on another "
                "worker — skipping this cycle"
            )
            result.lock_skipped = True
            quarantine_sweep_total.labels(outcome="lock_skipped").inc()
            return result

        try:
            try:
                async with session_factory() as session:
                    # /review-impl MED#1 — drain loop: repeatedly call
                    # the helper until a call returns < limit (natural
                    # completion) or we hit the iteration cap. Each
                    # call is its own Cypher transaction at ≤ limit
                    # rows, so the per-transaction risk stays bounded.
                    while result.iterations < max_drain_iterations:
                        invalidated_this_call = await run_quarantine_cleanup(
                            session,
                            user_id=None,  # global sweep
                            ttl_hours=ttl_hours,
                            limit=limit,
                        )
                        result.iterations += 1
                        result.invalidated += invalidated_this_call
                        # Natural terminator: backlog drained OR caller
                        # passed limit=None (single-shot semantics).
                        if limit is None or invalidated_this_call < limit:
                            break
            except Exception:
                logger.exception("C14a: quarantine sweep raised")
                result.errored = True
                quarantine_sweep_total.labels(outcome="errored").inc()
                return result

            logger.info(
                "C14a: quarantine sweep complete — invalidated=%d "
                "iterations=%d ttl_hours=%d limit=%s",
                result.invalidated, result.iterations, ttl_hours,
                "none" if limit is None else str(limit),
            )
            quarantine_sweep_total.labels(outcome="completed").inc()
            return result
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock($1)", _QUARANTINE_LOCK_KEY,
            )


async def run_quarantine_loop(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    *,
    interval_s: int = DEFAULT_INTERVAL_S,
    startup_delay_s: int = DEFAULT_STARTUP_DELAY_S,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    limit: int | None = DEFAULT_LIMIT_PER_SWEEP,
    max_drain_iterations: int = DEFAULT_MAX_DRAIN_ITERATIONS,
) -> None:
    """Infinite loop: startup-delay, sweep, sleep interval, repeat.

    Mirrors K20.3 ``run_project_regen_loop`` and C14a
    ``run_reconcile_loop`` shape.
    """
    logger.info(
        "C14a: quarantine loop starting (startup_delay=%ds interval=%ds "
        "ttl_hours=%d limit=%s)",
        startup_delay_s, interval_s, ttl_hours,
        "none" if limit is None else str(limit),
    )
    try:
        await asyncio.sleep(startup_delay_s)
        while True:
            try:
                await sweep_quarantine_once(
                    pool, session_factory,
                    ttl_hours=ttl_hours, limit=limit,
                    max_drain_iterations=max_drain_iterations,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "C14a: quarantine sweep failed — continuing next cycle"
                )
                quarantine_sweep_total.labels(outcome="errored").inc()
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        logger.info("C14a: quarantine loop stopping (cancelled)")
        raise
