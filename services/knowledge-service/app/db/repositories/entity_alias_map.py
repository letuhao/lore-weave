"""C17 — entity_alias_map repository.

Redirect index for post-merge alias resolution. The extractor's
``canonical_id`` is a SHA hash of the entity name (see
``app/db/neo4j_repos/canonical.py``); without a redirect table, every
re-extraction of a merged-away alias resurrects the source as a brand-
new entity.

Lookup key mirrors ``entity_canonical_id``:
``(user_id, project_scope, kind, canonical_alias)`` where
``project_scope`` is the project_id-as-text or the literal ``'global'``.
Resolver consults this table BEFORE the SHA hash; on hit, MERGE uses
the redirect target's id directly.

See ADR ``docs/03_planning/KNOWLEDGE_SERVICE_ENTITY_ALIAS_MAP_ADR.md``
for the design rationale, rejected alternatives, and the closing
checklist.
"""

from __future__ import annotations

from typing import Iterable, Literal
from uuid import UUID

import asyncpg

__all__ = ["EntityAliasMapRepo", "AliasReason"]


# Closed Literal mirroring the migrate.py CHECK constraint. Adding a
# new value requires coordinated update of: migrate.py CHECK, this
# Literal, any caller passing a hard-coded reason value.
AliasReason = Literal["merge", "backfill"]


class EntityAliasMapRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def lookup(
        self,
        user_id: UUID,
        project_scope: str,
        kind: str,
        canonical_alias: str,
    ) -> str | None:
        """Return ``target_entity_id`` if alias is registered, else None.

        Single PK index seek — sub-millisecond at any conceivable scale.
        Empty/whitespace canonical_alias is a defensive None (extraction
        canonicalization should not produce empties, but a
        crash-into-this-helper would otherwise hit the PK NOT NULL
        constraint and 500)."""
        if not canonical_alias:
            return None
        row = await self._pool.fetchrow(
            """
            SELECT target_entity_id
            FROM entity_alias_map
            WHERE user_id = $1
              AND project_scope = $2
              AND kind = $3
              AND canonical_alias = $4
            """,
            user_id, project_scope, kind, canonical_alias,
        )
        return row["target_entity_id"] if row is not None else None

    async def record_merge(
        self,
        user_id: UUID,
        project_scope: str,
        kind: str,
        canonical_alias: str,
        target_entity_id: str,
        source_entity_id: str | None,
    ) -> None:
        """Idempotent INSERT ... ON CONFLICT DO NOTHING.

        ON CONFLICT is explicitly DO NOTHING (not UPDATE): once an
        alias is mapped, a second-merge attempt for the same
        ``(user, scope, kind, alias)`` must NOT silently overwrite the
        first redirect. The expected pattern is ``repoint_target`` for
        chain-merge updates."""
        if not canonical_alias:
            return
        await self._pool.execute(
            """
            INSERT INTO entity_alias_map
                (user_id, project_scope, kind, canonical_alias,
                 target_entity_id, source_entity_id, reason)
            VALUES ($1, $2, $3, $4, $5, $6, 'merge')
            ON CONFLICT (user_id, project_scope, kind, canonical_alias)
                DO NOTHING
            """,
            user_id, project_scope, kind, canonical_alias,
            target_entity_id, source_entity_id,
        )

    async def list_for_entity(
        self,
        target_entity_id: str,
    ) -> list[dict]:
        """Reverse lookup — every alias redirecting to this entity.

        Used by FE display ("3 aliases redirect to this entity") and
        backfill audit. Hits ``idx_entity_alias_map_target``."""
        rows = await self._pool.fetch(
            """
            SELECT user_id, project_scope, kind, canonical_alias,
                   source_entity_id, reason, created_at
            FROM entity_alias_map
            WHERE target_entity_id = $1
            ORDER BY created_at DESC
            """,
            target_entity_id,
        )
        return [dict(r) for r in rows]

    async def bulk_backfill(
        self,
        rows: Iterable[tuple[UUID, str, str, str, str]],
    ) -> int:
        """Bulk INSERT with ``reason='backfill'``, ON CONFLICT DO NOTHING.

        Each tuple: ``(user_id, project_scope, kind, canonical_alias,
        target_entity_id)`` — backfill cannot reconstruct source_entity_id
        so it stays NULL. Returns count of newly-inserted rows.

        Used by ``scripts/backfill_entity_alias_map.py``. ON CONFLICT
        means the script is safe to re-run (idempotent), and a partial
        backfill that's interrupted by a crash can resume without
        creating duplicates."""
        records = [
            (uid, ps, kd, ca, tid, None, "backfill")
            for (uid, ps, kd, ca, tid) in rows
            if ca  # skip empty canonical_alias defensively
        ]
        if not records:
            return 0
        async with self._pool.acquire() as conn:
            # Use COPY-style executemany via prepared INSERT; asyncpg
            # has no native bulk insert, but executemany over an
            # ON-CONFLICT-DO-NOTHING is fast enough at hobby scale.
            inserted = 0
            for rec in records:
                status = await conn.execute(
                    """
                    INSERT INTO entity_alias_map
                        (user_id, project_scope, kind, canonical_alias,
                         target_entity_id, source_entity_id, reason)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, project_scope, kind, canonical_alias)
                        DO NOTHING
                    """,
                    *rec,
                )
                # asyncpg returns "INSERT 0 N" — N is rows actually inserted.
                if status.startswith("INSERT 0 1"):
                    inserted += 1
            return inserted

    async def repoint_target(
        self,
        user_id: UUID,
        old_target_entity_id: str,
        new_target_entity_id: str,
    ) -> int:
        """REVIEW-DESIGN catch — chain-merge re-point.

        When user merges B into C and B was previously a target (because
        user earlier merged A into B), the existing ``A→B`` row would
        point at the now-deleted source.id. Re-point every redirect
        whose ``target = $old_target`` onto ``$new_target`` in one SQL
        statement so multi-step merge chains stay consistent.

        Why not chase the chain at read time: every extraction read
        would multiply Postgres round-trips, and a data-corruption-
        induced cycle would loop forever. One UPDATE on the rare write
        path is cheaper and self-healing.

        Returns rowcount for ops logging."""
        if old_target_entity_id == new_target_entity_id:
            return 0
        status = await self._pool.execute(
            """
            UPDATE entity_alias_map
               SET target_entity_id = $1
             WHERE user_id = $2
               AND target_entity_id = $3
            """,
            new_target_entity_id, user_id, old_target_entity_id,
        )
        # asyncpg returns "UPDATE N".
        try:
            return int(status.split()[-1])
        except (ValueError, IndexError):
            return 0
