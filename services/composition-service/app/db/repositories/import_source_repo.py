"""import_source repository — W9 the per-user deconstruct-input store.

TENANCY (§12.6 COPYRIGHT — load-bearing): an import_source row is PER-USER ONLY.
The table has NO `visibility` column (it is un-shareable BY CONSTRUCTION — there is no
public/unlisted path, unlike motif/arc_template). `owner_user_id` is NOT NULL — a
system/global import_source is impossible. Every read/write filters on
`owner_user_id = caller`; a foreign id returns None (the router maps it to the uniform
H13 "not found or not accessible" — no existence oracle). create() SERVER-STAMPS the
owner = caller (never an arg), so a both-NULL row can never be written from this path.

Mirrors motif_repo / arc_template_repo tenancy discipline. The TABLE is F0-frozen
(app/db/migrate.py); this repo consumes it and adds NO migration.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import ImportSource

# The full row projection (no embedding/secret columns on this table — it is raw
# author-supplied text the user owns).
_SELECT_COLS = "id, owner_user_id, project_id, title, content, created_at"


def _row_to_import_source(row: asyncpg.Record) -> ImportSource:
    return ImportSource.model_validate(dict(row))


class ImportSourceRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self, user_id: UUID, *, content: str, title: str = "",
        project_id: UUID | None = None,
    ) -> ImportSource:
        """Create a PER-USER import_source. owner_user_id is STAMPED = user_id (never
        an arg → a NULL-owner/system row is impossible; the DB NOT NULL is the
        backstop). NO visibility arg — the table has no such column (§12.6: raw
        imported text is un-shareable by construction)."""
        query = f"""
        INSERT INTO import_source (owner_user_id, project_id, title, content)
        VALUES ($1, $2, $3, $4)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, project_id, title, content)
        return _row_to_import_source(row)

    async def get_for_owner(
        self, user_id: UUID, import_source_id: UUID,
    ) -> ImportSource | None:
        """OWNER-only read. A foreign/missing id returns None (IDOR-safe — the
        router maps None → the H13 uniform 'not found or not accessible', no
        existence oracle). There is NO read predicate that admits system/public rows
        here — an import_source is private to its owner, full stop."""
        query = f"""
        SELECT {_SELECT_COLS} FROM import_source
        WHERE id = $1 AND owner_user_id = $2
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, import_source_id, user_id)
        return _row_to_import_source(row) if row is not None else None

    async def list_for_owner(
        self, user_id: UUID, *, project_id: UUID | None = None, limit: int = 100,
    ) -> list[ImportSource]:
        """List the caller's OWN import_source rows (newest first). Optionally scoped
        to a project_id. Never returns another user's rows (no tier-merge — these are
        private input, not library content)."""
        params: list[Any] = [user_id]
        where = ["owner_user_id = $1"]
        if project_id is not None:
            params.append(project_id)
            where.append(f"project_id = ${len(params)}")
        params.append(max(0, limit))
        query = f"""
        SELECT {_SELECT_COLS} FROM import_source
        WHERE {" AND ".join(where)}
        ORDER BY created_at DESC
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
        return [_row_to_import_source(r) for r in rows]

    async def delete_for_owner(self, user_id: UUID, import_source_id: UUID) -> bool:
        """OWNER-only hard delete. Returns True iff a row the caller OWNS was deleted;
        a foreign/missing id deletes nothing → False (router → H13, no oracle)."""
        async with self._pool.acquire() as c:
            result = await c.execute(
                "DELETE FROM import_source WHERE id = $1 AND owner_user_id = $2",
                import_source_id, user_id,
            )
        # asyncpg execute returns a status string like "DELETE 1" / "DELETE 0".
        return result.rsplit(" ", 1)[-1] != "0"
