"""plan_run + plan_artifact repository (PlanForge M3).

Tenancy (BPS re-key, spec 25 OQ-3): rows are BOOK-scoped — every read filters
by book_id, and access is decided BEFORE the repo at the route's E0 book-grant
gate. `created_by` is a plain actor stamp on writes — STORED, never filtered
on. `plan_artifact` carries no book_id column: its reads gate through the
`JOIN plan_run r ON r.id = plan_artifact.run_id` with the scope on r.book_id —
never a direct artifact read without that join. A foreign/missing id returns
None — routers map to 404 (no existence oracle).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.db.models import PlanArtifact, PlanArtifactKind, PlanRun, PlanRunMode, PlanRunStatus

_SELECT_RUN = """
  id, created_by, book_id, work_id, status, mode, model_ref, source_checksum,
  source_markdown, active_job_id, error_detail, checkpoint_state,
  pass_state, genre_tags, is_archived, created_at, updated_at
"""

# `a.`-prefixed so the artifact reads can join plan_run (the book-scope gate);
# the INSERT RETURNING strips the prefix (authoring_run_units precedent).
_SELECT_ARTIFACT = "a.id, a.run_id, a.created_by, a.kind, a.content, a.created_at"


def _jsonb(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {})


def _row_run(row: asyncpg.Record) -> PlanRun:
    data = dict(row)
    # asyncpg hands JSONB back as a str unless a codec is registered. Every jsonb column must be
    # decoded HERE — a column selected but not decoded validates as a string and then silently
    # becomes `{}`/`[]` in the model, which is a read-only-looking write-only bug.
    for key in ("checkpoint_state", "pass_state", "genre_tags"):
        v = data.get(key)
        if isinstance(v, str):
            data[key] = json.loads(v)
    return PlanRun.model_validate(data)


def _row_artifact(row: asyncpg.Record) -> PlanArtifact:
    data = dict(row)
    c = data.get("content")
    if isinstance(c, str):
        data["content"] = json.loads(c)
    return PlanArtifact.model_validate(data)


class PlanRunsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        created_by: UUID,
        book_id: UUID,
        *,
        mode: PlanRunMode,
        source_checksum: str,
        source_markdown: str,
        model_ref: UUID | None = None,
        status: PlanRunStatus = "pending",
        # 27 PF-15 — the genre the plan is written FOR. A per-RUN input, not platform config: two
        # users planning two books want different values, and the same user's next book may too
        # (Settings & Configuration Boundary — "would two users want different values?" ⇒ yes ⇒
        # it is a choice that rides the row, never an env flag).
        genre_tags: list[str] | None = None,
    ) -> PlanRun:
        query = f"""
        INSERT INTO plan_run
          (created_by, book_id, mode, model_ref, source_checksum, source_markdown, status,
           genre_tags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        RETURNING {_SELECT_RUN}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query,
                created_by,
                book_id,
                mode,
                model_ref,
                source_checksum,
                source_markdown,
                status,
                json.dumps(list(genre_tags or [])),
            )
        return _row_run(row)

    async def find_by_checksum(
        self, book_id: UUID, source_checksum: str, mode: str,
    ) -> PlanRun | None:
        # `mode` is part of the identity of a propose request, not just the text --
        # a user re-Proposing identical markdown after switching Rules -> LLM must
        # get a FRESH run, never the stale other-mode result (D-PLANFORGE-MODE-DEDUPE).
        # Book-scoped dedupe (OQ-3): a grantee re-Proposing the owner's identical
        # markdown finds the existing run instead of forking a duplicate.
        # BE-4 — skip ARCHIVED runs: re-Proposing identical markdown must mint a FRESH run, never
        # dedupe onto a run the user archived (else their new Propose silently returns an invisible
        # run — a real bug, not a nicety).
        query = f"""
        SELECT {_SELECT_RUN} FROM plan_run
        WHERE book_id = $1 AND source_checksum = $2 AND mode = $3 AND NOT is_archived
        ORDER BY created_at DESC
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, book_id, source_checksum, mode)
        return _row_run(row) if row else None

    async def get_for_book(
        self, book_id: UUID, run_id: UUID,
    ) -> PlanRun | None:
        # BE-4 — MUST NOT filter archived: restore() and the detail view both need to read the
        # tombstone. Do not "fix" this with `AND NOT is_archived` — a later reviewer's instinct.
        query = f"""
        SELECT {_SELECT_RUN} FROM plan_run
        WHERE id = $1 AND book_id = $2
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, book_id)
        return _row_run(row) if row else None

    async def archive(self, book_id: UUID, run_id: UUID) -> bool:
        """BE-4 — soft-archive (mirrors canon_rules). True if it flipped; False if already archived
        or not in this book (the router maps False+not-found the same way the caller decides)."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                "UPDATE plan_run SET is_archived = true, updated_at = now() "
                "WHERE id = $1 AND book_id = $2 AND NOT is_archived RETURNING id",
                run_id, book_id,
            )
        return row is not None

    async def restore(self, book_id: UUID, run_id: UUID) -> bool:
        """BE-4b — the mirror of archive()."""
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                "UPDATE plan_run SET is_archived = false, updated_at = now() "
                "WHERE id = $1 AND book_id = $2 AND is_archived RETURNING id",
                run_id, book_id,
            )
        return row is not None

    async def list_for_book(
        self,
        book_id: UUID,
        *,
        limit: int = 20,
        cursor: str | None = None,
        include_archived: bool = False,
    ) -> tuple[list[PlanRun], str | None]:
        params: list[Any] = [book_id]
        where = ["book_id = $1"]
        if not include_archived:
            where.append("NOT is_archived")  # BE-4 — archived runs are hidden by default
        if cursor:
            try:
                ts_str, id_str = cursor.split("|", 1)
                ts = datetime.fromisoformat(ts_str)
                cid = UUID(id_str)
            except (ValueError, TypeError):
                ts, cid = None, None
            if ts is not None and cid is not None:
                params.extend([ts, cid])
                where.append(
                    f"(created_at, id) < (${len(params) - 1}, ${len(params)})"
                )
        params.append(min(max(limit, 1), 50))
        query = f"""
        SELECT {_SELECT_RUN} FROM plan_run
        WHERE {" AND ".join(where)}
        ORDER BY created_at DESC, id DESC
        LIMIT ${len(params)}
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, *params)
        runs = [_row_run(r) for r in rows]
        next_cursor: str | None = None
        if len(runs) == params[-1] and runs:
            last = runs[-1]
            if last.created_at is not None:
                next_cursor = f"{last.created_at.isoformat()}|{last.id}"
        return runs, next_cursor

    async def update_run(
        self,
        book_id: UUID,
        run_id: UUID,
        *,
        status: PlanRunStatus | None = None,
        active_job_id: UUID | None = ...,
        error_detail: str | None = ...,
        work_id: UUID | None = None,
        checkpoint_state: dict[str, Any] | None = None,
        # 27 PF-3 — the pass ledger. Written as a WHOLE object (the service reads-modifies-writes
        # one pass entry at a time); `None` means "leave it alone", never "clear it".
        pass_state: dict[str, Any] | None = None,
        genre_tags: list[str] | None = None,
        clear_error: bool = False,
    ) -> PlanRun | None:
        sets: list[str] = ["updated_at = now()"]
        params: list[Any] = [run_id, book_id]
        if status is not None:
            params.append(status)
            sets.append(f"status = ${len(params)}")
        if active_job_id is not ...:
            if active_job_id is None:
                sets.append("active_job_id = NULL")
            else:
                params.append(active_job_id)
                sets.append(f"active_job_id = ${len(params)}")
        if error_detail is not ...:
            if error_detail is None and not clear_error:
                pass
            elif error_detail is None:
                sets.append("error_detail = NULL")
            else:
                params.append(error_detail)
                sets.append(f"error_detail = ${len(params)}")
        elif clear_error:
            sets.append("error_detail = NULL")
        if work_id is not None:
            params.append(work_id)
            sets.append(f"work_id = ${len(params)}")
        if checkpoint_state is not None:
            params.append(_jsonb(checkpoint_state))
            sets.append(f"checkpoint_state = ${len(params)}::jsonb")
        if pass_state is not None:
            # A JSONB MERGE (`||`), not an overwrite. The passes are serialized today (PF-5 refuses
            # to run a pass while an upstream is stale), but the moment C2 fans them out, a
            # whole-object write would let two workers' read-modify-writes race and silently drop
            # one pass's ledger entry. `||` cannot lose a sibling key, and it is the same line.
            params.append(_jsonb(pass_state))
            sets.append(f"pass_state = COALESCE(pass_state, '{{}}'::jsonb) || ${len(params)}::jsonb")
        if genre_tags is not None:
            params.append(json.dumps(genre_tags))
            sets.append(f"genre_tags = ${len(params)}::jsonb")
        query = f"""
        UPDATE plan_run SET {", ".join(sets)}
        WHERE id = $1 AND book_id = $2
        RETURNING {_SELECT_RUN}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, *params)
        return _row_run(row) if row else None

    async def save_artifact(
        self,
        created_by: UUID,
        run_id: UUID,
        kind: PlanArtifactKind,
        content: dict[str, Any],
    ) -> PlanArtifact:
        query = f"""
        INSERT INTO plan_artifact (run_id, created_by, kind, content)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING {_SELECT_ARTIFACT.replace("a.", "")}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, run_id, created_by, kind, _jsonb(content),
            )
        return _row_artifact(row)

    async def latest_artifact(
        self,
        book_id: UUID,
        run_id: UUID,
        kind: PlanArtifactKind,
    ) -> PlanArtifact | None:
        # plan_artifact has no book_id column — its book scope is transitive
        # through the parent run join (OQ-3; worker-loaded-id parent scoping).
        query = f"""
        SELECT {_SELECT_ARTIFACT} FROM plan_artifact a
        JOIN plan_run r ON r.id = a.run_id
        WHERE a.run_id = $1 AND r.book_id = $2 AND a.kind = $3
        ORDER BY a.created_at DESC
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, book_id, kind)
        return _row_artifact(row) if row else None

    async def artifacts_by_ids(
        self, book_id: UUID, run_id: UUID, ids: list[UUID | str],
    ) -> dict[str, PlanArtifact]:
        """The pass runner's input resolver: fetch artifacts BY ID (PF-3's pointer rule), keyed by
        `str(id)`. Never "the latest of kind X" — pass 7 re-emits `scene_plan`, so a latest-by-kind
        read would hand it its own output as its input.

        Scoped through the parent run join, exactly like `latest_artifact`: `plan_artifact` has no
        `book_id`, so an id arriving from a worker's job input MUST be validated against the book
        that owns its run. An id that belongs to another book simply is not returned — the caller
        then sees a missing pointer and degrades, rather than reading across a tenancy boundary.
        """
        if not ids:
            return {}
        query = f"""
        SELECT {_SELECT_ARTIFACT} FROM plan_artifact a
        JOIN plan_run r ON r.id = a.run_id
        WHERE a.run_id = $1 AND r.book_id = $2 AND a.id = ANY($3::uuid[])
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, run_id, book_id, [UUID(str(i)) for i in ids])
        return {str(r["id"]): _row_artifact(r) for r in rows}

    async def latest_link_report(
        self, book_id: UUID, run_id: UUID, target: str,
    ) -> PlanArtifact | None:
        """The newest `link_report` FOR ONE TARGET ("skeleton" | "scene_plan").

        Both linkers emit kind `link_report`, so `latest_artifact(..., "link_report")` can hand the
        skeleton link the SCENE link's report — whose PF-11 version ledger holds only `scene:*` keys.
        The skeleton would then find no prior `arc:*`/`chapter:*` version, fall back to its
        no-prior sentinel, and overwrite every human edit on the next compile. Filtering on the
        report's own `target` is the fix, and it is one query.

        Book scope is transitive through the run join (OQ-3), exactly like `latest_artifact`.
        """
        query = f"""
        SELECT {_SELECT_ARTIFACT} FROM plan_artifact a
        JOIN plan_run r ON r.id = a.run_id
        WHERE a.run_id = $1 AND r.book_id = $2 AND a.kind = 'link_report'
          AND a.content ->> 'target' = $3
        ORDER BY a.created_at DESC
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, run_id, book_id, target)
        return _row_artifact(row) if row else None

    async def plan_state_for_book(self, book_id: UUID) -> dict[str, Any]:
        """"Does this book have an arc plan?" — ONE round-trip, book-keyed.

        Called once per chat turn (chat-service's per-turn plan probe), so it must
        stay a single cheap read: run_count + the latest run's status + a `spec`
        artifact EXISTS, all in one statement. NO N+1 (never list the runs then
        probe each one's artifacts) — the spec probe is an EXISTS over the
        `JOIN plan_run r ON r.id = a.run_id` book-scope gate every plan_artifact
        read must go through (plan_artifact carries no book_id of its own).

        `has_spec` is the meaningful signal: a run can exist as `pending`/`failed`
        with no spec artifact, which means there is NO arc plan yet. A book with no
        runs at all is NOT an error — it returns zeros (the caller maps it to 200).

        Index: `idx_plan_run_book_created (book_id, created_at DESC)` serves both
        the count and the latest-status read (the older `idx_plan_run_owner_book`
        leads with `created_by`, which these book-only filters cannot use);
        `idx_plan_artifact_run_kind (run_id, kind, …)` serves the EXISTS probe.
        """
        # BE-4 — the per-chat-turn probe must NOT count/report an archived run (all three
        # subqueries filter NOT is_archived).
        query = """
        SELECT
          (SELECT COUNT(*) FROM plan_run WHERE book_id = $1 AND NOT is_archived)::int AS run_count,
          (SELECT status FROM plan_run WHERE book_id = $1 AND NOT is_archived
             ORDER BY created_at DESC, id DESC LIMIT 1) AS latest_status,
          EXISTS (
            SELECT 1 FROM plan_artifact a
            JOIN plan_run r ON r.id = a.run_id
            WHERE r.book_id = $1 AND a.kind = 'spec' AND NOT r.is_archived
          ) AS has_spec
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, book_id)
        return {
            "run_count": int(row["run_count"] or 0),
            "latest_status": row["latest_status"],
            "has_spec": bool(row["has_spec"]),
        }

    async def list_artifact_refs(
        self, book_id: UUID, run_id: UUID,
    ) -> list[dict[str, Any]]:
        query = """
        SELECT DISTINCT ON (a.kind) a.kind, a.id AS artifact_id
        FROM plan_artifact a
        JOIN plan_run r ON r.id = a.run_id
        WHERE a.run_id = $1 AND r.book_id = $2
        ORDER BY a.kind, a.created_at DESC
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, run_id, book_id)
        return [{"kind": r["kind"], "artifact_id": r["artifact_id"]} for r in rows]
