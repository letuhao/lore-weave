"""Projects repository.

SECURITY RULE: every method takes `user_id` as the first argument and
every SQL statement filters by `user_id = $1`. Reviewers must reject any
query that does not. There is no bypass for admin flows in Track 1.
"""

import json
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
        self, user_id: UUID, include_archived: bool = False
    ) -> list[Project]:
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_projects
        WHERE user_id = $1
          AND ($2 OR NOT is_archived)
        ORDER BY created_at DESC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, include_archived)
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
        """Apply a partial update. Empty patch returns the current row
        unchanged (does NOT touch updated_at). Returns None if the project
        does not exist or belongs to a different user.
        """
        updates = patch.model_dump(exclude_unset=True)
        if not updates:
            return await self.get(user_id, project_id)

        set_clauses: list[str] = []
        params: list[object] = [user_id, project_id]
        for field, value in updates.items():
            if field not in _UPDATABLE_COLUMNS:
                # Defense-in-depth; Pydantic should already prevent this.
                raise ValueError(f"field not updatable: {field}")
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
        query = """
        DELETE FROM knowledge_projects
        WHERE user_id = $1 AND project_id = $2
        """
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, user_id, project_id)
        return _rows_changed(status) >= 1
