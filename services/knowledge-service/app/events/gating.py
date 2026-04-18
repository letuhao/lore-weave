"""K14.4 — Opt-in gating logic.

Checks whether a project has extraction enabled before processing
an event. Caches the result for 10s to avoid hammering Postgres
on every event.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

import asyncpg

__all__ = ["should_extract"]

logger = logging.getLogger(__name__)

# TTL cache: project_id → (enabled: bool, expires_at: float)
_cache: dict[UUID, tuple[bool, float]] = {}
_CACHE_TTL_S = 10.0


async def should_extract(
    pool: asyncpg.Pool,
    project_id: UUID,
    user_id: UUID,
) -> bool:
    """Return True if extraction is enabled for this project.

    Checks extraction_enabled AND extraction_status in ('ready', 'building').
    Cached for 10s per project to avoid per-event DB queries.
    """
    now = time.monotonic()

    # Check cache
    cached = _cache.get(project_id)
    if cached is not None:
        enabled, expires = cached
        if now < expires:
            return enabled

    # Query DB
    row = await pool.fetchrow(
        """
        SELECT extraction_enabled, extraction_status
        FROM knowledge_projects
        WHERE project_id = $1 AND user_id = $2
        """,
        project_id, user_id,
    )

    if row is None:
        _cache[project_id] = (False, now + _CACHE_TTL_S)
        return False

    enabled = bool(row["extraction_enabled"]) and row["extraction_status"] in ("ready", "building")
    _cache[project_id] = (enabled, now + _CACHE_TTL_S)
    return enabled


def invalidate_cache(project_id: UUID) -> None:
    """Remove a project from the gating cache.

    Called when extraction_enabled changes (K16.3 start, K16.4 cancel).
    """
    _cache.pop(project_id, None)


def clear_cache() -> None:
    """Clear the entire gating cache. Used in tests."""
    _cache.clear()
