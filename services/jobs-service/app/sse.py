"""Per-user SSE bridge (Unified Job Control Plane P2 M3).

The projection consumer publishes each applied `JobEvent` to a per-OWNER Redis
pub/sub channel (`loreweave:jobs:user:<owner_user_id>`); the `GET /v1/jobs/stream`
endpoint subscribes to the authenticated user's channel and relays events as SSE.
Pub/sub (not a re-read of the stream) keeps it owner-scoped + fan-out cheap, and a
dropped pub/sub message is non-fatal — the projection table is the SSOT, so a
client reconnect + a `GET /v1/jobs` refetch recovers the current state.

Publishing uses a SEPARATE Redis connection from the consumer's blocking
`xreadgroup` loop (one connection cannot do both). The SSE payload carries the
derived `control_caps` so the GUI can update its buttons live without a refetch.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Awaitable, Callable

import redis.asyncio as aioredis

from loreweave_jobs import JobEvent

from .contract import derive_control_caps

log = logging.getLogger(__name__)

CHANNEL_PREFIX = "loreweave:jobs:user:"
# How long get_message blocks before we emit a heartbeat comment (keeps idle
# connections + proxies alive without spinning).
HEARTBEAT_S = 15.0


def _channel(owner_user_id: str) -> str:
    return f"{CHANNEL_PREFIX}{owner_user_id}"


def event_to_payload(event: JobEvent) -> dict:
    """The live SSE payload — the JobRecord-ish shape + derived control_caps."""
    status = event.status.value if hasattr(event.status, "value") else event.status
    return {
        "service": event.service,
        "job_id": str(event.job_id),
        "owner_user_id": str(event.owner_user_id),
        "kind": event.kind,
        "status": status,
        "parent_job_id": str(event.parent_job_id) if event.parent_job_id else None,
        "detail_status": event.detail_status,
        "progress": event.progress,
        "title": event.title,
        "error": event.error,
        # P4 usage fields on the live frame so the GUI updates cost/tokens without a
        # refetch. These are per-EVENT (what the producer emitted now) — the projection
        # COALESCE-accumulates the row, but a live frame shows the latest emitted values;
        # the GUI's external store merges them onto the cached row.
        "model": event.model,
        "cost_usd": event.cost_usd,
        "tokens_in": event.tokens_in,
        "tokens_out": event.tokens_out,
        "params": event.params,
        "updated_at": event.occurred_at,
        # Uniform with the read API: pass the per-job `retryable` flag (composition's
        # per-job retry signal) when the event carries params. NOTE the residual gap
        # (D-JOBS-P4-RETRY-COMPOSITION-SSE-CAPS): composition's FAILED transition emits
        # params=None (only the create emit carries retryable), so a freshly-failed
        # composition job's LIVE frame won't include the retry cap — the read API (which
        # reads the COALESCE-preserved projection params) is authoritative and a refetch/
        # reconnect recovers it (this file's SSOT contract). Kind-retryable siblings
        # (translation/extraction/video_gen) are unaffected (their retry is kind-based).
        "control_caps": [c.value for c in derive_control_caps(
            event.status, event.kind, retryable=(event.params or {}).get("retryable"))],
    }


def make_notifier(publisher: aioredis.Redis) -> Callable[[JobEvent], Awaitable[None]]:
    """Build the consumer `notify` hook that publishes one event to its owner's
    channel via the dedicated publisher connection."""

    async def _notify(event: JobEvent) -> None:
        await publisher.publish(_channel(event.owner_user_id), json.dumps(event_to_payload(event)))

    return _notify


async def stream_user_events(redis_url: str, owner_user_id: str) -> AsyncIterator[str]:
    """Async generator of SSE frames for ONE user. Opens its own pub/sub
    subscription (and tears it down on disconnect). Emits a heartbeat comment
    every ~HEARTBEAT_S so an idle client/proxy keeps the connection open."""
    client = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(_channel(owner_user_id))
    try:
        yield ": connected\n\n"
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=HEARTBEAT_S)
            if msg is None:
                yield ": heartbeat\n\n"
                continue
            data = msg.get("data")
            if data:
                yield f"data: {data}\n\n"
    finally:
        try:
            await pubsub.unsubscribe(_channel(owner_user_id))
            await pubsub.aclose()
        finally:
            await client.aclose()
