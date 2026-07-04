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


# Substrings that mark a CORRECTION-class event. learning consumes a firehose of
# ALL domain events on 5 streams and handles only the correction subset, so an
# unhandled type is normally a non-correction event we correctly ignore (DEBUG).
# But an unhandled event whose type carries one of these markers is a correction
# that is being SILENTLY DROPPED — a producer renamed one, or shipped a new
# correction type nobody wired (the exact producer-side gap the consumer-owned
# CORRECTION_EVENT_TYPES contract is structurally blind to). Surface it at WARN so
# it's visible at runtime, where producer-side truth actually lives. Low-noise: the
# firehose's non-correction events (created/translated/started/…) match none of these.
_CORRECTION_MARKERS = (
    "corrected",
    "feedback",
    "reviewed",
    "merged",
    "confirmed",
    "quality",
    "adjusted",
)


def _looks_like_correction(event_type: str) -> bool:
    et = event_type.lower()
    return any(marker in et for marker in _CORRECTION_MARKERS)


class EventDispatcher:
    """Maps event_type → handler function. Dispatch routes by exact match;
    unknown types are skipped (returns False) — quietly for non-correction firehose
    noise, but at WARN for a correction-class type with no handler (a silent drop)."""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, event_type: str, handler: HandlerFn) -> None:
        self._handlers[event_type] = handler

    async def dispatch(self, event: EventData, **deps: Any) -> bool:
        handler = self._handlers.get(event.event_type)
        if handler is None:
            if _looks_like_correction(event.event_type):
                # No-silent-drop (runtime half): a correction-class event with no
                # handler is a lost learning signal — make it VISIBLE. Register a
                # handler + add it to CORRECTION_EVENT_TYPES, or confirm it's
                # deliberately out of scope.
                logger.warning(
                    "No handler for CORRECTION-class event_type=%s (stream=%s, id=%s) "
                    "— dropping a correction signal; wire a handler or confirm out-of-scope",
                    event.event_type, event.stream, event.message_id,
                )
            else:
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
