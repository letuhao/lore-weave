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

__all__ = ["should_extract", "may_extract_chat_turn"]

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


async def may_extract_chat_turn(
    pool: asyncpg.Pool,
    project_id: UUID,
    user_id: UUID,
) -> bool:
    """WS-1.3 — the D6 per-turn extraction gate. DERIVED, and FAILS CLOSED.

        may_extract_chat_turn = (NOT is_assistant) AND chat_turn_extraction_enabled

    ── Why derived, never stored ──
    Storing the answer is how the two consumers (this service's `handle_chat_turn` and
    worker-ai's drainer) drift apart, and a one-sided gate is a silent-success bug: one
    side stops extracting, the other keeps going, and nobody notices until a private
    conversation shows up in a novel's knowledge graph.

    ── Why the assistant is excluded from per-TURN extraction ──
    D6: one extraction source per fact, by cost tier. The assistant's facts are extracted
    ONCE A DAY from the CONFIRMED diary entry — a human-reviewed artifact — not from every
    turn of an 8-hour work session. Extracting per turn would (a) double-count every fact,
    (b) multiply LLM spend by ~100x, and (c) canonize unreviewed, off-the-cuff chat as
    trusted knowledge about the user's real colleagues.

    ── Why it FAILS CLOSED ──
    Every failure path returns False. A missing project, a DB error, an unreadable row: all
    "do not extract". Provisioning is a multi-service fan-out that can partially fail, and
    the cost of a false negative (a turn not extracted; the daily distiller catches it) is
    trivially recoverable. The cost of a false positive — extracting a private, all-day
    work conversation as canon — is not.
    """
    row = await pool.fetchrow(
        """
        SELECT is_assistant, chat_turn_extraction_enabled
        FROM knowledge_projects
        WHERE project_id = $1 AND user_id = $2
        """,
        project_id, user_id,
    )
    if row is None:
        logger.info(
            "D6 gate: no project %s for user %s — refusing chat-turn extraction (fail-closed)",
            project_id, user_id,
        )
        return False

    if bool(row["is_assistant"]):
        # Not an error, and not silent: the assistant path is SUPPOSED to skip per-turn
        # extraction. Its facts come from the daily confirmed entry instead.
        logger.debug(
            "D6 gate: project %s is the assistant project — per-turn extraction is OFF by "
            "design (facts come from the confirmed daily entry, once)",
            project_id,
        )
        return False

    return bool(row["chat_turn_extraction_enabled"])


def invalidate_cache(project_id: UUID) -> None:
    """Remove a project from the gating cache.

    Called when extraction_enabled changes (K16.3 start, K16.4 cancel).
    """
    _cache.pop(project_id, None)


def clear_cache() -> None:
    """Clear the entire gating cache. Used in tests."""
    _cache.clear()
