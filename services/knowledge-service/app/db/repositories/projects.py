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

# Advisory-lock namespace for the per-(user, book) book-project get-or-create
# (create_or_get). Transaction-scoped (released at commit), paired with
# hashtext("{user}:{book}"). Distinct from the cron jobs' single-key locks.
_PROJECT_BOOK_LOCK_NS = 0x4B50  # "KP"

_SELECT_COLS = """
  project_id, user_id, name, description, project_type, book_id, instructions,
  extraction_enabled, extraction_status, embedding_model, embedding_dimension,
  rerank_model, rerank_model_source,
  extraction_config, last_extracted_at, estimated_cost_usd, actual_cost_usd,
  is_archived, tool_calling_enabled, memory_remember_confirm, save_raw_extraction,
  canon_capture_enabled,
  genre, is_derivative, world_id, version, created_at, updated_at
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
     # WS-4C Half A: per-project canon auto-capture CONSENT toggle. NOT NULL
     # DEFAULT **false** (fail-closed — corrected from a once-shipped `true`;
     # migrate.py:1520/1532 heals+resets it) — do NOT "fix" this to true. Like
     # tool_calling_enabled it is deliberately absent from _NULLABLE_UPDATE_COLUMNS;
     # an explicit None is skipped.
     "canon_capture_enabled",
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
     "rerank_model", "rerank_model_source",
     # G4: attach/detach a project to a world. Nullable (explicit None clears
     # the world link) — listed in _NULLABLE_UPDATE_COLUMNS below.
     "world_id"}
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
     "rerank_model",
     # G4: None clears the world link (detach a project from a world).
     "world_id"}
)


# ── C7-followup (KN-7) — server-side projects-list filtering ──────────
# The projects browser narrows over ALL projects server-side now (was a
# client-side filter over loaded cursor pages — didn't scale). The sort
# is a CLOSED allowlist mapping the public `sort_by` token to a real
# column + the cursor's seek key. `status` filters on the project's
# derived state (extraction_status column + the `archived` pseudo-state).
#
# Cursor stability: the seek key is ALWAYS (sort_col, project_id) with
# project_id as the deterministic secondary tiebreaker — created_at /
# updated_at can tie under millisecond clocks and name / status are
# heavily non-unique, so project_id is what makes a page boundary stable
# under concurrent inserts. The cursor encodes the sort value (as the
# row's first element) + project_id; see public/projects.py.

# token → (column, is_text). is_text drives the cursor value (re)typing
# in the router: a text column round-trips the raw string; a timestamp
# column parses back to a datetime.
_PROJECT_SORT_COLUMNS: dict[str, tuple[str, bool]] = {
    "created_at": ("created_at", False),
    "updated_at": ("updated_at", False),
    "name": ("name", True),
    # `status` sorts on the extraction lifecycle column (disabled /
    # building / paused / ready / failed) — a stable text ordering.
    "status": ("extraction_status", True),
}

# Project-level status the public `status` filter accepts. The five
# extraction_status enum values plus the `archived` pseudo-state (which
# is the is_archived flag, not an extraction_status). A closed set so an
# unknown value 422s at the router rather than silently matching nothing.
_PROJECT_STATUS_FILTERS: frozenset[str] = frozenset(
    {"disabled", "building", "paused", "ready", "failed", "archived"}
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
        async with self._pool.acquire() as conn:
            return _row_to_project(await self._insert(conn, user_id, data))

    async def _insert(
        self, conn: asyncpg.Connection, user_id: UUID, data: ProjectCreate
    ) -> asyncpg.Record:
        # review-impl (Phase 1) — MUST set chat_turn_extraction_enabled=true here.
        #
        # WS-1.3 added that column with DEFAULT FALSE (fail-closed) and a D6 gate that now
        # HARD-BLOCKS the chat-turn enqueue when it is false. The one-time backfill only
        # touched PRE-EXISTING rows. So without setting it here, EVERY project created after
        # the WS-1.3 deploy would silently stop extracting chat knowledge — a regression I
        # introduced in the very slice that added the gate.
        #
        # A normal project opts in (true); this preserves the pre-WS-1.3 behavior. The
        # assistant project is the exception (facts come once a day from the confirmed
        # entry, D6) — and it is NOT created through this path: WS-1.4's provisioner inserts
        # it with is_assistant=true AND chat_turn_extraction_enabled=false explicitly. This
        # path never sets is_assistant, so it only ever mints normal projects.
        query = f"""
        INSERT INTO knowledge_projects
          (user_id, name, description, project_type, book_id, instructions,
           genre, is_derivative, world_id, chat_turn_extraction_enabled)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, true)
        RETURNING {_SELECT_COLS}
        """
        return await conn.fetchrow(
            query,
            user_id,
            data.name,
            data.description,
            data.project_type,
            data.book_id,
            data.instructions,
            data.genre,
            # C23-fix (dị bản G2): force_new ⇒ this is a derivative's own
            # fresh partition; stamp is_derivative so the source book's
            # create_or_get / get_by_book never hand it back.
            data.force_new,
            # G4: world-level project binding (NULL for normal projects).
            data.world_id,
        )

    async def create_or_get(
        self, user_id: UUID, data: ProjectCreate
    ) -> tuple[Project, bool]:
        """Idempotent create for the book-binding path. Returns ``(project, created)``.

        A book has ONE knowledge graph, but two concurrent first-POSTs for the
        same book (composition's get-or-create-work flow — D-COMP-POST-WORK-RACE)
        each saw "no project" and each created a DUPLICATE empty book project. For
        `project_type='book'` WITH a `book_id`, this serialises per-(user, book)
        with an advisory xact lock and returns the existing non-archived book
        project if one already exists (created=False), else inserts (created=True).

        Scoped to `project_type='book'`: a general/translation/code project — or a
        book-typed one with no `book_id` — still always inserts (the FE general-
        project create UX is unchanged). No UNIQUE(user, book_id) constraint is
        added (legacy rows may have several projects per book; `resolve_work`
        already tolerates that by picking the earliest).

        C23-fix (dị bản G2): when ``data.force_new`` is set (the composition
        derive path) we BYPASS the dedup entirely and ALWAYS insert a fresh
        project — `_insert` stamps it is_derivative=true. Combined with the
        ``AND NOT is_derivative`` predicate in the dedup SELECT below (and in
        `get_by_book`), a derivative is never returned for the SOURCE book, so
        the derivative gets its OWN distinct project_id (its own Neo4j delta
        partition) and composition's uq_composition_work_project holds."""
        if data.force_new or not (
            data.project_type == "book" and data.book_id is not None
        ):
            return await self.create(user_id, data), True
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Lock released at Tx commit — there is NO cross-service call held
                # under it (pure DB), so the window is a single SELECT+INSERT.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                    _PROJECT_BOOK_LOCK_NS, f"{user_id}:{data.book_id}",
                )
                existing = await conn.fetchrow(
                    f"""
                    SELECT {_SELECT_COLS} FROM knowledge_projects
                    WHERE user_id = $1 AND project_type = 'book'
                      AND book_id = $2 AND NOT is_archived
                      AND NOT is_derivative
                      -- WS-1.4: the assistant project is a project_type='book' bound to the
                      -- diary book; it must NEVER be handed back to a normal book-project
                      -- flow (which would treat the assistant's memory as a novel's KG,
                      -- wrong partition + wrong extraction semantics). Same guard as
                      -- NOT is_derivative, for the same "shares a book_id" reason.
                      AND NOT is_assistant
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    user_id, data.book_id,
                )
                if existing is not None:
                    # G4: idempotent world-binding. Stamp world_id onto the
                    # existing bible-book project ONLY when it is not yet bound
                    # (first world-create binding, or a re-provision after the
                    # column landed). We deliberately do NOT rebind a project
                    # that already carries a (different) world_id — a bible book
                    # belongs to exactly one world and never moves, so a
                    # differing world_id would be a caller bug, not a re-home;
                    # refusing it keeps the binding stable. Re-provision with the
                    # SAME world_id is a no-op. Not a content edit, so `version`
                    # is left untouched (If-Match is for user PATCHes).
                    if (
                        data.world_id is not None
                        and existing["world_id"] is None
                    ):
                        existing = await conn.fetchrow(
                            f"""
                            UPDATE knowledge_projects
                            SET world_id = $3, updated_at = now()
                            WHERE user_id = $1 AND project_id = $2
                            RETURNING {_SELECT_COLS}
                            """,
                            user_id, existing["project_id"], data.world_id,
                        )
                    return _row_to_project(existing), False
                return _row_to_project(await self._insert(conn, user_id, data)), True

    async def get_or_create_benchmark_sandbox(
        self, user_id: UUID, embedding_model: str, embedding_dimension: int
    ) -> Project:
        """R1 (D-JOURNEY-KG-BENCHMARK-UX) — resolve (or lazily create) the hidden
        benchmark SANDBOX project for ``(user, embedding_model)``. The K17.9
        benchmark runs HERE, never on the user's real content-bearing build
        project, so it cannot trip ``not_benchmark_project`` and its ~10 synthetic
        fixture passages never pollute real data. Owner-scoped, ``book_id`` NULL,
        ``is_benchmark_sandbox=true``, and excluded from every project listing.
        Idempotent via a per-(user, model) advisory lock so two concurrent
        benchmark POSTs can't create duplicate sandboxes."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                    _PROJECT_BOOK_LOCK_NS, f"benchmark:{user_id}:{embedding_model}",
                )
                existing = await conn.fetchrow(
                    f"""
                    SELECT {_SELECT_COLS} FROM knowledge_projects
                    WHERE user_id = $1 AND is_benchmark_sandbox
                      AND embedding_model = $2 AND NOT is_archived
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    user_id, embedding_model,
                )
                if existing is not None:
                    return _row_to_project(existing)
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO knowledge_projects
                      (user_id, name, project_type, is_benchmark_sandbox,
                       embedding_model, embedding_dimension)
                    VALUES ($1, $2, 'general', true, $3, $4)
                    RETURNING {_SELECT_COLS}
                    """,
                    user_id, f"__benchmark__:{embedding_model}",
                    embedding_model, embedding_dimension,
                )
                return _row_to_project(row)

    async def get_or_create_assistant_project(
        self, user_id: UUID, book_id: UUID, name: str = "Work Assistant"
    ) -> tuple[Project, bool]:
        """WS-1.4 (spec 02 §Q2.2) — resolve (or create) the user's ONE assistant
        knowledge project, bound to their diary book. Returns ``(project, created)``.

        ``is_assistant=true`` marks it as the assistant's memory. The one-per-user
        partial unique (``uq_knowledge_projects_one_assistant_per_user``) means two
        concurrent provisions (two devices, a retried BFF call) converge on ONE project
        instead of splitting the assistant's memory into two graphs; the per-(user)
        advisory lock makes the get-or-create race-safe within a single Tx window.

        ``chat_turn_extraction_enabled=FALSE``, explicitly and fail-closed (D6): the
        assistant's facts come once a day from the CONFIRMED diary entry
        (``chapter.kg_indexed``), never per chat turn. Extracting every turn as trusted
        canon about the user's real colleagues, at ~100x spend, is exactly the bug the
        D6 gate exists to stop — so this path must not inherit the normal project's
        opt-in ``true``."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                    _PROJECT_BOOK_LOCK_NS, f"assistant:{user_id}",
                )
                existing = await conn.fetchrow(
                    f"""
                    SELECT {_SELECT_COLS} FROM knowledge_projects
                    WHERE user_id = $1 AND is_assistant AND NOT is_archived
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    user_id,
                )
                if existing is not None:
                    # Idempotent book-binding: bind the diary book if a prior provision
                    # created the assistant project book-less (or before the diary
                    # existed). Never REBIND to a different book — the assistant belongs
                    # to exactly one diary; a differing book_id is a caller bug, refused
                    # by leaving the existing binding intact.
                    if existing["book_id"] is None and book_id is not None:
                        existing = await conn.fetchrow(
                            f"""
                            UPDATE knowledge_projects
                            SET book_id = $3, updated_at = now()
                            WHERE user_id = $1 AND project_id = $2
                            RETURNING {_SELECT_COLS}
                            """,
                            user_id, existing["project_id"], book_id,
                        )
                    return _row_to_project(existing), False
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO knowledge_projects
                      (user_id, name, project_type, book_id, is_assistant,
                       chat_turn_extraction_enabled)
                    VALUES ($1, $2, 'book', $3, true, false)
                    RETURNING {_SELECT_COLS}
                    """,
                    user_id, name, book_id,
                )
                return _row_to_project(row), True

    async def list(
        self,
        user_id: UUID,
        *,
        include_archived: bool = False,
        limit: int = 50,
        cursor_sort_value: object | None = None,
        cursor_project_id: UUID | None = None,
        book_id: UUID | None = None,
        world_id: UUID | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        status: str | None = None,
    ) -> list[Project]:
        """K7.2 (D-K1-03) + C7-followup (KN-7): cursor-paginated listing
        with server-side search / sort / status narrowing.

        Order: ``<sort_col> <dir>, project_id <dir>``. project_id is the
        deterministic secondary key that makes the page boundary stable —
        created_at / updated_at can tie under millisecond clocks, and
        name / status are heavily non-unique. The cursor's seek predicate
        is the row-value comparison ``(<sort_col>, project_id) <op>
        (cursor_sort_value, cursor_project_id)`` where ``<op>`` is ``<``
        for descending and ``>`` for ascending, matching the ORDER BY so
        paging is stable even with concurrent inserts. Both cursor params
        must be supplied together (the router enforces both-or-none).

        Additive + back-compatible: no params ⇒ the original
        ``created_at DESC, project_id DESC`` behaviour. ``sort_by`` is a
        CLOSED allowlist (router 422s an unknown token before calling).

        ``search`` is a case-insensitive substring on ``name`` (ILIKE
        with the wildcards escaped so a user typing ``%`` / ``_`` doesn't
        get a surprise wildcard). ``status`` filters on the project's
        derived state: ``archived`` ⇒ ``is_archived = true``; any other
        value ⇒ ``extraction_status = <value>``.

        We fetch ``limit + 1`` rows so the router can detect "more pages
        exist" without a second COUNT query.
        """
        # Cap the requested limit defensively — router enforces the
        # public ceiling but the repo defends in depth.
        capped = max(1, min(limit, 100))
        fetch_limit = capped + 1

        # Resolve the sort column from the closed allowlist — defense in
        # depth (the router validates, but a future internal caller might
        # not). An unknown token is a programming error, not user input.
        col, _is_text = _PROJECT_SORT_COLUMNS.get(sort_by, ("created_at", False))
        direction = "ASC" if sort_dir == "asc" else "DESC"
        seek_op = ">" if direction == "ASC" else "<"

        # Build query in two static halves so the planner can pick
        # idx_knowledge_projects_user (partial WHERE NOT is_archived)
        # on the common path.
        params: list[object] = [user_id]

        # status filter takes precedence over include_archived for the
        # archived bucket: ?status=archived forces is_archived=true even
        # when include_archived wasn't set. Other status values are
        # implicitly non-archived (a "ready but archived" project belongs
        # to the archived bucket, not the ready bucket).
        if status == "archived":
            status_pred = " AND is_archived"
        elif status is not None:
            params.append(status)
            status_pred = (
                f" AND NOT is_archived AND extraction_status = ${len(params)}"
            )
        elif include_archived:
            status_pred = ""
        else:
            status_pred = " AND NOT is_archived"

        search_pred = ""
        if search:
            # Escape ILIKE wildcards so a literal % / _ doesn't widen the
            # match. ESCAPE '\' pairs with the backslash-escaped wildcards.
            escaped = (
                search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            params.append(f"%{escaped}%")
            search_pred = f" AND name ILIKE ${len(params)} ESCAPE '\\'"

        cursor_pred = ""
        if cursor_sort_value is not None and cursor_project_id is not None:
            params.extend([cursor_sort_value, cursor_project_id])
            cursor_pred = (
                f" AND ({col}, project_id) {seek_op} "
                f"(${len(params) - 1}, ${len(params)})"
            )

        # C5 (ARCH-1): optional book filter — the editor AI panel resolves a
        # book's knowledge project by book_id. Placeholder is numbered
        # dynamically so it composes with the optional params above.
        book_pred = ""
        if book_id is not None:
            params.append(book_id)
            book_pred = f" AND book_id = ${len(params)}"

        # G4: world-level project visibility.
        # - explicit world_id filter ⇒ return that world's project(s) (the
        #   world-rollup resolver / world workspace).
        # - no world_id AND no book_id (the HOME projects browse) ⇒ HIDE
        #   world-level projects (world_id IS NOT NULL) so the bible/world
        #   project never appears as a phantom row.
        # - a book_id filter (editor AI panel / useWorldProject graph resolver)
        #   is EXEMPT — it must still resolve the bible book's world project.
        world_pred = ""
        if world_id is not None:
            params.append(world_id)
            world_pred = f" AND world_id = ${len(params)}"
        elif book_id is None:
            world_pred = " AND world_id IS NULL"
        params.append(fetch_limit)

        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_projects
        WHERE user_id = $1 AND NOT is_benchmark_sandbox{status_pred}{search_pred}{cursor_pred}{book_pred}{world_pred}
        ORDER BY {col} {direction}, project_id {direction}
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
        WHERE user_id = $1 AND NOT is_benchmark_sandbox
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

    async def project_meta(self, project_id: UUID) -> tuple[UUID, UUID | None] | None:
        """E0-3 authorization bootstrap — return ``(owner_user_id, book_id)`` for a
        project, NOT scoped by user. This is the ONLY non-user-scoped read; it
        returns just the two ids the grant gate needs (never project content), so a
        non-grantee still gets a uniform 404 at the access layer (no oracle). Returns
        None if the project does not exist. ``book_id`` is None for a book-less
        project (→ owner-only fallback, R1)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, book_id FROM knowledge_projects WHERE project_id = $1",
                project_id,
            )
        return (row["user_id"], row["book_id"]) if row else None

    async def get_by_book(self, book_id: UUID) -> Project | None:
        """E0-3 — the (single, book-owner-owned) active book project for a book,
        NOT user-scoped. Book-scoped routes (raw-search) call this AFTER a book
        grant check so a collaborator searches the owner's project. Creation is
        book-owner-only, so there is at most one 'book' project per book.

        C23-fix (dị bản G2): `AND NOT is_derivative` so a derivative project
        sharing the source's book_id is never mistaken for the source book's
        canonical project (raw-search must always resolve the SOURCE partition)."""
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_projects
        WHERE book_id = $1 AND project_type = 'book' AND NOT is_archived
          AND NOT is_derivative
          -- WS-1.4: never resolve the diary's assistant project as a normal book
          -- project (same "shares a book_id" reason as NOT is_derivative).
          AND NOT is_assistant
        ORDER BY created_at
        LIMIT 1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, book_id)
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

    async def set_rerank_model(
        self,
        user_id: UUID,
        project_id: UUID,
        *,
        rerank_model: str | None,
        rerank_model_source: str = "user_model",
    ) -> Project | None:
        """S5b: set the project's BYOK reranker (campaign override path). Unlike
        embedding, rerank has no vector-space hazard — it is applied at raw-search
        time — so no graph delete / confirm is needed. rerank_model NULL clears the
        selection (rerank skipped); rerank_model_source is NOT NULL (default
        'user_model'). Owner-scoped; returns None if not owned / not found."""
        query = f"""
        UPDATE knowledge_projects
        SET rerank_model = $3, rerank_model_source = $4, updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, user_id, project_id, rerank_model, rerank_model_source,
            )
        return _row_to_project(row) if row else None

    async def set_canon_capture_consent(
        self, user_id: UUID, project_id: UUID, *, enabled: bool,
    ) -> Project | None:
        """A2 / D-R17 — the per-turn work-capture CONSENT toggle (`canon_capture_enabled`). The
        column is fail-closed by DEFAULT false; this is the user turning capture ON/OFF. Owner-
        scoped (None if not owned / not found). The chat-service capture gate reads this via
        `project_enables`, so the effect lands on the NEXT turn — E8: "consent off mid-day stops
        capture next tick". The effective value is still AND(deploy_ceiling, this) — a deployment
        kill-switch can force it off regardless (surfaced by the capabilities read)."""
        query = f"""
        UPDATE knowledge_projects
        SET canon_capture_enabled = $3, updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, project_id, enabled)
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

    async def list_assistant_project_ids(self, user_id: UUID) -> "list[str]":
        """D16 (spec 07 §Q4) — the ids of the user's ASSISTANT (diary) projects, as strings for a Neo4j
        param. The memory_* read tools pass these as `exclude_project_ids` when a session has no explicit
        project, so the all-projects fallback can never surface work-diary entities into a novel-writing
        session. Normally 0 or 1 row (one assistant per user), so this is a cheap indexed lookup."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT project_id FROM knowledge_projects "
                "WHERE user_id = $1 AND is_assistant AND NOT is_archived",
                user_id,
            )
        return [str(r["project_id"]) for r in rows]
