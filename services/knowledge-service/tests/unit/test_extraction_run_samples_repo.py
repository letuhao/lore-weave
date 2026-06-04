"""Q4b-feed — unit tests for ExtractionRunSamplesRepo.

The run-attributable items+source buffer feeding the online LLM judge.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repositories.extraction_run_samples import ExtractionRunSamplesRepo

pytestmark = pytest.mark.asyncio


def _items():
    return {
        "entity": [{"name": "Alice", "kind": "person"}],
        "relation": [{"subject": "Alice", "predicate": "fell_into", "object": "hole", "polarity": "positive"}],
        "event": [{"summary": "Alice fell down the hole", "participants": ["Alice"]}],
    }


async def test_insert_returns_true_on_insert():
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="INSERT 0 1")
    repo = ExtractionRunSamplesRepo(pool)
    ok = await repo.insert_sample(
        run_id=uuid.uuid4(), user_id=uuid.uuid4(), project_id=None, book_id=None,
        config_hash="abc", items=_items(), source_text="Alice fell down the hole.",
    )
    assert ok is True
    sql = pool.execute.await_args.args[0]
    assert "ON CONFLICT (run_id) DO NOTHING" in sql


async def test_insert_returns_false_on_conflict():
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="INSERT 0 0")  # conflict → 0 rows
    repo = ExtractionRunSamplesRepo(pool)
    ok = await repo.insert_sample(
        run_id=uuid.uuid4(), user_id=uuid.uuid4(), project_id=None, book_id=None,
        config_hash=None, items=_items(), source_text="x",
    )
    assert ok is False


async def test_insert_serializes_items_as_json():
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="INSERT 0 1")
    repo = ExtractionRunSamplesRepo(pool)
    items = _items()
    await repo.insert_sample(
        run_id=uuid.uuid4(), user_id=uuid.uuid4(), project_id=None, book_id=None,
        config_hash=None, items=items, source_text="x",
    )
    params = pool.execute.await_args.args
    # items_jsonb param is position 6 (1-indexed $6 → args[6] after sql at args[0])
    assert json.loads(params[6]) == items


async def test_fetch_returns_none_when_absent():
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    repo = ExtractionRunSamplesRepo(pool)
    assert await repo.fetch_sample(uuid.uuid4()) is None


async def test_fetch_parses_jsonb_string_and_roundtrips():
    rid, uid = uuid.uuid4(), uuid.uuid4()
    items = _items()
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "run_id": rid, "user_id": uid, "project_id": None, "book_id": None,
        "config_hash": "h", "items_jsonb": json.dumps(items),  # asyncpg returns str
        "source_text": "Alice fell down the hole.",
    })
    repo = ExtractionRunSamplesRepo(pool)
    sample = await repo.fetch_sample(rid)
    assert sample is not None
    assert sample.run_id == rid
    assert sample.items == items  # str → parsed dict
    assert sample.source_text == "Alice fell down the hole."


async def test_prune_returns_count_and_scopes_to_window():
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="DELETE 4")
    repo = ExtractionRunSamplesRepo(pool)
    n = await repo.prune_older_than(7)
    assert n == 4
    sql = pool.execute.await_args.args[0]
    assert "DELETE FROM extraction_run_samples" in sql
    assert "make_interval(days => $1)" in sql
    assert pool.execute.await_args.args[1] == 7


async def test_prune_zero_when_none_old():
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="DELETE 0")
    repo = ExtractionRunSamplesRepo(pool)
    assert await repo.prune_older_than(7) == 0
