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
from app.db.models import ScopeType, Summary, SummaryVersion
from app.db.repositories import VersionMismatchError

_SELECT_COLS = """
  summary_id, user_id, scope_type, scope_id, content, token_count,
  version, created_at, updated_at
"""

# D-K8-01: columns projected for summary-version responses. Mirrors
# the SummaryVersion Pydantic model exactly.
_VERSION_SELECT_COLS = """
  version_id, summary_id, user_id, version, content, token_count,
  created_at, edit_source
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

    # K7d export safety belt. Mirrors ProjectsRepo.EXPORT_HARD_CAP:
    # the export route refuses with 507 rather than silently truncating,
    # which would produce an incomplete GDPR bundle and quietly violate
    # the regulation. Sized an order of magnitude above the Memory-page
    # cap because one user can legitimately accumulate project + session
    # summaries across many scopes over time.
    EXPORT_HARD_CAP = 10_000

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

    async def list_all_for_user(self, user_id: UUID) -> list[Summary]:
        """Return every summary row owned by `user_id` for K7d export.

        Capped at `EXPORT_HARD_CAP + 1` so the export route can detect
        overflow and fail noisily with 507 instead of producing a
        truncated GDPR bundle. Ordering is not meaningful for export —
        we sort by (scope_type, scope_id, updated_at) only so the JSON
        output is deterministic across identical exports, which makes
        import / merge / diff tools easier to write.
        """
        query = f"""
        SELECT {_SELECT_COLS}
        FROM knowledge_summaries
        WHERE user_id = $1
        ORDER BY scope_type, scope_id, updated_at
        LIMIT {self.EXPORT_HARD_CAP + 1}
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
        expected_version: int | None = None,
    ) -> Summary:
        """Insert or update a summary.

        D-K8-03: when ``expected_version`` is provided the ON CONFLICT
        UPDATE branch gates on ``version = $6`` so concurrent writers
        cannot silently clobber each other. The INSERT branch (first
        save, no prior row) always succeeds regardless — the client
        couldn't have obtained an ETag before the row existed. Raises
        ``VersionMismatchError`` on conflict.

        D-K8-01: every successful UPDATE also captures the PRE-update
        row (content + version + token_count) into
        knowledge_summary_versions inside the same transaction so
        the history table stays consistent with the parent even
        under concurrency. INSERT path writes no history row — v1
        is the original, not a "previous" state.
        """
        token_count = _estimate_tokens(content)
        version_predicate = (
            f" WHERE knowledge_summaries.version = ${6}"
            if expected_version is not None
            else ""
        )
        # The upsert + history insert must be transactional so a
        # concurrent writer can't sneak in between the history row
        # and the parent bump.
        insert_query = f"""
        INSERT INTO knowledge_summaries
          (user_id, scope_type, scope_id, content, token_count)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, scope_type, scope_id) DO UPDATE
          SET content = EXCLUDED.content,
              token_count = EXCLUDED.token_count,
              version = knowledge_summaries.version + 1,
              updated_at = now()
          {version_predicate}
        RETURNING {_SELECT_COLS}, (xmax <> 0) AS was_update
        """
        params: list[object] = [user_id, scope_type, scope_id, content, token_count]
        if expected_version is not None:
            params.append(expected_version)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Capture pre-update state + lock the row. FOR UPDATE
                # serialises concurrent upserts so one side sees
                # pre.version advance and produces a VersionMismatch
                # cleanly instead of racing.
                pre = await conn.fetchrow(
                    """
                    SELECT summary_id, version, content, token_count
                    FROM knowledge_summaries
                    WHERE user_id = $1
                      AND scope_type = $2
                      AND scope_id IS NOT DISTINCT FROM $3
                    FOR UPDATE
                    """,
                    user_id, scope_type, scope_id,
                )
                row = await conn.fetchrow(insert_query, *params)
                if pre is not None and row is not None:
                    # D-K8-01: write the pre-update state as a
                    # history row. INSERT path (pre is None) skips
                    # this — there's nothing to archive.
                    await conn.execute(
                        """
                        INSERT INTO knowledge_summary_versions
                          (summary_id, user_id, version, content, token_count, edit_source)
                        VALUES ($1, $2, $3, $4, $5, 'manual')
                        """,
                        pre["summary_id"],
                        user_id,
                        pre["version"],
                        pre["content"],
                        pre["token_count"],
                    )
                # If row is None while we hold a FOR UPDATE lock on
                # `pre`, the only cause is a version-predicate miss
                # on the UPDATE branch (because pre existed, INSERT
                # would have been blocked by the unique constraint).
                # Both cases below do NOT bump the version and do
                # NOT write history.

        if row is not None:
            result = Summary.model_validate(dict(row))
            _invalidate_cache(user_id, scope_type, scope_id)
            return result

        # Version mismatch. `pre` holds the state at the moment we
        # took the lock, which is the truth the caller needs in its
        # 412 envelope. If pre is also None, something really odd
        # happened — raise RuntimeError so it doesn't turn into a
        # silent success path.
        if pre is None:
            raise RuntimeError(
                "summaries.upsert returned 0 rows with no prior row",
            )
        current = await self.get(user_id, scope_type, scope_id)
        if current is None:
            # The row was deleted between our lock release and the
            # follow-up SELECT. Treat as mismatch with the stale
            # pre state — the client will refetch and see 404 on
            # its next read.
            raise RuntimeError(
                "summaries.upsert: row disappeared after FOR UPDATE",
            )
        raise VersionMismatchError(current)

    async def upsert_project_scoped(
        self,
        user_id: UUID,
        project_id: UUID,
        content: str,
        expected_version: int | None = None,
    ) -> Summary | None:
        """Upsert a project-scope summary atomically with an ownership check.

        Returns the new Summary on success, or None if the user does not
        own `project_id` (cross-user OR nonexistent — the router cannot
        distinguish these per KSA §6.4 anti-leak rules).

        The ownership check lives in a CTE (`WITH owned AS ...`) so the
        INSERT is gated on `EXISTS(SELECT 1 FROM owned)`; a non-owner
        inserts zero rows and the RETURNING yields nothing, which we
        map to None.

        D-K8-03: version-gated UPDATE branch; 0-row result
        disambiguated via a follow-up get() (raises
        VersionMismatchError on mismatch, returns None on ownership
        failure).

        D-K8-01: every successful update writes a history row into
        knowledge_summary_versions inside the same transaction. The
        pre-update fetch doubles as a FOR UPDATE lock so concurrent
        writers serialise. INSERT path writes no history — v1 is the
        original, nothing to archive.
        """
        token_count = _estimate_tokens(content)
        version_predicate = (
            f" WHERE knowledge_summaries.version = ${5}"
            if expected_version is not None
            else ""
        )
        upsert_query = f"""
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
            {version_predicate}
          RETURNING {_SELECT_COLS}
        )
        SELECT * FROM upserted
        """
        params: list[object] = [user_id, project_id, content, token_count]
        if expected_version is not None:
            params.append(expected_version)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Pre-update lock + state capture. Note: if the user
                # doesn't own the project, this SELECT returns None
                # whether or not a summary row exists, because the
                # row-filter on user_id matches the ownership model.
                # That's safe — the CTE ownership check below is the
                # real gate.
                pre = await conn.fetchrow(
                    """
                    SELECT summary_id, version, content, token_count
                    FROM knowledge_summaries
                    WHERE user_id = $1
                      AND scope_type = 'project'
                      AND scope_id = $2
                    FOR UPDATE
                    """,
                    user_id, project_id,
                )
                row = await conn.fetchrow(upsert_query, *params)
                if pre is not None and row is not None:
                    # D-K8-01: write pre-update state as history.
                    await conn.execute(
                        """
                        INSERT INTO knowledge_summary_versions
                          (summary_id, user_id, version, content, token_count, edit_source)
                        VALUES ($1, $2, $3, $4, $5, 'manual')
                        """,
                        pre["summary_id"],
                        user_id,
                        pre["version"],
                        pre["content"],
                        pre["token_count"],
                    )

        if row is not None:
            result = Summary.model_validate(dict(row))
            _invalidate_cache(user_id, "project", project_id)
            return result

        if expected_version is None:
            # Legacy path: 0 rows means ownership failure.
            return None

        # With expected_version set, 0 rows could be either ownership
        # failure OR version mismatch. Follow-up SELECT disambiguates.
        current = await self.get(user_id, "project", project_id)
        if current is None:
            return None
        raise VersionMismatchError(current)

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

    # ─── D-K8-01: summary version history ───────────────────────────

    # K7d-style safety cap: refuse to return more than this many
    # history rows from a single list call. The UI pages 50 at a
    # time in Track 1; the cap is higher so future iterations can
    # bump limit without touching the repo.
    VERSIONS_LIST_HARD_CAP = 200

    async def list_versions(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        *,
        limit: int = 50,
    ) -> list[SummaryVersion]:
        """D-K8-01: list history rows newest-first for a given
        summary scope. Filters by user_id on the denormalised column
        so cross-user access returns an empty list by construction.

        The summary row itself is NOT included in the response —
        the current state is served by `get()`. This endpoint only
        returns ARCHIVED versions (pre-update snapshots).
        """
        effective_limit = max(1, min(limit, self.VERSIONS_LIST_HARD_CAP))
        query = f"""
        SELECT {_VERSION_SELECT_COLS}
        FROM knowledge_summary_versions
        WHERE user_id = $1
          AND summary_id IN (
            SELECT summary_id FROM knowledge_summaries
            WHERE user_id = $1
              AND scope_type = $2
              AND scope_id IS NOT DISTINCT FROM $3
          )
        ORDER BY version DESC
        LIMIT {effective_limit}
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, scope_type, scope_id)
        return [SummaryVersion.model_validate(dict(r)) for r in rows]

    async def get_version(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        version: int,
    ) -> SummaryVersion | None:
        """D-K8-01: fetch a specific history row for preview.
        Returns None if (a) the version doesn't exist, (b) it
        belongs to another user (blocked by the user_id filter
        that joins through knowledge_summaries), or (c) the scope
        doesn't match the row's parent summary."""
        query = f"""
        SELECT {_VERSION_SELECT_COLS}
        FROM knowledge_summary_versions
        WHERE user_id = $1
          AND version = $4
          AND summary_id IN (
            SELECT summary_id FROM knowledge_summaries
            WHERE user_id = $1
              AND scope_type = $2
              AND scope_id IS NOT DISTINCT FROM $3
          )
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id, scope_type, scope_id, version)
        return SummaryVersion.model_validate(dict(row)) if row else None

    async def rollback_to(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        target_version: int,
        expected_version: int,
    ) -> Summary:
        """D-K8-01: create a NEW version whose content is a copy of
        `target_version`. Never rewinds the version counter — the
        rollback produces (current_version + 1) with the old
        content, and the pre-rollback row is itself archived to
        history with `edit_source='rollback'`.

        Requires ``expected_version`` (strict If-Match semantics) so
        a stale History panel can't accidentally roll forward over a
        concurrent edit. Raises ``VersionMismatchError`` on conflict.
        Raises ``LookupError`` if the target version doesn't exist
        (router maps to 404).
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # 1. Lock the current row and fetch its state.
                pre = await conn.fetchrow(
                    """
                    SELECT summary_id, version, content, token_count
                    FROM knowledge_summaries
                    WHERE user_id = $1
                      AND scope_type = $2
                      AND scope_id IS NOT DISTINCT FROM $3
                    FOR UPDATE
                    """,
                    user_id, scope_type, scope_id,
                )
                if pre is None:
                    raise LookupError("summary_not_found")
                if pre["version"] != expected_version:
                    raise VersionMismatchError(
                        Summary.model_validate(
                            dict(
                                await conn.fetchrow(
                                    f"SELECT {_SELECT_COLS} FROM knowledge_summaries "
                                    "WHERE summary_id = $1",
                                    pre["summary_id"],
                                )
                            )
                        )
                    )

                # 2. Fetch the target history row.
                target = await conn.fetchrow(
                    """
                    SELECT content, token_count
                    FROM knowledge_summary_versions
                    WHERE summary_id = $1
                      AND user_id = $2
                      AND version = $3
                    """,
                    pre["summary_id"], user_id, target_version,
                )
                if target is None:
                    raise LookupError("target_version_not_found")

                # 3. Archive the pre-rollback row as history with
                #    edit_source='rollback'. The AUDIT TRAIL records
                #    *which* row was displaced by the rollback.
                await conn.execute(
                    """
                    INSERT INTO knowledge_summary_versions
                      (summary_id, user_id, version, content, token_count, edit_source)
                    VALUES ($1, $2, $3, $4, $5, 'rollback')
                    """,
                    pre["summary_id"],
                    user_id,
                    pre["version"],
                    pre["content"],
                    pre["token_count"],
                )

                # 4. Overwrite the live row with the target content,
                #    bumping version.
                updated = await conn.fetchrow(
                    f"""
                    UPDATE knowledge_summaries
                    SET content = $2,
                        token_count = $3,
                        version = version + 1,
                        updated_at = now()
                    WHERE summary_id = $1
                    RETURNING {_SELECT_COLS}
                    """,
                    pre["summary_id"],
                    target["content"],
                    target["token_count"],
                )

        assert updated is not None
        result = Summary.model_validate(dict(updated))
        _invalidate_cache(user_id, scope_type, scope_id)
        return result
