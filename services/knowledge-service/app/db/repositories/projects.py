"""Projects repository.

SECURITY RULE: every method takes `user_id` as the first argument and
every SQL statement filters by `user_id = $1`. Reviewers must reject any
query that does not. There is no bypass for admin flows in Track 1.
"""

import json
from datetime import datetime
from uuid import UUID

import asyncpg

from app.db.models import Project, ProjectCreate, ProjectUpdate

_SELECT_COLS = """
  project_id, user_id, name, description, project_type, book_id, instructions,
  extraction_enabled, extraction_status, embedding_model, extraction_config,
  last_extracted_at, estimated_cost_usd, actual_cost_usd, is_archived,
  created_at, updated_at
"""

# Explicit allowlist for dynamic UPDATE SET. Pydantic's ProjectUpdate already
# restricts fields, but we defend-in-depth by checking every field name
# against this set before building SQL.
_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"name", "description", "instructions", "book_id"}
)

# Columns that accept NULL. For everything else, a None value on an
# explicitly-set field is treated as "skip" (not "set to NULL") so we
# don't violate NOT NULL constraints. book_id is the only nullable
# updatable column — setting it to None explicitly clears the link.
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset({"book_id"})


def _rows_changed(status: str) -> int:
    """Parse asyncpg command tag like 'UPDATE 1' / 'DELETE 0' safely."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except ValueError:
        return 0


def _row_to_project(row: asyncpg.Record) -> Project:
    data = dict(row)
    # asyncpg returns jsonb as str or dict depending on codec; normalise.
    ec = data.get("extraction_config")
    if isinstance(ec, str):
        data["extraction_config"] = json.loads(ec)
    return Project.model_validate(data)


class ProjectsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, user_id: UUID, data: ProjectCreate) -> Project:
        query = f"""
        INSERT INTO knowledge_projects
          (user_id, name, description, project_type, book_id, instructions)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                user_id,
                data.name,
                data.description,
                data.project_type,
                data.book_id,
                data.instructions,
            )
        return _row_to_project(row)

    async def list(
        self,
        user_id: UUID,
        *,
        include_archived: bool = False,
        limit: int = 50,
        cursor_created_at: datetime | None = None,
        cursor_project_id: UUID | None = None,
    ) -> list[Project]:
        """K7.2 (D-K1-03 cleanup): cursor-paginated listing.

        Order: created_at DESC, project_id DESC. The pair acts as a
        stable sort key — created_at alone is not unique under
        millisecond-precision Postgres clocks. Cursor is "skip rows
        ordered AT-OR-AFTER (cursor_created_at, cursor_project_id)".
        Both cursor params must be supplied together; passing only
        one is treated as no cursor (the router enforces both-or-none
        before calling).

        We fetch `limit + 1` rows so the router can detect "more
        pages exist" without a second COUNT query.
        """
        # Cap the requested limit defensively — router enforces the
        # public ceiling but the repo defends in depth.
        capped = max(1, min(limit, 100))
        fetch_limit = capped + 1

        # Build query in two static halves so the planner can pick
        # idx_knowledge_projects_user (partial WHERE NOT is_archived)
        # on the common path.
        archived_pred = "" if include_archived else " AND NOT is_archived"
        params: list[object] = [user_id]
        cursor_pred = ""
        if cursor_created_at is not None and cursor_project_id is not None:
            params.extend([cursor_created_at, cursor_project_id])
            cursor_pred = (
                " AND (created_at, project_id) < ($2, $3)"
            )
        params.append(fetch_limit)

        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_projects
        WHERE user_id = $1{archived_pred}{cursor_pred}
        ORDER BY created_at DESC, project_id DESC
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [_row_to_project(r) for r in rows]

    async def get(self, user_id: UUID, project_id: UUID) -> Project | None:
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_projects
        WHERE user_id = $1 AND project_id = $2
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, project_id)
        return _row_to_project(row) if row else None

    async def update(
        self, user_id: UUID, project_id: UUID, patch: ProjectUpdate
    ) -> Project | None:
        """Apply a partial update.

        - Fields the caller didn't set are omitted (Pydantic exclude_unset).
        - Fields explicitly set to a value replace the current value.
        - Fields explicitly set to None on a NOT-NULL column (name /
          description / instructions) are silently SKIPPED — use a string
          like "" to clear them.
        - Fields explicitly set to None on a nullable column (book_id)
          CLEAR the column.
        - Empty patch (or a patch whose only fields were skipped) returns
          the current row unchanged — does NOT touch updated_at.
        - Returns None if the project does not exist or belongs to a
          different user.
        """
        raw = patch.model_dump(exclude_unset=True)
        updates: dict[str, object] = {}
        for field, value in raw.items():
            if field not in _UPDATABLE_COLUMNS:
                # Defense-in-depth; Pydantic should already prevent this.
                raise ValueError(f"field not updatable: {field}")
            if value is None and field not in _NULLABLE_UPDATE_COLUMNS:
                # Skip None on NOT-NULL columns; treat as no-op for that field.
                continue
            updates[field] = value

        if not updates:
            return await self.get(user_id, project_id)

        set_clauses: list[str] = []
        params: list[object] = [user_id, project_id]
        for field, value in updates.items():
            params.append(value)
            set_clauses.append(f"{field} = ${len(params)}")
        set_clauses.append("updated_at = now()")

        query = f"""
        UPDATE knowledge_projects
        SET {", ".join(set_clauses)}
        WHERE user_id = $1 AND project_id = $2
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
        return _row_to_project(row) if row else None

    async def archive(self, user_id: UUID, project_id: UUID) -> bool:
        """Archive a project. Returns True only if this call flipped the
        is_archived bit — calling archive() on an already-archived or
        non-existent project returns False.
        """
        query = """
        UPDATE knowledge_projects
        SET is_archived = true, updated_at = now()
        WHERE user_id = $1 AND project_id = $2 AND NOT is_archived
        """
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, user_id, project_id)
        return _rows_changed(status) >= 1

    async def delete(self, user_id: UUID, project_id: UUID) -> bool:
        """Delete a project and cascade its project-scoped summaries.

        knowledge_summaries has no FK to knowledge_projects (scope_id is
        nullable and shared across multiple scope types) so the cascade
        runs in code inside a single transaction. We invalidate the L1
        cache after a successful commit; same-process only — cross-
        process invalidation is Track 2 (D-T2-04).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM knowledge_summaries
                    WHERE user_id = $1
                      AND scope_type = 'project'
                      AND scope_id = $2
                    """,
                    user_id, project_id,
                )
                status = await conn.execute(
                    """
                    DELETE FROM knowledge_projects
                    WHERE user_id = $1 AND project_id = $2
                    """,
                    user_id, project_id,
                )
        deleted = _rows_changed(status) >= 1
        if deleted:
            from app.context import cache
            cache.invalidate_l1(user_id, project_id)
        return deleted
