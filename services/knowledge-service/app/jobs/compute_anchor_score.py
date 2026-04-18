"""K13.1 — nightly anchor_score refresh job.

Recomputes `anchor_score` for every non-archived, extraction-enabled
project. Canonical (glossary-linked) entities keep `anchor_score=1.0`;
discovered entities get `mention_count / max(mention_count)` per
project; archived entities stay at 0.0.

Thin wrapper over `entities.recompute_anchor_score` (K11.5b). This
module owns project enumeration, advisory-lock-based concurrency
guard, and aggregate stats; the math lives in the Neo4j repo.

Why refresh nightly: mention counts shift as new chapters are
extracted, so the relative importance of discovered entities changes.
A scheduled refresh keeps RAG ranking accurate without paying the
cost on every query.

**Concurrency.** The refresh takes a Postgres session-level advisory
lock so two overlapping cron fires don't both sweep the graph
simultaneously (idempotent but wasteful). The second caller returns
a zeroed `RefreshResult` with `lock_skipped=True`.

**Resilience.** A fresh Neo4j session is opened per project so that
a driver fault during one project's recompute doesn't take out the
remaining sweep.

Reference: KSA §3.4.E.
"""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Awaitable, Callable

import asyncpg

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import recompute_anchor_score

logger = logging.getLogger(__name__)

__all__ = ["RefreshResult", "refresh_anchor_scores"]

# Stable key for pg_try_advisory_lock so overlapping cron fires serialise.
# Format: KKnn.mmss → 1301_01_00 → 1_301_01_00 → arbitrary but stable int64.
_REFRESH_LOCK_KEY = 1_301_01_00

# Factory returning a *fresh* CypherSession per call, wrapped in an async
# context manager so the caller's `async with` closes the driver session.
SessionFactory = Callable[[], AbstractAsyncContextManager[CypherSession]]


@dataclass
class RefreshResult:
    """Aggregate stats from a single refresh run."""

    projects_processed: int
    entities_updated: int
    projects_failed: int
    lock_skipped: bool = False


_LIST_PROJECTS_SQL = """
SELECT user_id::text   AS user_id,
       project_id::text AS project_id
FROM knowledge_projects
WHERE is_archived = false
  AND extraction_enabled = true
ORDER BY user_id, project_id
"""


async def refresh_anchor_scores(
    pool: asyncpg.Pool,
    session_factory: SessionFactory,
) -> RefreshResult:
    """Iterate non-archived projects, call `recompute_anchor_score` per
    project, return aggregate counts.

    Args:
        pool: asyncpg pool pointing at the knowledge-service Postgres DB.
        session_factory: Zero-arg callable returning an async-context-
            manager wrapping a Neo4j CypherSession. Each project gets
            a fresh session so a mid-sweep driver fault isolates to
            the offending project.

    Returns:
        `RefreshResult` with processed/updated/failed counts. If the
        advisory lock was already held by another process, returns a
        zeroed result with `lock_skipped=True`.
    """
    async with pool.acquire() as conn:
        locked = await conn.fetchval(
            "SELECT pg_try_advisory_lock($1)", _REFRESH_LOCK_KEY,
        )
        if not locked:
            logger.info(
                "K13.1: refresh already in progress on another worker — "
                "skipping this run"
            )
            return RefreshResult(0, 0, 0, lock_skipped=True)

        try:
            rows = await conn.fetch(_LIST_PROJECTS_SQL)
            processed, updated, failed = 0, 0, 0

            for row in rows:
                user_id = row["user_id"]
                project_id = row["project_id"]
                try:
                    async with session_factory() as session:
                        n_updated, _ = await recompute_anchor_score(
                            session,
                            user_id=user_id,
                            project_id=project_id,
                        )
                except Exception:
                    logger.exception(
                        "K13.1: recompute_anchor_score failed "
                        "user=%s project=%s",
                        user_id, project_id,
                    )
                    failed += 1
                    continue
                processed += 1
                updated += n_updated

            logger.info(
                "K13.1: anchor-score refresh complete — "
                "processed=%d updated=%d failed=%d",
                processed, updated, failed,
            )
            return RefreshResult(
                projects_processed=processed,
                entities_updated=updated,
                projects_failed=failed,
            )
        finally:
            await conn.fetchval(
                "SELECT pg_advisory_unlock($1)", _REFRESH_LOCK_KEY,
            )
