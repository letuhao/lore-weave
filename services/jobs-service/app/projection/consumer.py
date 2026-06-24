"""`JobProjectionConsumer` — projects `loreweave:events:jobs` into the mirror.

Built on the shared `BaseProjectionConsumer` (the multi-stream projection
transport scaffold — backlog replay at id="0" so a fresh deploy sees history,
periodic XAUTOCLAIM reclaim, retry→DLQ). This consumer reads the SINGLE jobs
stream; the base handles all transport. `handle` parses the relayed event
(worker-infra's outbox relay XADDs `{event_type, aggregate_id, payload, source,
outbox_id}`) into a `JobEvent` and upserts it.

Error policy = retry→DLQ (default): a transient DB failure redelivers; after
`max_retries` the raw event is parked in `dead_letter_events` (+ acked so the PEL
drains) and the reconcile sweep (P2 M4 / P3) is the durability backstop. An
unparseable / malformed payload is a no-op (logged + acked) — it can never become
a `JobEvent`, so retrying it is pointless poison.
"""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Optional

import asyncpg

from loreweave_jobs import JOBS_STREAM, BaseProjectionConsumer, JobEvent

from .store import upsert_job_event

logger = logging.getLogger(__name__)

GROUP_NAME = "jobs-projection"

# Optional async hook(JobEvent) invoked AFTER a successful upsert — M3 wires the
# SSE pub/sub publish here. None = no notify (M1).
NotifyHook = Callable[[JobEvent], Awaitable[None]]


class JobProjectionConsumer(BaseProjectionConsumer):
    """Project the canonical job-event stream into `job_projection`. Run `run()`
    as a lifespan background task; `stop()` + cancel to shut down."""

    streams = [JOBS_STREAM]
    group = GROUP_NAME
    start_id = "0"            # replay backlog — a projection needs history
    ack_on_error = False      # retry→DLQ (a dropped event = a job stuck "running")
    consumer_name_prefix = "jobs"
    count = 50
    block_ms = 5000

    def __init__(
        self,
        redis_url: str,
        pool: asyncpg.Pool,
        *,
        consumer_name: Optional[str] = None,
        notify: Optional[NotifyHook] = None,
    ) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._notify = notify

    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        """Parse + upsert ONE event. Returns (ack) on success or an unparseable
        no-op; raises (→ retry→DLQ) only on a transient store/DB failure."""
        event = self._parse(stream, msg_id, fields)
        if event is None:
            return  # unparseable/malformed — ack as a no-op, never poison-loop
        applied = await upsert_job_event(self._pool, event)
        # Only notify when the upsert actually advanced the row — a monotonic
        # no-op (stale/duplicate event) must not push a wrong-state SSE frame.
        if applied and self._notify is not None:
            try:
                await self._notify(event)
            except Exception:  # noqa: BLE001 — notify is best-effort; never fail the projection
                logger.warning("jobs SSE notify failed for %s/%s", event.service, event.job_id, exc_info=True)

    def _parse(self, stream: str, msg_id: str, fields: dict) -> Optional[JobEvent]:
        raw = fields.get("payload")
        if not raw:
            logger.warning("jobs event missing payload: stream=%s id=%s", stream, msg_id)
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("jobs event invalid JSON: stream=%s id=%s", stream, msg_id)
            return None
        try:
            return JobEvent.from_payload(payload)
        except (KeyError, ValueError, TypeError):
            logger.warning("jobs event malformed (missing/invalid field): stream=%s id=%s", stream, msg_id)
            return None

    async def on_dlq(self, stream: str, msg_id: str, fields: dict, exc: Exception) -> None:
        """Park an event that failed to project `max_retries` times. The reconcile
        sweep heals the affected job; this preserves the raw event for debugging."""
        raw = fields.get("payload")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = None
        await self._pool.execute(
            "INSERT INTO dead_letter_events (stream, msg_id, payload, error) "
            "VALUES ($1, $2, $3::jsonb, $4)",
            stream, msg_id, json.dumps(payload) if payload is not None else None, str(exc),
        )
