"""Projects repository.

SECURITY RULE: every method takes `user_id` as the first argument and
every SQL statement filters by `user_id = $1`. Reviewers must reject any
query that does not. There is no bypass for admin flows in Track 1.
"""

import json
from datetime import datetime
from uuid import UUID

import asyncpg

from app.context import cache
from app.db.models import ExtractionStatus, Project, ProjectCreate, ProjectUpdate
from app.db.repositories import VersionMismatchError

_SELECT_COLS = """
  project_id, user_id, name, description, project_type, book_id, instructions,
  extraction_enabled, extraction_status, embedding_model, embedding_dimension,
  rerank_model, rerank_model_source,
  extraction_config, last_extracted_at, estimated_cost_usd, actual_cost_usd,
  is_archived, tool_calling_enabled, memory_remember_confirm, save_raw_extraction,
  genre, version, created_at, updated_at
"""

# Explicit allowlist for dynamic UPDATE SET. Pydantic's ProjectUpdate already
# restricts fields, but we defend-in-depth by checking every field name
# against this set before building SQL.
_UPDATABLE_COLUMNS: frozenset[str] = frozenset(
    {"name", "description", "instructions", "book_id", "is_archived",
     "embedding_model", "genre",
     # K21.12-BE (design D9): per-project tool-calling toggle. NOT NULL,
     # so it is deliberately absent from _NULLABLE_UPDATE_COLUMNS — an
     # explicit None on this field is skipped like name/description.
     "tool_calling_enabled",
     # K21-C (design D4): per-project memory_remember confirmation
     # gate. NOT NULL, so — like tool_calling_enabled — deliberately
     # absent from _NULLABLE_UPDATE_COLUMNS; explicit None is skipped.
     "memory_remember_confirm",
     # P2 (D6): opt-in raw-response retention. NOT NULL DEFAULT false;
     # FE follow-up D-P2-FE-SAVE-RAW will expose a toggle. PATCH updates
     # the flag; leaf_processor reads it at extraction time.
     "save_raw_extraction",
     # D-EMB-MODEL-REF-01: embedding_dimension is now caller-supplied
     # (it was a derived column under the old logical-name design).
     # embedding_model carries the provider-registry user_model UUID,
     # which is not derivable to a dimension — so the caller (FE picker /
     # config flow) sends embedding_model + embedding_dimension together.
     "embedding_dimension",
     # D-RERANK-NOT-BYOK: per-project BYOK rerank model (user_model UUID) +
     # source. rerank_model is nullable (clears the selection → raw-search skips
     # rerank); rerank_model_source is NOT NULL (default 'user_model') so, like
     # tool_calling_enabled, an explicit None is skipped. FE picker = S0b.
     "rerank_model", "rerank_model_source"}
)

# Columns that accept NULL. For everything else, a None value on an
# explicitly-set field is treated as "skip" (not "set to NULL") so we
# don't violate NOT NULL constraints.
# - `book_id`: None clears the book link.
# - `embedding_model` (D-EMB-MODEL-REF-01): the provider-registry
#   user_model UUID of the embedding model. None clears the selection;
#   clearing it also clears embedding_dimension (see update()).
# - `embedding_dimension` (D-EMB-MODEL-REF-01): caller-supplied; nullable
#   so the model selection can be cleared.
_NULLABLE_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {"book_id", "embedding_model", "embedding_dimension", "genre",
     # D-RERANK-NOT-BYOK: None clears the rerank model selection.
     "rerank_model"}
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
          (user_id, name, description, project_type, book_id, instructions, genre)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
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
                data.genre,
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
        book_id: UUID | None = None,
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
        # C5 (ARCH-1): optional book filter — the editor AI panel resolves a
        # book's knowledge project by book_id. Placeholder is numbered
        # dynamically so it composes with the optional cursor params above.
        book_pred = ""
        if book_id is not None:
            params.append(book_id)
            book_pred = f" AND book_id = ${len(params)}"
        params.append(fetch_limit)

        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_projects
        WHERE user_id = $1{archived_pred}{cursor_pred}{book_pred}
        ORDER BY created_at DESC, project_id DESC
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [_row_to_project(r) for r in rows]

    # K7d export safety belt: if a user somehow has more than this
    # many projects, the export endpoint refuses with 507 rather than
    # silently truncating. Track 1 expects << 100 per user; if anyone
    # legitimately hits this we'll switch the export to a streaming
    # NDJSON response (Track 3 scope per K7.5 spec notes).
    EXPORT_HARD_CAP = 10_000

    async def list_all_for_user(self, user_id: UUID) -> "list[Project]":
        """Return every project owned by `user_id` (incl. archived) for
        K7d export. Capped at `EXPORT_HARD_CAP + 1` so the route can
        detect overflow and fail noisily.
        """
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_projects
        WHERE user_id = $1
        ORDER BY created_at, project_id
        LIMIT {self.EXPORT_HARD_CAP + 1}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
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
        self,
        user_id: UUID,
        project_id: UUID,
        patch: ProjectUpdate,
        expected_version: int | None = None,
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
          the current row unchanged — does NOT touch updated_at or version.
          Preserves the K7b no-op contract.
        - Returns None if the project does not exist or belongs to a
          different user.

        D-K8-03: when ``expected_version`` is not None the UPDATE's
        WHERE clause gates on ``version = $N`` and the SET clause
        bumps ``version = version + 1``. The 0-row path does a
        follow-up SELECT so the router can distinguish 404 (row
        gone) from 412 (row exists with a different version).
        Raises ``VersionMismatchError`` with the current row on
        version mismatch.
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

        # D-EMB-MODEL-REF-01: embedding_model now carries the provider-
        # registry user_model UUID — a dimension is not derivable from it,
        # so the caller supplies embedding_dimension explicitly. The only
        # invariant kept here: clearing the model (None) clears the
        # dimension too, so a project can't be left model-less but
        # dimension-tagged.
        if updates.get("embedding_model", "unset") is None:
            updates["embedding_dimension"] = None

        if not updates:
            # No-op: K7b contract preserves updated_at AND version. Even
            # if the caller passed an expected_version we don't need
            # to validate it — an empty patch is semantically a no-op
            # read, and GETs don't require If-Match either.
            return await self.get(user_id, project_id)

        set_clauses: list[str] = []
        params: list[object] = [user_id, project_id]
        for field, value in updates.items():
            params.append(value)
            set_clauses.append(f"{field} = ${len(params)}")
        set_clauses.append("updated_at = now()")

        version_clause = ""
        if expected_version is not None:
            params.append(expected_version)
            version_clause = f" AND version = ${len(params)}"
            set_clauses.append("version = version + 1")

        query = f"""
        UPDATE knowledge_projects
        SET {", ".join(set_clauses)}
        WHERE user_id = $1 AND project_id = $2{version_clause}
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
        if row is not None:
            return _row_to_project(row)

        if expected_version is None:
            # Legacy path: 0 rows means 404 (not found / cross-user).
            return None

        # D-K8-03: 0 rows with an expected_version could mean either
        # 404 or 412. A follow-up GET disambiguates. Race with a
        # concurrent DELETE would flip 412 → 404 which is acceptable
        # (the client sees "the row no longer exists" which is the
        # fresher truth).
        current = await self.get(user_id, project_id)
        if current is None:
            return None
        raise VersionMismatchError(current)

    async def update_extraction_config(
        self,
        user_id: UUID,
        project_id: UUID,
        config: dict,
        expected_version: int,
    ) -> Project | None:
        """B2-B-b1 — replace `extraction_config` (JSONB) + bump version.

        Dedicated path (not the generic `update`) because the JSONB column
        needs `json.dumps` + a `::jsonb` cast that the generic SET-clause loop
        doesn't do. Mirrors `update`'s If-Match discipline: a 0-row result with
        a version that exists raises VersionMismatchError (→ 412); a missing row
        returns None (→ 404)."""
        query = f"""
        UPDATE knowledge_projects
        SET extraction_config = $3::jsonb,
            version = version + 1,
            updated_at = now()
        WHERE user_id = $1 AND project_id = $2 AND version = $4
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query, user_id, project_id, json.dumps(config), expected_version,
            )
        if row is not None:
            return _row_to_project(row)
        current = await self.get(user_id, project_id)
        if current is None:
            return None
        raise VersionMismatchError(current)

    async def set_extraction_state(
        self,
        user_id: UUID,
        project_id: UUID,
        *,
        extraction_enabled: bool,
        extraction_status: ExtractionStatus,
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
        conn: "asyncpg.Connection | None" = None,
    ) -> Project | None:
        """K16.3: atomically update extraction-related fields on a project.

        Accepts an optional `conn` so the caller can run this inside
        an existing transaction (e.g., the start-job endpoint creates
        the job row and updates the project in one transaction).

        `embedding_model` / `embedding_dimension` are COALESCE-updated —
        pass both together (D-EMB-MODEL-REF-03: the dimension is probed
        by the caller and must stay paired with the model); pass neither
        to leave them unchanged.

        Returns the updated project or None if the project doesn't
        exist / belongs to another user.
        """
        query = f"""
        UPDATE knowledge_projects
        SET extraction_enabled = $3,
            extraction_status = $4,
            embedding_model = COALESCE($5, embedding_model),
            embedding_dimension = COALESCE($6, embedding_dimension),
            updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        RETURNING {_SELECT_COLS}
        """
        if conn is not None:
            row = await conn.fetchrow(
                query, user_id, project_id,
                extraction_enabled, extraction_status,
                embedding_model, embedding_dimension,
            )
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(
                    query, user_id, project_id,
                    extraction_enabled, extraction_status,
                    embedding_model, embedding_dimension,
                )
        return _row_to_project(row) if row else None

    async def archive(
        self, user_id: UUID, project_id: UUID
    ) -> Project | None:
        """Archive a project and return the updated row.

        K7b-I2 fix: returns the row via UPDATE … RETURNING so the
        router doesn't have to issue a second SELECT. Also closes a
        tiny race window where a concurrent DELETE could 404 the
        follow-up get() between the UPDATE and the SELECT.

        Returns None if the project does not exist, belongs to another
        user, or was already archived — the caller treats these
        uniformly as 404 (don't leak which one it was).
        """
        query = f"""
        UPDATE knowledge_projects
        SET is_archived = true, updated_at = now()
        WHERE user_id = $1 AND project_id = $2 AND NOT is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, project_id)
        return _row_to_project(row) if row else None

    async def delete(self, user_id: UUID, project_id: UUID) -> bool:
        """Delete a project and cascade its project-scoped summaries.

        knowledge_summaries has no FK to knowledge_projects (scope_id is
        nullable and shared across multiple scope types) so the cascade
        runs in code inside a single transaction.

        K7b-I1 fix: we DELETE the project row FIRST and short-circuit on
        rowcount=0. This guarantees that a cross-user or nonexistent
        delete never runs the summary cascade — previously we deleted
        summaries before verifying ownership, which was wasted work in
        the happy path and a logic smell in edge cases. The project-
        first order is also safe: both DELETEs live in the same
        transaction, so an early return rolls back atomically.

        After a successful commit we invalidate the L1 cache for the
        project. Same-process only — cross-process invalidation is
        Track 2 (D-T2-04).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.execute(
                    """
                    DELETE FROM knowledge_projects
                    WHERE user_id = $1 AND project_id = $2
                    """,
                    user_id, project_id,
                )
                if _rows_changed(status) < 1:
                    # Project didn't exist or wasn't ours — abort the
                    # transaction so we don't touch summaries either.
                    return False
                await conn.execute(
                    """
                    DELETE FROM knowledge_summaries
                    WHERE user_id = $1
                      AND scope_type = 'project'
                      AND scope_id = $2
                    """,
                    user_id, project_id,
                )
        cache.invalidate_l1(user_id, project_id)
        return True
