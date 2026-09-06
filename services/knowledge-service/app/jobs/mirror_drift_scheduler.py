"""Scheduled glossary→KG mirror reconciliation (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER).

The detector and the repairer both exist and both are `/internal` endpoints, which means a
PERSON has to ask. The divergence that started this — 17 of 43 entities absent from the
acceptance book's graph — was found by hand, during an investigation into something else,
a day after the events were lost. Nothing would have found it otherwise, and nothing would
find the next one.

This is what runs it.

Module shape mirrors `reconcile_evidence_count_scheduler` (C14a/C14b) deliberately: same
advisory-lock idiom, same cursor-resumable sweep, same loop wrapper, so operators keep one
mental model across the service's background schedulers.

WHY IT DETECTS BUT DOES NOT REPAIR BY DEFAULT
----------------------------------------------
`KNOWLEDGE_MIRROR_AUTO_REPAIR` defaults **false**, and the argument cuts both ways.

(That env var name is load-bearing and was wrong once: this Settings class has no
`env_prefix`, so the field name IS the variable name. It read `mirror_auto_repair` while
this docstring promised `KNOWLEDGE_MIRROR_AUTO_REPAIR` — a documented switch that did not
exist, found by trying to use it. The field is `knowledge_mirror_auto_repair` now.)

  * A reconciler that only detects leaves the data broken until someone reads a log.
  * A reconciler that silently fixes MASKS the breakage that caused the drift. The mirror
    converges, the alarm never fires, and a handler that has been dropping every third
    event looks exactly like a healthy system with a diligent janitor.

The resolution is the metric, not the default: when auto-repair is on,
`glossary_mirror_repaired_total` is the alarm — a healthy system converges to ZERO repairs
per sweep, so sustained repair volume is the signal that something upstream keeps losing
events. Turning it on is a deployment decision (one env var), and until someone makes it
this sweep converts silent rot into a number that goes red, which is the actual gap.

COST, MEASURED RATHER THAN ASSUMED
-----------------------------------
Detection is one paged glossary read plus one bounded graph lookup per mirrorable entity.
Measured 2026-08-12 against a real book: **~95 ms for 43 entities** (~2 ms/entity, ~8 ms
fixed). The dev database holds 451 projects, so a full sweep is ~45 seconds. That is why
this walks per-entity through the `GraphStore` port instead of earning a bulk read: at
this cost the port change would buy nothing, and a detector bound to one engine would have
to be rewritten by the engine swap it exists to survive.

`PROJECT_CAP` bounds a single sweep anyway, and the cursor resumes the next one where this
one stopped — so a database that grows past the cap gets swept in slices instead of one
long transaction-hogging pass.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

import asyncpg

from app.db.repositories.sweeper_state import SweeperStateRepo
from app.metrics import (
    glossary_mirror_missing,
    glossary_mirror_projects_diverged,
    glossary_mirror_repaired_total,
    glossary_mirror_sweep_total,
)
from app.mirror.glossary_mirror import detect_mirror_drift

__all__ = [
    "MirrorSweepResult",
    "sweep_mirror_drift_once",
    "run_mirror_drift_loop",
    "DEFAULT_INTERVAL_S",
    "DEFAULT_STARTUP_DELAY_S",
    "PROJECT_CAP",
    "SWEEPER_NAME",
]

logger = logging.getLogger(__name__)

SWEEPER_NAME = "glossary_mirror_drift"

# Distinct from 20_310_001/002 (K20.3), 003 (K19b.8), 004 (C14a reconcile),
# 005 (quarantine) so every scheduler can run concurrently without blocking.
_MIRROR_LOCK_KEY = 20_310_006

# Six-hourly. Drift accrues at entity-write rate and the cost is seconds, so the interval
# is chosen for DETECTION LATENCY, not for load: a handler that breaks at 09:00 is visible
# by 15:00 rather than the next day.
DEFAULT_INTERVAL_S = 6 * 60 * 60
# Stagger: K20.3 uses 10/15 min, K19b.8 20, C14a 25, quarantine 30. 35 keeps every loop off
# the same boot second.
DEFAULT_STARTUP_DELAY_S = 35 * 60

# One sweep walks at most this many projects. Not a silent cap — the cursor persists, so
# the next sweep continues from here, and `projects_capped` says it happened.
PROJECT_CAP = 500

# Projects are walked oldest-id first so the cursor seek is deterministic. `$1::uuid IS
# NULL` matches everything on a fresh sweep.
_LIST_PROJECTS_SQL = """
SELECT project_id::text AS project_id, book_id::text AS book_id, user_id::text AS user_id
FROM knowledge_projects
WHERE ($1::uuid IS NULL OR project_id > $1::uuid)
  AND book_id IS NOT NULL
ORDER BY project_id
LIMIT $2
"""


@dataclass
class MirrorSweepResult:
    projects_considered: int = 0
    projects_diverged: int = 0
    missing_total: int = 0
    repaired: int = 0
    errored: int = 0
    lock_skipped: bool = False
    projects_capped: bool = False
    # Per-project detail for the log line. Bounded by PROJECT_CAP, and only the diverged
    # ones — a sweep of 451 healthy projects should say almost nothing.
    diverged: list[tuple[str, int]] = field(default_factory=list)


SessionFactory = Callable[[], Any]


async def sweep_mirror_drift_once(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    glossary_client: Any,
    *,
    auto_repair: bool = False,
    sweeper_state_repo: SweeperStateRepo | None = None,
    project_cap: int = PROJECT_CAP,
) -> MirrorSweepResult:
    """Walk every project, measure the mirror, optionally close it.

    Per-project errors are logged, counted and skipped — one unreachable book must not
    stop the sweep, or a single broken project hides the state of every other one.
    """
    result = MirrorSweepResult()

    async with pool.acquire() as conn:
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", _MIRROR_LOCK_KEY,
        )
        if not locked:
            logger.info("mirror sweep already running on another worker — skipping")
            result.lock_skipped = True
            glossary_mirror_sweep_total.labels(outcome="lock_skipped").inc()
            return result

        try:
            cursor = None
            if sweeper_state_repo is not None:
                cursor = await sweeper_state_repo.read_cursor(SWEEPER_NAME)
                if cursor is not None:
                    logger.info("mirror sweep resuming from project=%s", cursor)

            rows = await conn.fetch(_LIST_PROJECTS_SQL, cursor, project_cap)
            result.projects_considered = len(rows)
            result.projects_capped = len(rows) == project_cap

            for row in rows:
                project_id = row["project_id"]
                try:
                    async with session_factory() as session:
                        drift = await detect_mirror_drift(
                            session=session,
                            glossary_client=glossary_client,
                            project_id=UUID(project_id),
                            book_id=UUID(row["book_id"]),
                            user_id=UUID(row["user_id"]),
                        )
                    if drift is None:
                        # The truth side was unreachable. NOT zero divergence — counting
                        # it as healthy is how an outage renders as a clean sweep.
                        result.errored += 1
                        continue

                    if drift.missing:
                        result.projects_diverged += 1
                        result.missing_total += drift.missing
                        result.diverged.append((project_id, drift.missing))

                        if auto_repair:
                            repaired = await _repair(
                                glossary_client, row["book_id"], drift.missing_ids,
                            )
                            result.repaired += repaired
                            glossary_mirror_repaired_total.inc(repaired)

                    # Cursor AFTER the project is fully handled, and before the counters
                    # are trusted — same ordering argument as C14a: a failure here means
                    # we re-measure a project, which is idempotent and cheap.
                    if sweeper_state_repo is not None:
                        await sweeper_state_repo.upsert_cursor(
                            SWEEPER_NAME, UUID(project_id),
                        )
                except Exception:
                    logger.exception("mirror sweep raised for project=%s", project_id)
                    result.errored += 1
                    continue

            # A capped sweep must KEEP its cursor so the next one continues. Clearing it
            # here would restart at the beginning every time and the tail of the project
            # list would never be swept at all — a silent blind spot rather than a slow one.
            if sweeper_state_repo is not None and not result.projects_capped:
                await sweeper_state_repo.clear_cursor(SWEEPER_NAME)

            glossary_mirror_missing.set(result.missing_total)
            glossary_mirror_projects_diverged.set(result.projects_diverged)
            glossary_mirror_sweep_total.labels(outcome="completed").inc()
            if result.errored:
                glossary_mirror_sweep_total.labels(outcome="errored").inc()

            log = logger.warning if result.missing_total else logger.info
            log(
                "mirror sweep complete — projects=%d diverged=%d MISSING=%d "
                "repaired=%d errored=%d capped=%s%s",
                result.projects_considered, result.projects_diverged,
                result.missing_total, result.repaired, result.errored,
                result.projects_capped,
                # The ids, so a red metric is actionable without a second investigation.
                "".join(f"\n    project={p} missing={n}" for p, n in result.diverged),
            )
            return result
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", _MIRROR_LOCK_KEY)


async def _repair(glossary_client: Any, book_id: str, missing_ids: list[str]) -> int:
    """Hand the missing ids back to the SSOT. Returns how many it actually re-emitted.

    The count comes from glossary-service's response, NOT from `len(missing_ids)`: the
    emit path declines ids it will not emit for (soft-deleted, nameless, another book's),
    and counting the request as the result would report repairs that never happened.
    """
    response = await glossary_client.reemit_mirror(UUID(book_id), missing_ids)
    if response is None:
        # The re-emit failed. Raise so the per-project handler counts it as an error —
        # returning 0 would look like "nothing needed repairing".
        raise RuntimeError(f"mirror re-emit failed for book={book_id}")
    return int(response.get("reemitted", 0))


async def run_mirror_drift_loop(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    glossary_client: Any,
    *,
    auto_repair: bool = False,
    sweeper_state_repo: SweeperStateRepo | None = None,
    interval_s: int = DEFAULT_INTERVAL_S,
    startup_delay_s: int = DEFAULT_STARTUP_DELAY_S,
) -> None:
    """Startup-delay, sweep, sleep, repeat. Cancellation propagates so lifespan teardown
    does not leave a dangling task."""
    logger.info(
        "mirror-drift loop starting (startup_delay=%ds interval=%ds auto_repair=%s)",
        startup_delay_s, interval_s, auto_repair,
    )
    try:
        await asyncio.sleep(startup_delay_s)
        while True:
            try:
                await sweep_mirror_drift_once(
                    pool, session_factory, glossary_client,
                    auto_repair=auto_repair,
                    sweeper_state_repo=sweeper_state_repo,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("mirror sweep failed — continuing next cycle")
                glossary_mirror_sweep_total.labels(outcome="errored").inc()
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        logger.info("mirror-drift loop stopping (cancelled)")
        raise
