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

    # K7c safety belt: hard cap on un-paginated list_for_user results
    # so a user with thousands of project rows can't DoS the Memory page.
    # Track 1 expects one global + a handful of projects per user; if a
    # real user ever hits this we'll add proper pagination on the GET
    # /v1/knowledge/summaries endpoint.
    _LIST_FOR_USER_HARD_CAP = 1000

    async def list_for_user(self, user_id: UUID) -> list[Summary]:
        """Return every summary row owned by `user_id`, all scopes.

        Used by the K7c GET /v1/knowledge/summaries endpoint to render
        the user's Memory page in one round-trip. Capped at
        `_LIST_FOR_USER_HARD_CAP` rows. Ordered global → project →
        session → entity (intentional CASE order so the router can rely
        on globals appearing first), then most-recently-updated first
        within each scope.
        """
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_summaries
        WHERE user_id = $1
        ORDER BY
          CASE scope_type
            WHEN 'global' THEN 0
            WHEN 'project' THEN 1
            WHEN 'session' THEN 2
            WHEN 'entity' THEN 3
            ELSE 4
          END,
          updated_at DESC
        LIMIT {self._LIST_FOR_USER_HARD_CAP}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
        return [Summary.model_validate(dict(r)) for r in rows]

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

    async def upsert_project_scoped(
        self,
        user_id: UUID,
        project_id: UUID,
        content: str,
    ) -> Summary | None:
        """Upsert a project-scope summary atomically with an ownership check.

        Returns the new Summary on success, or None if the user does not
        own `project_id` (cross-user OR nonexistent — the router cannot
        distinguish these per KSA §6.4 anti-leak rules).

        Closes the TOCTOU window between a router-level "does this user
        own the project?" SELECT and the subsequent upsert: a single CTE
        guards the INSERT/UPDATE on `EXISTS(SELECT 1 FROM knowledge_projects
        WHERE user_id=$1 AND project_id=$2)`. If the EXISTS returns false
        the INSERT inserts zero rows, the ON CONFLICT path doesn't fire,
        and RETURNING yields nothing — we map empty → None.

        Also halves connection-pool usage on the hot edit path versus
        the previous "two repo calls = two pool.acquire() round trips"
        shape used in the K7c BUILD.
        """
        token_count = _estimate_tokens(content)
        query = f"""
        WITH owned AS (
          SELECT 1 FROM knowledge_projects
          WHERE user_id = $1 AND project_id = $2
        ),
        upserted AS (
          INSERT INTO knowledge_summaries
            (user_id, scope_type, scope_id, content, token_count)
          SELECT $1, 'project', $2, $3, $4
          WHERE EXISTS (SELECT 1 FROM owned)
          ON CONFLICT (user_id, scope_type, scope_id) DO UPDATE
            SET content = EXCLUDED.content,
                token_count = EXCLUDED.token_count,
                version = knowledge_summaries.version + 1,
                updated_at = now()
          RETURNING {_SELECT_COLS}
        )
        SELECT * FROM upserted
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, project_id, content, token_count)
        if row is None:
            return None
        result = Summary.model_validate(dict(row))
        _invalidate_cache(user_id, "project", project_id)
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
