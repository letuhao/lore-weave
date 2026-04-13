"""Summaries repository.

SECURITY RULE: every method takes `user_id` as the first argument and
every SQL statement filters by `user_id = $1`.

K6.3: after every successful write (upsert / delete), we invalidate
the matching key in the per-process TTL cache so the next read in
the same process sees the fresh value. Cross-process invalidation
is Track 2.
"""

from uuid import UUID

import asyncpg

from app.context import cache
from app.db.models import ScopeType, Summary

_SELECT_COLS = """
  summary_id, user_id, scope_type, scope_id, content, token_count,
  version, created_at, updated_at
"""


def _estimate_tokens(content: str) -> int:
    # Rough heuristic — 1 token ≈ 4 chars for English. CJK will
    # underestimate; Track 3 switches to tiktoken.
    return max(1, len(content) // 4)


def _rows_changed(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


def _invalidate_cache(
    user_id: UUID, scope_type: ScopeType, scope_id: UUID | None
) -> None:
    """Drop the matching cache key after a write.

    Keeps the invalidation switch in one place so both upsert and
    delete stay in sync with app.context.cache's keying scheme. An
    unknown scope_type is a no-op — we'd rather silently skip an
    unexpected scope than leak cache state, and the surrounding code
    already validates scope_type at the repo boundary.
    """
    if scope_type == "global":
        cache.invalidate_l0(user_id)
    elif scope_type == "project" and scope_id is not None:
        cache.invalidate_l1(user_id, scope_id)


class SummariesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(
        self, user_id: UUID, scope_type: ScopeType, scope_id: UUID | None
    ) -> Summary | None:
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_summaries
        WHERE user_id = $1
          AND scope_type = $2
          AND scope_id IS NOT DISTINCT FROM $3
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, scope_type, scope_id)
        return Summary.model_validate(dict(row)) if row else None

    async def upsert(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        content: str,
    ) -> Summary:
        token_count = _estimate_tokens(content)
        query = f"""
        INSERT INTO knowledge_summaries
          (user_id, scope_type, scope_id, content, token_count)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, scope_type, scope_id) DO UPDATE
          SET content = EXCLUDED.content,
              token_count = EXCLUDED.token_count,
              version = knowledge_summaries.version + 1,
              updated_at = now()
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query, user_id, scope_type, scope_id, content, token_count
            )
        result = Summary.model_validate(dict(row))
        _invalidate_cache(user_id, scope_type, scope_id)
        return result

    async def delete(
        self, user_id: UUID, scope_type: ScopeType, scope_id: UUID | None
    ) -> bool:
        query = """
        DELETE FROM knowledge_summaries
        WHERE user_id = $1
          AND scope_type = $2
          AND scope_id IS NOT DISTINCT FROM $3
        """
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, user_id, scope_type, scope_id)
        changed = _rows_changed(status) >= 1
        if changed:
            _invalidate_cache(user_id, scope_type, scope_id)
        return changed
