"""P3 — tests for LevelSummariesRepo (D4 + M5 UniqueViolation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from app.db.repositories.level_summaries import (
    LevelSummariesRepo,
    LevelSummary,
    UpsertOutcome,
)


def _record(level_id, book_id, md5="md5-a", text="A summary text long enough."):
    """Build a mocked asyncpg.Record-like dict for tests."""
    return {
        "id": uuid4(),
        "level_id": level_id,
        "book_id": book_id,
        "summary_text": text,
        "summary_input_md5": md5,
        "embedding_dimension": 1024,
        "embedding_model_uuid": "embed-uuid",
    }


async def test_find_cached_md5_match_returns_summary():
    pool = MagicMock()
    book = uuid4()
    chapter = uuid4()
    pool.fetchrow = AsyncMock(return_value=_record(level_id=chapter, book_id=book))
    repo = LevelSummariesRepo(pool)
    out = await repo.find_cached(
        level="chapter", level_id=chapter,
        embedding_model_uuid="embed-uuid", summary_input_md5="md5-a",
    )
    assert isinstance(out, LevelSummary)
    assert out.level_id == chapter


async def test_find_cached_md5_mismatch_returns_none():
    """Existing row but md5 differs → cache miss (input changed)."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=_record(uuid4(), uuid4(), md5="md5-old"))
    repo = LevelSummariesRepo(pool)
    out = await repo.find_cached(
        level="chapter", level_id=uuid4(),
        embedding_model_uuid="embed-uuid",
        summary_input_md5="md5-NEW",
    )
    assert out is None


async def test_find_cached_no_row_returns_none():
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    repo = LevelSummariesRepo(pool)
    out = await repo.find_cached(
        level="chapter", level_id=uuid4(),
        embedding_model_uuid="embed-uuid", summary_input_md5="md5",
    )
    assert out is None


async def test_upsert_summary_happy_path_returns_race_winner_true():
    pool = MagicMock()
    new_id = uuid4()
    pool.fetchrow = AsyncMock(return_value={"id": new_id})
    repo = LevelSummariesRepo(pool)
    outcome = await repo.upsert_summary(
        level="chapter", level_id=uuid4(), book_id=uuid4(),
        summary_text="text", summary_input_md5="m",
        embedding_dimension=1024, embedding_model_uuid="e",
    )
    assert outcome.race_winner is True
    assert outcome.cache_hit is False
    assert outcome.summary_id == new_id


async def test_upsert_summary_unique_violation_with_md5_match_treats_as_cache_hit():
    """M5: concurrent writer beat us; md5 matches → cache-equivalent (race loser)."""
    pool = MagicMock()
    existing_id = uuid4()

    # First call (INSERT) raises UniqueViolationError; second (SELECT) returns
    # existing row with matching md5.
    insert_call_count = 0

    async def fetchrow_side_effect(*args, **kwargs):
        nonlocal insert_call_count
        insert_call_count += 1
        if insert_call_count == 1:
            raise asyncpg.UniqueViolationError("dup")
        return {"id": existing_id, "summary_input_md5": "md5-X"}

    pool.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    repo = LevelSummariesRepo(pool)
    outcome = await repo.upsert_summary(
        level="chapter", level_id=uuid4(), book_id=uuid4(),
        summary_text="text", summary_input_md5="md5-X",  # matches existing
        embedding_dimension=1024, embedding_model_uuid="e",
    )
    assert outcome.race_winner is False
    assert outcome.cache_hit is True
    assert outcome.summary_id == existing_id


async def test_upsert_summary_unique_violation_with_md5_mismatch_accepts_race_winner_row():
    """M5: race + md5 differs → log warning + accept race winner; return cache_hit=True."""
    pool = MagicMock()
    existing_id = uuid4()
    call_count = 0

    async def fetchrow_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise asyncpg.UniqueViolationError("dup")
        return {"id": existing_id, "summary_input_md5": "md5-DIFFERENT"}

    pool.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    repo = LevelSummariesRepo(pool)
    outcome = await repo.upsert_summary(
        level="chapter", level_id=uuid4(), book_id=uuid4(),
        summary_text="text", summary_input_md5="md5-ours",
        embedding_dimension=1024, embedding_model_uuid="e",
    )
    assert outcome.race_winner is False
    assert outcome.cache_hit is True  # accept race winner
    assert outcome.summary_id == existing_id


async def test_count_by_book_returns_int():
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"n": 7})
    repo = LevelSummariesRepo(pool)
    n = await repo.count_by_book(
        book_id=uuid4(), level="chapter", embedding_model_uuid="e",
    )
    assert n == 7


async def test_list_by_book_returns_list_of_summaries():
    pool = MagicMock()
    book = uuid4()
    pool.fetch = AsyncMock(return_value=[
        _record(level_id=uuid4(), book_id=book, md5="m1", text="summary one. body."),
        _record(level_id=uuid4(), book_id=book, md5="m2", text="summary two. body."),
    ])
    repo = LevelSummariesRepo(pool)
    out = await repo.list_by_book(
        book_id=book, level="chapter", embedding_model_uuid="e",
    )
    assert len(out) == 2
    assert all(isinstance(s, LevelSummary) for s in out)
