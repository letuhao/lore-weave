"""P3 — Per-level summary repository (chapter/part/book).

Spec: docs/specs/2026-05-23-p3-hierarchical-reduce.md §D4 + §D3 M5.

3 tables — summary_chapters / summary_parts / summary_books — each with
UNIQUE (level_id, embedding_model_uuid) so re-extraction with a different
embedding_model creates a NEW row (matches H1 per-model index family).

M5 fix: concurrent extraction jobs on same book race on UNIQUE; this
repo catches UniqueViolationError and verifies md5 match before treating
as cache-equivalent.

Spec D10 cache: summary_input_md5 includes
  hash(joined_child_texts + level + extractor_version + model_ref)
— caller (summary_processor) computes the md5 + passes it; repo just
persists. Re-extraction with same md5 = cache hit (no LLM call).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

__all__ = [
    "Level",
    "LevelSummary",
    "LevelSummariesRepo",
    "UpsertOutcome",
]


Level = Literal["chapter", "part", "book"]

# Table-name + level-id-column lookup per level.
_LEVEL_TABLE: dict[Level, tuple[str, str]] = {
    "chapter": ("summary_chapters", "chapter_id"),
    "part": ("summary_parts", "part_id"),
    "book": ("summary_books", "book_id"),
}


@dataclass
class LevelSummary:
    """One row from summary_chapters / summary_parts / summary_books."""
    id: UUID
    level: Level
    level_id: UUID                # chapter_id | part_id | book_id
    book_id: UUID
    summary_text: str
    summary_input_md5: str
    embedding_dimension: int
    embedding_model_uuid: str


@dataclass
class UpsertOutcome:
    """Result of upsert_summary().

    cache_hit:
      - True  when an existing row already matches summary_input_md5 →
              caller skips LLM call entirely.
      - False when a fresh row was written → caller already called LLM
              (this is the post-LLM persistence path).
    race_winner:
      - True  when this caller's INSERT succeeded.
      - False when a concurrent caller already wrote a matching row
              first (UniqueViolation + md5 match — M5 cache-equivalent).
    """
    cache_hit: bool
    race_winner: bool
    summary_id: UUID


class LevelSummariesRepo:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    # ── Cache check (pre-LLM) ──────────────────────────────────────────

    async def find_cached(
        self,
        *,
        level: Level,
        level_id: UUID,
        embedding_model_uuid: str,
        summary_input_md5: str,
    ) -> LevelSummary | None:
        """Return existing row IF (level_id, embedding_model_uuid) matches
        AND its summary_input_md5 equals the passed md5.

        Used by summary_processor BEFORE the LLM call to skip work on
        unchanged content (D10 re-run cheapness). Different md5 = different
        input → cache miss → caller must call LLM + upsert.
        """
        table, level_col = _LEVEL_TABLE[level]
        row = await self._pool.fetchrow(
            f"""
            SELECT id, {level_col} AS level_id, book_id, summary_text,
                   summary_input_md5, embedding_dimension, embedding_model_uuid
            FROM {table}
            WHERE {level_col} = $1
              AND embedding_model_uuid = $2
            """,
            level_id,
            embedding_model_uuid,
        )
        if row is None:
            return None
        if row["summary_input_md5"] != summary_input_md5:
            return None  # cache miss — input changed
        return _row_to_summary(row, level)

    # ── Write (post-LLM) ───────────────────────────────────────────────

    async def upsert_summary(
        self,
        *,
        level: Level,
        level_id: UUID,
        book_id: UUID,
        summary_text: str,
        summary_input_md5: str,
        embedding_dimension: int,
        embedding_model_uuid: str,
    ) -> UpsertOutcome:
        """Insert a new summary row OR (per M5) gracefully handle a
        concurrent UniqueViolation.

        Race semantics:
          - Happy path: INSERT succeeds → race_winner=True, cache_hit=False.
          - Race + md5 match: UniqueViolation → SELECT existing row,
            confirm md5 matches → race_winner=False, cache_hit=True
            (treat as cache-equivalent; LLM cost was wasted but no
            corruption).
          - Race + md5 mismatch: UniqueViolation → SELECT existing,
            md5 differs → log warning + leave race-winner's row
            (race winner has different summary; ours is dropped).
        """
        table, level_col = _LEVEL_TABLE[level]
        try:
            row = await self._pool.fetchrow(
                f"""
                INSERT INTO {table}
                  ({level_col}, book_id, summary_text, summary_input_md5,
                   embedding_dimension, embedding_model_uuid)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                level_id, book_id, summary_text, summary_input_md5,
                embedding_dimension, embedding_model_uuid,
            )
            return UpsertOutcome(
                cache_hit=False, race_winner=True, summary_id=row["id"],
            )
        except asyncpg.UniqueViolationError:
            # M5: concurrent writer beat us. Verify md5 match → treat as
            # cache-equivalent (no further action). If md5 differs, log
            # + accept the race winner's row.
            existing = await self._pool.fetchrow(
                f"""
                SELECT id, summary_input_md5
                FROM {table}
                WHERE {level_col} = $1 AND embedding_model_uuid = $2
                """,
                level_id, embedding_model_uuid,
            )
            if existing is None:
                # Bizarre: UniqueViolation fired but row no longer exists
                # (race + delete?). Re-raise as runtime error.
                raise RuntimeError(
                    f"UniqueViolation but no row for {level}={level_id} "
                    f"embed={embedding_model_uuid}"
                )
            if existing["summary_input_md5"] != summary_input_md5:
                logger.warning(
                    "level_summaries md5 mismatch on UniqueViolation: "
                    "level=%s level_id=%s our_md5=%s existing_md5=%s",
                    level, level_id, summary_input_md5[:8],
                    existing["summary_input_md5"][:8],
                )
            return UpsertOutcome(
                cache_hit=True, race_winner=False, summary_id=existing["id"],
            )

    # ── Read helpers for Mode-3 router + summary aggregation ──────────

    async def list_by_book(
        self, *, book_id: UUID, level: Level, embedding_model_uuid: str,
    ) -> list[LevelSummary]:
        """Return all summaries for a book at a given level.

        Used by:
          - summary_processor at part level (load children chapter summaries)
          - summary_processor at book level (load children part summaries)
          - Mode-3 retrieval blend (when index query needs raw text alongside vector)
        """
        table, level_col = _LEVEL_TABLE[level]
        rows = await self._pool.fetch(
            f"""
            SELECT id, {level_col} AS level_id, book_id, summary_text,
                   summary_input_md5, embedding_dimension, embedding_model_uuid
            FROM {table}
            WHERE book_id = $1 AND embedding_model_uuid = $2
            ORDER BY {level_col}
            """,
            book_id, embedding_model_uuid,
        )
        return [_row_to_summary(r, level) for r in rows]

    async def count_by_book(
        self, *, book_id: UUID, level: Level, embedding_model_uuid: str,
    ) -> int:
        """Used by summary_processor's D9 defensive check at part/book level —
        verify expected_children == actual_summary_rows before generating
        a higher-level summary.
        """
        table, level_col = _LEVEL_TABLE[level]
        row = await self._pool.fetchrow(
            f"SELECT count(*) AS n FROM {table} "
            f"WHERE book_id = $1 AND embedding_model_uuid = $2",
            book_id, embedding_model_uuid,
        )
        return int(row["n"]) if row else 0


def _row_to_summary(row: asyncpg.Record, level: Level) -> LevelSummary:
    return LevelSummary(
        id=row["id"],
        level=level,
        level_id=row["level_id"],
        book_id=row["book_id"],
        summary_text=row["summary_text"],
        summary_input_md5=row["summary_input_md5"],
        embedding_dimension=row["embedding_dimension"],
        embedding_model_uuid=row["embedding_model_uuid"],
    )
