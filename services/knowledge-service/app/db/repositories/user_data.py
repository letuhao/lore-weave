"""User-data repository — owns cross-table operations on a user's
knowledge-service-owned rows (projects + summaries).

K7d's GDPR-erasure delete needs both `knowledge_projects` and
`knowledge_summaries` purged in a single transaction so the user gets
one definitive answer ("either everything is gone or nothing is").
Putting that on either ProjectsRepo or SummariesRepo would couple
them to the other table's columns; a thin standalone repo keeps the
concern in one place and reads naturally as "user data, all of it".

SECURITY RULE (same as every other repo): user_id is the first arg
and every statement filters on it. There is no admin bypass.
"""

from uuid import UUID

import asyncpg

from app.context import cache


def _rows_changed(status: str) -> int:
    """Parse asyncpg command tag like 'DELETE 5' → 5."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


class UserDataRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def delete_all_for_user(self, user_id: UUID) -> dict[str, int]:
        """Hard-delete every project + summary row owned by `user_id`.

        Both DELETEs run inside a single asyncpg transaction so the
        user-visible answer is atomic: either both tables are cleared
        or neither is. After commit, every cache entry for this user
        is invalidated in-process — cross-process invalidation is
        Track 2 (D-T2-04) so a sibling worker may serve up to 60s of
        stale L0/L1 reads before its own TTL expires.

        Order: summaries first, projects second. There's no FK from
        summaries to projects (scope_id is nullable + cross-scope), so
        the order is mostly cosmetic — but deleting "the smaller
        dependent set" first matches the K7b cascade convention and
        leaves the bigger DELETE for last where its row count is the
        natural last word in the receipt.

        Returns: {"summaries": int, "projects": int} — counts of rows
        actually deleted, suitable for the route's 200 response body.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                s_status = await conn.execute(
                    "DELETE FROM knowledge_summaries WHERE user_id = $1",
                    user_id,
                )
                p_status = await conn.execute(
                    "DELETE FROM knowledge_projects WHERE user_id = $1",
                    user_id,
                )

        # Cache invalidation runs AFTER commit succeeds — if the
        # transaction rolled back we don't want to drop fresh cached
        # rows that are still valid.
        cache.invalidate_all_for_user(user_id)

        return {
            "summaries": _rows_changed(s_status),
            "projects": _rows_changed(p_status),
        }
