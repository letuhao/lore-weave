"""K14.3 — Unit tests for event dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.events.dispatcher import EventData, EventDispatcher


def _event(event_type="chat.turn_completed"):
    return EventData(
        stream="loreweave:events:chat",
        message_id="1-0",
        event_type=event_type,
        aggregate_id=str(uuid4()),
        payload={"user_id": str(uuid4())},
        source="book",
        raw={},
    )


@pytest.mark.asyncio
async def test_dispatch_calls_registered_handler():
    handler = AsyncMock()
    d = EventDispatcher()
    d.register("chat.turn_completed", handler)

    result = await d.dispatch(_event("chat.turn_completed"))
    assert result is True
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_unknown_type_returns_false():
    d = EventDispatcher()
    result = await d.dispatch(_event("unknown.type"))
    assert result is False


@pytest.mark.asyncio
async def test_dispatch_propagates_handler_error():
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    d = EventDispatcher()
    d.register("chat.turn_completed", handler)

    with pytest.raises(RuntimeError):
        await d.dispatch(_event("chat.turn_completed"))


def test_registered_types():
    d = EventDispatcher()
    d.register("a", AsyncMock())
    d.register("b", AsyncMock())
    assert sorted(d.registered_types) == ["a", "b"]
