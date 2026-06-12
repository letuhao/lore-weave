"""M6b: _record_glossary_usage — best-effort batched usage-index write."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.workers.session_translator import _record_glossary_usage

CT_ID = uuid4()


@pytest.mark.asyncio
async def test_records_one_row_per_used_entity():
    pool = AsyncMock()
    ids = {str(uuid4()), str(uuid4()), str(uuid4())}
    await _record_glossary_usage(pool, CT_ID, ids)
    pool.executemany.assert_awaited_once()
    sql, rows = pool.executemany.await_args.args
    assert "chapter_translation_glossary_usage" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert "$2::uuid" in sql  # text entity_ids cast to uuid
    assert {r[1] for r in rows} == ids
    assert all(r[0] == CT_ID for r in rows)


@pytest.mark.asyncio
async def test_empty_set_is_noop():
    pool = AsyncMock()
    await _record_glossary_usage(pool, CT_ID, set())
    pool.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_db_error_is_swallowed():
    """A usage-index write failure must NEVER break translation (best-effort)."""
    pool = AsyncMock()
    pool.executemany.side_effect = RuntimeError("db down")
    # Must not raise.
    await _record_glossary_usage(pool, CT_ID, {str(uuid4())})
