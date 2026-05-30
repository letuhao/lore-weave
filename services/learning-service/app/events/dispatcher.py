"""Event dispatcher — routes event_type → handler.

Cloned from knowledge-service. Unknown events are logged and acked (no retry);
handler exceptions propagate to the consumer for DLQ handling.

NOTE: `EventData.outbox_id` is the producer's outbox row id, carried on the
Redis stream via the relay's `outbox_id` XADD field (worker-infra outbox_relay
§4.0). It is the end-to-end idempotency key — stable across relay re-emission,
unlike `message_id` (changes on re-emit) and `aggregate_id` (the reused target
id). The corrections handler keys `ON CONFLICT` on it; an empty value is a hard
error, NOT a silent insert (R3-W1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

__all__ = ["EventDispatcher", "EventData"]

logger = logging.getLogger(__name__)


@dataclass
class EventData:
    """Parsed event from a Redis Stream message."""
    stream: str
    message_id: str
    event_type: str
    aggregate_id: str
    payload: dict[str, Any]
    source: str
    raw: dict[str, str]  # original Redis fields
    outbox_id: str = ""  # producer outbox row id (relay §4.0) — dedup key


# Handler signature: async def handler(event: EventData, **deps) -> None
HandlerFn = Callable[..., Awaitable[None]]


class EventDispatcher:
    """Maps event_type → handler function. Dispatch routes by exact match;
    unknown types are logged and skipped (returns False)."""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, event_type: str, handler: HandlerFn) -> None:
        self._handlers[event_type] = handler

    async def dispatch(self, event: EventData, **deps: Any) -> bool:
        handler = self._handlers.get(event.event_type)
        if handler is None:
            logger.debug(
                "No handler for event_type=%s (stream=%s, id=%s) — skipping",
                event.event_type, event.stream, event.message_id,
            )
            return False
        await handler(event, **deps)
        return True

    @property
    def registered_types(self) -> list[str]:
        return list(self._handlers.keys())
