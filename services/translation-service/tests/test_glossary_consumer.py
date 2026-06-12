"""M5c: glossary-staleness consumer — event parse + stale-marking handler."""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.events.glossary_consumer import parse_glossary_event, handle_glossary_event

BOOK_ID = str(uuid4())


# ── parse_glossary_event ──────────────────────────────────────────────────────

def test_parse_valid():
    et, payload = parse_glossary_event(
        {"event_type": "glossary.entity_updated", "payload": json.dumps({"book_id": BOOK_ID})})
    assert et == "glossary.entity_updated" and payload["book_id"] == BOOK_ID


def test_parse_bad_json_yields_empty_payload():
    et, payload = parse_glossary_event({"event_type": "x", "payload": "{not json"})
    assert et == "x" and payload == {}


def test_parse_missing_fields():
    et, payload = parse_glossary_event({})
    assert et == "" and payload == {}


def test_parse_non_dict_payload():
    et, payload = parse_glossary_event({"event_type": "x", "payload": "[1,2,3]"})
    assert payload == {}


ENTITY_ID = str(uuid4())


# ── handle_glossary_event — M6b targeted path ─────────────────────────────────

@pytest.mark.asyncio
async def test_handle_targeted_uses_usage_index():
    """entity_id present ⇒ the targeted query keys on the usage index + falls back
    to legacy (NOT EXISTS) chapters; carries book/entity/language args."""
    pool = AsyncMock()
    handled = await handle_glossary_event(
        pool, "glossary.entity_updated",
        {"book_id": BOOK_ID, "glossary_entity_id": ENTITY_ID, "target_language": "vi"})
    assert handled is True
    pool.execute.assert_awaited_once()
    sql, book_arg, entity_arg, lang_arg = pool.execute.await_args.args
    assert "is_glossary_stale = true" in sql
    assert "chapter_translation_glossary_usage" in sql       # precise join
    assert "NOT EXISTS" in sql                                # legacy fallback
    # review-impl MED-HIGH: per-language filter matches the PRIMARY SUBTAG
    # (case-insensitive) — NOT an exact `=` — so "vi" flags a "vi-VN" chapter.
    assert "SPLIT_PART(ct.target_language, '-', 1)" in sql
    assert "ct.target_language = $3" not in sql              # no brittle exact match
    assert str(book_arg) == BOOK_ID
    assert str(entity_arg) == ENTITY_ID
    assert lang_arg == "vi"


@pytest.mark.asyncio
async def test_handle_targeted_no_language_flags_all_langs():
    """A name/structural change carries no target_language ⇒ lang arg is None
    ($3 IS NULL ⇒ all languages of the affected chapters)."""
    pool = AsyncMock()
    await handle_glossary_event(
        pool, "glossary.entity_updated",
        {"book_id": BOOK_ID, "glossary_entity_id": ENTITY_ID})
    _sql, _book, _entity, lang_arg = pool.execute.await_args.args
    assert lang_arg is None


# ── handle_glossary_event — coarse fallback (no entity anchor) ────────────────

@pytest.mark.asyncio
async def test_handle_coarse_when_no_entity_id():
    """A legacy event without glossary_entity_id ⇒ coarse book-level flag
    (the old M5c path), still honoring an optional language filter."""
    pool = AsyncMock()
    handled = await handle_glossary_event(
        pool, "glossary.entity_updated", {"book_id": BOOK_ID})
    assert handled is True
    pool.execute.assert_awaited_once()
    sql, book_arg, lang_arg = pool.execute.await_args.args
    assert "is_glossary_stale = true" in sql
    assert "WHERE book_id" in sql
    assert "chapter_translation_glossary_usage" not in sql    # NOT the targeted query
    assert str(book_arg) == BOOK_ID
    assert lang_arg is None


@pytest.mark.asyncio
async def test_handle_invalid_entity_id_falls_back_to_coarse():
    """A malformed entity_id must not crash — degrade to the coarse path."""
    pool = AsyncMock()
    handled = await handle_glossary_event(
        pool, "glossary.entity_updated",
        {"book_id": BOOK_ID, "glossary_entity_id": "not-a-uuid"})
    assert handled is True
    sql = pool.execute.await_args.args[0]
    assert "chapter_translation_glossary_usage" not in sql


@pytest.mark.asyncio
async def test_handle_ignores_other_event_types():
    pool = AsyncMock()
    handled = await handle_glossary_event(
        pool, "glossary.entity_deleted", {"book_id": BOOK_ID})
    assert handled is False
    pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_missing_book_id_noop():
    pool = AsyncMock()
    handled = await handle_glossary_event(pool, "glossary.entity_updated", {})
    assert handled is False
    pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_invalid_book_id_noop():
    pool = AsyncMock()
    handled = await handle_glossary_event(
        pool, "glossary.entity_updated", {"book_id": "not-a-uuid"})
    assert handled is False
    pool.execute.assert_not_awaited()


# ── consumer group setup (review-impl fixes) ──────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_group_uses_forward_offset():
    """review-impl MED: group starts at '$' (new events only) — NOT '0' (which
    would replay the entire glossary backlog and mass-flag every book on deploy)."""
    from app.events.glossary_consumer import GlossaryStaleConsumer
    c = GlossaryStaleConsumer("redis://x", AsyncMock())
    fake = AsyncMock()
    c._redis = fake  # bypass real connect
    await c._ensure_group()
    fake.xgroup_create.assert_awaited_once()
    assert fake.xgroup_create.await_args.kwargs.get("id") == "$"


@pytest.mark.asyncio
async def test_ensure_group_swallows_busygroup():
    import redis.asyncio as aioredis
    from app.events.glossary_consumer import GlossaryStaleConsumer
    c = GlossaryStaleConsumer("redis://x", AsyncMock())
    fake = AsyncMock()
    fake.xgroup_create.side_effect = aioredis.ResponseError("BUSYGROUP group exists")
    c._redis = fake
    await c._ensure_group()  # must not raise


@pytest.mark.asyncio
async def test_ensure_group_reraises_other_errors():
    import redis.asyncio as aioredis
    from app.events.glossary_consumer import GlossaryStaleConsumer
    c = GlossaryStaleConsumer("redis://x", AsyncMock())
    fake = AsyncMock()
    fake.xgroup_create.side_effect = aioredis.ResponseError("WRONGTYPE")
    c._redis = fake
    with pytest.raises(aioredis.ResponseError):
        await c._ensure_group()
