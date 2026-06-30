"""F3 — per-entity ordinal-stamped canonical snapshot repository (§12.1).

Incremental Temporal Knowledge Architecture, milestone F3 (KG side). The
per-entity canonical snapshot is the bounded "who is this entity as of chapter
N" prose — DISTINCT from the book-STRUCTURAL summary tree
(``summary_chapters``/``parts``/``books``), which is chapter->part->book, not
per-entity. Aligned to the glossary ``canonical_snapshot`` versioned-cache model.

**INV-FACTS (the foundational invariant):** the snapshot is a LAZY, VERSIONED,
REGENERABLE CACHE — *never* truth. The facts in Neo4j are the only source of
truth; a snapshot may be dropped and rebuilt from facts without data loss. This
repo never accepts a "write the truth here" call; it only caches a fold result
and reports whether the cache is still valid.

**Cache identity / staleness (§12.1, B0/B3/F6):** a snapshot is keyed by
``(entity_id, attr_scope, as_of_ordinal, fold_algo_version)``. It is VALID iff:
  1. ``fold_algo_version == current`` (a strategy bump invalidates every row), AND
  2. no fact with ``valid_from_ordinal <= as_of_ordinal`` has an ``updated_at``
     newer than the snapshot's ``fact_coverage_at`` (a late / back-filled fact
     bumps the entity's max fact ``updated_at`` -> the snapshot goes stale ->
     rebuild-on-read; self-healing per B3).
The caller (the fold job) computes the current max-coverage timestamp from Neo4j
and passes it to ``get_valid_snapshot`` for the comparison — this repo owns only
the Postgres cache row, not the Neo4j fact read.

**Fold-failure state (B4):** ``fold_attempts`` + ``fold_failed_at`` +
``canonical_status`` give a poison fact an explicit backoff (mirrors the KG
``RETRY_BUDGET=3``); after ``MAX_FOLD_ATTEMPTS`` failures the row is
``'unbuildable'`` and the FE shows the structured facts instead of a broken card.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

__all__ = [
    "EntityCanonicalSnapshot",
    "EntityCanonicalSnapshotsRepo",
    "MAX_FOLD_ATTEMPTS",
    "snapshot_content_hash",
]

# B4 — mirror the KG summary RETRY_BUDGET=3: after this many consecutive fold
# failures the snapshot is quarantined ('unbuildable') so a poison fact can't
# re-fail every job-end forever. INV-FACTS guarantees the data is still readable
# from the facts; only the prose convenience is degraded.
MAX_FOLD_ATTEMPTS = 3


def snapshot_content_hash(content: str) -> str:
    """sha256 of the bounded prose — the translation-cache + diff-view key (D8).

    A re-ground that changes the content changes the hash -> translation cache
    miss -> re-translate; identical content -> hit (free). The FE diff (§7-4)
    recomputes both endpoints at the current fold_algo_version before diffing.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class EntityCanonicalSnapshot:
    """One row from ``entity_canonical_snapshots``."""

    id: UUID
    user_id: UUID
    project_id: UUID | None
    entity_id: str
    attr_scope: str
    as_of_ordinal: int
    content: str
    content_hash: str
    fold_algo_version: int
    fact_coverage_at: datetime | None
    canonical_status: str
    fold_attempts: int
    fold_failed_at: datetime | None
    built_at: datetime
    updated_at: datetime


class EntityCanonicalSnapshotsRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ── cache read (with the §12.1 staleness check) ────────────────────

    async def get_valid_snapshot(
        self,
        *,
        user_id: UUID,
        entity_id: str,
        as_of_ordinal: int,
        fold_algo_version: int,
        current_fact_coverage_at: datetime | None,
        attr_scope: str = "narrative",
    ) -> EntityCanonicalSnapshot | None:
        """Return the cached snapshot ONLY IF it is still valid (§12.1).

        Valid iff it exists at the exact ``(entity, scope, ordinal, algo_version)``
        key AND its ``fact_coverage_at`` is not older than
        ``current_fact_coverage_at`` (the max ``updated_at`` over the entity's
        facts with ``valid_from_ordinal <= as_of_ordinal``, read from Neo4j by the
        caller). A stale / version-mismatched / missing snapshot returns ``None``
        — a CACHE MISS, not an error: the caller rebuilds from facts (INV-FACTS).
        ``canonical_status='unbuildable'`` also returns ``None`` so the caller
        falls back to structured facts (B4).
        """
        row = await self._pool.fetchrow(
            """
            SELECT id, user_id, project_id, entity_id, attr_scope, as_of_ordinal,
                   content, content_hash, fold_algo_version, fact_coverage_at,
                   canonical_status, fold_attempts, fold_failed_at, built_at,
                   updated_at
            FROM entity_canonical_snapshots
            WHERE user_id = $1
              AND entity_id = $2
              AND attr_scope = $3
              AND as_of_ordinal = $4
              AND fold_algo_version = $5
            """,
            user_id, entity_id, attr_scope, as_of_ordinal, fold_algo_version,
        )
        if row is None:
            return None
        snap = self._row_to_snapshot(row)
        if snap.canonical_status == "unbuildable":
            return None
        # Staleness: a newer fact than the snapshot covered -> rebuild-on-read.
        # NULL coverage on either side is treated as "unknown -> stale" (fail to
        # the rebuild path, never serve a possibly-stale prose card).
        if current_fact_coverage_at is not None:
            if snap.fact_coverage_at is None or (
                snap.fact_coverage_at < current_fact_coverage_at
            ):
                return None
        return snap

    # ── cache write (after a successful fold) ──────────────────────────

    async def upsert_snapshot(
        self,
        *,
        user_id: UUID,
        project_id: UUID | None,
        entity_id: str,
        as_of_ordinal: int,
        content: str,
        fold_algo_version: int,
        fact_coverage_at: datetime | None,
        attr_scope: str = "narrative",
    ) -> EntityCanonicalSnapshot:
        """Persist a freshly-folded snapshot (the post-fold cache write).

        Upserts on the ``(entity, scope, ordinal, algo_version)`` identity — a
        re-fold at the SAME identity (e.g. a newer fact bumped coverage) overwrites
        the content + coverage and resets the failure state to ``'ready'``. A
        re-ground at a NEW ``as_of_ordinal`` / ``fold_algo_version`` is a new row
        (the row IS the version). ``content_hash`` is derived here so the
        translation/diff key always matches the stored content.
        """
        content_hash = snapshot_content_hash(content)
        row = await self._pool.fetchrow(
            """
            INSERT INTO entity_canonical_snapshots
              (user_id, project_id, entity_id, attr_scope, as_of_ordinal,
               content, content_hash, fold_algo_version, fact_coverage_at,
               canonical_status, fold_attempts, fold_failed_at, built_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'ready',0,NULL,now(),now())
            ON CONFLICT (entity_id, attr_scope, as_of_ordinal, fold_algo_version)
            DO UPDATE SET
              content          = EXCLUDED.content,
              content_hash     = EXCLUDED.content_hash,
              fact_coverage_at = EXCLUDED.fact_coverage_at,
              project_id       = EXCLUDED.project_id,
              canonical_status = 'ready',
              fold_attempts    = 0,
              fold_failed_at   = NULL,
              built_at         = now(),
              updated_at       = now()
            RETURNING id, user_id, project_id, entity_id, attr_scope, as_of_ordinal,
                      content, content_hash, fold_algo_version, fact_coverage_at,
                      canonical_status, fold_attempts, fold_failed_at, built_at,
                      updated_at
            """,
            user_id, project_id, entity_id, attr_scope, as_of_ordinal,
            content, content_hash, fold_algo_version, fact_coverage_at,
        )
        assert row is not None  # INSERT ... RETURNING always returns a row
        return self._row_to_snapshot(row)

    # ── dirty / failure state (the debounced-fold trigger + B4 backoff) ─

    async def mark_dirty(
        self,
        *,
        user_id: UUID,
        entity_id: str,
        attr_scope: str = "narrative",
    ) -> int:
        """Flag every snapshot row for an entity ``dirty`` so the next fold batch
        rebuilds it (the ``canonical_dirty`` debounce trigger, §3.3). Returns the
        number of rows flagged. A row already ``unbuildable`` is left alone (its
        backoff governs it, not the dirty flag)."""
        result = await self._pool.execute(
            """
            UPDATE entity_canonical_snapshots
            SET canonical_status = 'dirty', updated_at = now()
            WHERE user_id = $1 AND entity_id = $2 AND attr_scope = $3
              AND canonical_status <> 'unbuildable'
            """,
            user_id, entity_id, attr_scope,
        )
        # asyncpg execute returns a status string like "UPDATE 3"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def record_fold_failure(
        self,
        *,
        user_id: UUID,
        entity_id: str,
        as_of_ordinal: int,
        fold_algo_version: int,
        attr_scope: str = "narrative",
    ) -> str:
        """Record a fold failure for one snapshot identity (B4 backoff).

        Increments ``fold_attempts``; at ``MAX_FOLD_ATTEMPTS`` the row is
        quarantined ``'unbuildable'`` (stop re-folding; FE shows structured facts).
        If the row doesn't exist yet (the first fold of a never-built snapshot
        failed), inserts a placeholder failure row so the backoff still counts.
        Returns the resulting ``canonical_status``.
        """
        row = await self._pool.fetchrow(
            """
            INSERT INTO entity_canonical_snapshots
              (user_id, project_id, entity_id, attr_scope, as_of_ordinal,
               content, content_hash, fold_algo_version, fact_coverage_at,
               canonical_status, fold_attempts, fold_failed_at, built_at, updated_at)
            VALUES ($1, NULL, $2, $3, $4, '', $5, $6, NULL,
                    CASE WHEN 1 >= $7 THEN 'unbuildable' ELSE 'dirty' END,
                    1, now(), now(), now())
            ON CONFLICT (entity_id, attr_scope, as_of_ordinal, fold_algo_version)
            DO UPDATE SET
              fold_attempts    = entity_canonical_snapshots.fold_attempts + 1,
              fold_failed_at   = now(),
              canonical_status = CASE
                WHEN entity_canonical_snapshots.fold_attempts + 1 >= $7
                THEN 'unbuildable' ELSE 'dirty' END,
              updated_at       = now()
            RETURNING canonical_status
            """,
            user_id, entity_id, attr_scope, as_of_ordinal,
            snapshot_content_hash(""), fold_algo_version, MAX_FOLD_ATTEMPTS,
        )
        assert row is not None
        return str(row["canonical_status"])

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_snapshot(row: asyncpg.Record) -> EntityCanonicalSnapshot:
        return EntityCanonicalSnapshot(
            id=row["id"],
            user_id=row["user_id"],
            project_id=row["project_id"],
            entity_id=row["entity_id"],
            attr_scope=row["attr_scope"],
            as_of_ordinal=row["as_of_ordinal"],
            content=row["content"],
            content_hash=row["content_hash"],
            fold_algo_version=row["fold_algo_version"],
            fact_coverage_at=row["fact_coverage_at"],
            canonical_status=row["canonical_status"],
            fold_attempts=row["fold_attempts"],
            fold_failed_at=row["fold_failed_at"],
            built_at=row["built_at"],
            updated_at=row["updated_at"],
        )
