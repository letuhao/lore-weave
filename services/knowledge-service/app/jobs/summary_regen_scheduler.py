"""K20.3 — scheduled project-summary regeneration.

Periodic asyncio loop that walks every non-archived, extraction-
enabled project and calls ``regenerate_project_summary`` per-project
so drift-prevention rules + similarity + user-edit lock + guardrails
all run on a schedule, not just on manual user trigger.

Module shape mirrors K13.1 ``anchor_refresh_loop``:
  - ``sweep_projects_once`` is the pure sweep function (easy to unit
    test with mocked collaborators)
  - ``run_project_regen_loop`` wraps the sweep in an infinite asyncio
    loop with startup delay + interval sleep, registered from the
    FastAPI lifespan as ``asyncio.create_task(...)``.

Advisory lock: a second process (or a replica) trying to run the
sweep concurrently bails out with ``lock_skipped=True`` rather than
double-regenerating every project. Single-worker dev deploys always
take the lock.

Model resolution: scheduled regen has no caller to supply
``model_ref``. For each project we look up the most recent completed
extraction job and reuse its ``llm_model``. Projects that never ran
extraction are skipped (``no_model`` outcome) because we can't pick a
BYOK model out of thin air.

Scope (Cycle α):
  - Project summary regen (L1) only
  - Global summary regen (L0) deferred to Cycle β — needs a cross-
    project model-resolution story

Behaviour contract matrix:
  - regen helper → ``regenerated``         : counted as ``regenerated``
  - regen helper → ``no_op_similarity``    : counted as ``no_op``
  - regen helper → ``no_op_empty_source``  : counted as ``no_op``
  - regen helper → ``no_op_guardrail``     : counted as ``no_op``
  - regen helper → ``user_edit_lock``      : counted as ``skipped`` (expected)
  - regen helper → ``regen_concurrent_edit``: counted as ``skipped``
  - Unhandled exception                    : counted as ``errored``
  - Project has no ``llm_model`` anywhere  : counted as ``no_model``
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import UUID

import asyncpg

from app.clients.provider_client import ProviderClient
from app.db.repositories.summaries import SummariesRepo
from app.jobs.regenerate_summaries import regenerate_project_summary

__all__ = [
    "SweepResult",
    "sweep_projects_once",
    "run_project_regen_loop",
    "DEFAULT_INTERVAL_S",
    "DEFAULT_STARTUP_DELAY_S",
]

logger = logging.getLogger(__name__)

# Distinct from K13.1 anchor-refresh's `_REFRESH_LOCK_KEY` so the two
# schedulers don't block each other.
_PROJECT_REGEN_LOCK_KEY = 20_310_001

DEFAULT_INTERVAL_S = 24 * 60 * 60  # daily
DEFAULT_STARTUP_DELAY_S = 600  # 10 min — warm-up buffer past K13.1's 5


_LIST_PROJECTS_SQL = """
SELECT user_id::text   AS user_id,
       project_id::text AS project_id
FROM knowledge_projects
WHERE is_archived = false
  AND extraction_enabled = true
ORDER BY user_id, project_id
"""

# Read the last successful extraction_job for the project and reuse
# its ``llm_model`` as the regen model. This is the cheapest
# model-resolution story we can ship for α; a later cycle can move
# to a dedicated ``project.regen_model`` column or user-preference
# lookup if the pattern proves fragile.
_LATEST_LLM_MODEL_SQL = """
SELECT llm_model
FROM extraction_jobs
WHERE user_id = $1 AND project_id = $2 AND status = 'complete'
ORDER BY completed_at DESC NULLS LAST, created_at DESC
LIMIT 1
"""


@dataclass
class SweepResult:
    """Aggregate stats from a single sweep. Mirrors K13.1
    ``RefreshResult`` so operators reading the logs see familiar
    shape across the two schedulers."""

    projects_considered: int = 0
    regenerated: int = 0
    no_op: int = 0
    skipped: int = 0  # user_edit_lock / regen_concurrent_edit
    no_model: int = 0
    errored: int = 0
    lock_skipped: bool = False


# The session_factory parameter is a zero-arg callable returning an
# async-CM wrapping a Neo4j CypherSession — same contract as K13.1.
SessionFactory = Callable[[], Any]


async def sweep_projects_once(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    provider_client: ProviderClient,
    summaries_repo: SummariesRepo,
) -> SweepResult:
    """Iterate every non-archived + extraction-enabled project and
    fire a regen for each. Returns aggregate counts for logging.

    Concurrent-run safety via ``pg_try_advisory_lock``. A second
    process hitting the sweep while the first holds the lock returns
    immediately with ``lock_skipped=True``.

    Per-project errors are logged + counted (``errored``) + skipped
    — one bad project doesn't poison the whole sweep. The regen
    helper's own no-op paths (similarity, empty source, guardrail)
    fold into the ``no_op`` counter; the user-edit-lock + concurrent-
    edit races fold into ``skipped`` because they represent "we
    intentionally didn't regenerate this one".
    """
    result = SweepResult()

    async with pool.acquire() as conn:
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", _PROJECT_REGEN_LOCK_KEY,
        )
        if not locked:
            logger.info(
                "K20.3: project regen sweep already running on another "
                "worker — skipping this cycle"
            )
            result.lock_skipped = True
            return result

        try:
            rows = await conn.fetch(_LIST_PROJECTS_SQL)
            result.projects_considered = len(rows)
            for row in rows:
                user_id = row["user_id"]
                project_id = row["project_id"]
                try:
                    llm_model = await conn.fetchval(
                        _LATEST_LLM_MODEL_SQL, UUID(user_id), UUID(project_id),
                    )
                except Exception:
                    logger.exception(
                        "K20.3: model lookup failed user=%s project=%s",
                        user_id, project_id,
                    )
                    result.errored += 1
                    continue
                if llm_model is None:
                    logger.info(
                        "K20.3: skip user=%s project=%s — no prior "
                        "extraction job to borrow a model from",
                        user_id, project_id,
                    )
                    result.no_model += 1
                    continue
                try:
                    regen = await regenerate_project_summary(
                        user_id=UUID(user_id),
                        project_id=UUID(project_id),
                        model_source="user_model",
                        model_ref=llm_model,
                        pool=pool,
                        session_factory=session_factory,
                        provider_client=provider_client,
                        summaries_repo=summaries_repo,
                    )
                except Exception:
                    logger.exception(
                        "K20.3: regenerate_project_summary raised "
                        "user=%s project=%s",
                        user_id, project_id,
                    )
                    result.errored += 1
                    continue

                status = regen.status
                if status == "regenerated":
                    result.regenerated += 1
                elif status in {
                    "no_op_similarity",
                    "no_op_empty_source",
                    "no_op_guardrail",
                }:
                    result.no_op += 1
                elif status in {"user_edit_lock", "regen_concurrent_edit"}:
                    result.skipped += 1
                else:
                    # Defensive: unknown status from a future helper
                    # update lands here and gets counted so we notice
                    # via logs + metrics instead of silently dropping.
                    logger.warning(
                        "K20.3: unrecognized regen status=%s user=%s project=%s",
                        status, user_id, project_id,
                    )
                    result.errored += 1
            logger.info(
                "K20.3: project regen sweep complete — "
                "considered=%d regenerated=%d no_op=%d skipped=%d "
                "no_model=%d errored=%d",
                result.projects_considered,
                result.regenerated,
                result.no_op,
                result.skipped,
                result.no_model,
                result.errored,
            )
            return result
        finally:
            await conn.execute(
                "SELECT pg_advisory_unlock($1)", _PROJECT_REGEN_LOCK_KEY,
            )


async def run_project_regen_loop(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
    provider_client: ProviderClient,
    summaries_repo: SummariesRepo,
    *,
    interval_s: int = DEFAULT_INTERVAL_S,
    startup_delay_s: int = DEFAULT_STARTUP_DELAY_S,
) -> None:
    """Infinite loop: startup-delay, sweep, sleep interval, repeat.

    Mirrors K13.1 ``run_anchor_refresh_loop`` shape so operators have
    one mental model for "background scheduler" across the service.

    Cancellation: re-raise ``asyncio.CancelledError`` at each sleep /
    await boundary so FastAPI lifespan teardown sees the cancellation
    cleanly without surfacing a traceback.
    """
    if startup_delay_s > 0:
        logger.info(
            "K20.3: project regen loop scheduled in %ds, then every %ds",
            startup_delay_s, interval_s,
        )
        try:
            await asyncio.sleep(startup_delay_s)
        except asyncio.CancelledError:
            logger.info("K20.3: project regen loop cancelled during startup delay")
            raise

    while True:
        try:
            await sweep_projects_once(
                pool, session_factory, provider_client, summaries_repo,
            )
        except asyncio.CancelledError:
            logger.info("K20.3: project regen loop cancelled during sweep")
            raise
        except Exception:
            logger.exception(
                "K20.3: project regen sweep errored (non-fatal) — "
                "continuing loop"
            )

        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            logger.info("K20.3: project regen loop cancelled during sleep")
            raise


# Type hint re-export for callers that want to spell out the full
# lifespan-task signature.
LoopCallable = Callable[..., Awaitable[None]]
