"""K14.3 — Event dispatcher.

Routes event_type strings to handler functions. Unknown events are
logged and acked (no retry). Handler exceptions are propagated to
the consumer for DLQ handling (K14.8).
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


# Handler signature: async def handler(event: EventData, **deps) -> None
HandlerFn = Callable[..., Awaitable[None]]


class EventDispatcher:
    """Maps event_type → handler function.

    Register handlers at startup. Dispatch routes by exact match.
    Unknown types are logged and skipped (returns False).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, event_type: str, handler: HandlerFn) -> None:
        self._handlers[event_type] = handler

    async def dispatch(self, event: EventData, **deps: Any) -> bool:
        """Dispatch an event to its handler.

        Returns True if handled, False if no handler registered.
        Raises on handler error (caller catches for DLQ).
        """
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
