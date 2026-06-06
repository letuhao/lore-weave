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


# ── handle_glossary_event ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handle_marks_book_stale():
    pool = AsyncMock()
    handled = await handle_glossary_event(
        pool, "glossary.entity_updated", {"book_id": BOOK_ID})
    assert handled is True
    pool.execute.assert_awaited_once()
    sql, arg = pool.execute.await_args.args
    assert "is_glossary_stale = true" in sql
    assert "WHERE book_id" in sql
    assert str(arg) == BOOK_ID  # parsed to UUID, matches


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
