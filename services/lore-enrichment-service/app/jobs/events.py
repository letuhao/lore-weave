"""Job lifecycle EVENTS on Redis Streams (RAID C14).

The job runner (``app.jobs.runner``) emits one event per lifecycle phase so an
external consumer (UI / observability / a later eval gate) can follow a job
without polling the DB. Events go on ONE stream
(``loreweave:events:lore_enrichment``) following the platform convention
(``loreweave:events:<aggregate>``, mirrors glossary's
``loreweave:events:glossary`` outbox). The producer is:

  * **idempotent** — a per-(job, stage[, gap_ref]) dedupe key guards against a
    re-run / crash-resume double-emitting the same ``proposal_created`` or
    ``stage_completed``. The dedupe set is seeded from prior runs so an
    at-least-once consumer never sees a duplicate the producer could avoid.
  * **consumer-group-safe** — events are plain ``XADD`` field maps (all values
    stringified); a consumer group reads via ``XREADGROUP`` exactly like the
    knowledge-service K14 consumer. Field values are JSON-encodable scalars only.
  * **non-fatal** — Redis being down NEVER crashes the job. A failed emit is
    swallowed (best-effort) and the runner proceeds; the DB row remains the
    source of truth. The emitter records emit failures for observability.

Boundaries (locked):
  * NO model names, NO secrets, NO business logic — this only serializes a job's
    lifecycle. The event payload carries IDs + counts + a phase, never enriched
    content (H0: the makeup lore lives in the quarantined proposal row, not the
    event bus).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

__all__ = [
    "JobEventType",
    "JobEvent",
    "RedisStreamProducer",
    "JobEventEmitter",
    "LORE_ENRICHMENT_STREAM",
    "STREAM_MAXLEN",
]

logger = logging.getLogger("lore_enrichment.job_events")

#: The single Redis stream key (platform convention loreweave:events:<aggregate>).
LORE_ENRICHMENT_STREAM: str = "loreweave:events:lore_enrichment"

#: Approximate cap on stream length (XADD MAXLEN ~) — mirrors the glossary
#: outbox stream's 10000 bound so the bus cannot grow unbounded.
STREAM_MAXLEN: int = 10000


class JobEventType(str, Enum):
    """The job lifecycle events emitted on the stream (brief-locked names)."""

    STARTED = "lore_enrichment.job.started"
    STAGE_COMPLETED = "lore_enrichment.job.stage_completed"
    PROPOSAL_CREATED = "lore_enrichment.job.proposal_created"
    PAUSED = "lore_enrichment.job.paused"
    COMPLETED = "lore_enrichment.job.completed"
    FAILED = "lore_enrichment.job.failed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class JobEvent:
    """One lifecycle event. ``dedupe_key`` makes the producer idempotent: two
    events with the same key are the SAME logical occurrence (a crash-resume
    must not double-emit). The key is derived from job_id + event type + an
    optional per-gap discriminator so per-gap events stay distinct."""

    event_type: JobEventType
    job_id: str
    project_id: str
    user_id: str
    dedupe_key: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=_now_iso)

    def to_fields(self) -> dict[str, str]:
        """Serialize to a flat XADD field map (all values stringified).

        ``data`` is JSON-encoded under one field so arbitrary nested payloads
        round-trip through Redis Streams (which only stores string field maps).
        UTF-8 / CJK safe: ``ensure_ascii=False`` keeps place names readable."""
        return {
            "event_type": self.event_type.value,
            "job_id": self.job_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "dedupe_key": self.dedupe_key,
            "ts": self.ts,
            "data": json.dumps(self.data, ensure_ascii=False),
        }


class RedisStreamProducer(Protocol):
    """The minimal Redis seam the emitter needs: append a field map to a stream.

    Implemented over ``redis.asyncio`` in production; a fake in unit tests so the
    event contract is exercised without a real Redis. Returns the stream message
    id (or raises on transport failure — the emitter swallows it)."""

    async def xadd(
        self, stream: str, fields: dict[str, str], *, maxlen: int | None = None
    ) -> str: ...


class _AioredisProducer:
    """``redis.asyncio``-backed :class:`RedisStreamProducer`.

    Lazily connects; a connection failure surfaces on first ``xadd`` and is
    caught by the emitter (best-effort). Mirrors the knowledge-service consumer's
    ``aioredis.from_url`` usage (decode_responses=True)."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._redis: Any = None

    async def _ensure(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis  # local import — optional dep

            self._redis = aioredis.from_url(self._url, decode_responses=True)
        return self._redis

    async def xadd(
        self, stream: str, fields: dict[str, str], *, maxlen: int | None = None
    ) -> str:
        r = await self._ensure()
        # approximate trim (MAXLEN ~) — cheap, keeps the stream bounded.
        return await r.xadd(stream, fields, maxlen=maxlen, approximate=True)

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


def make_redis_producer(redis_url: str) -> _AioredisProducer:
    """Build the production Redis Streams producer from a redis URL."""
    return _AioredisProducer(redis_url)


class JobEventEmitter:
    """Idempotent, best-effort job-event producer over a Redis stream.

    Construct with a :class:`RedisStreamProducer` (real or fake) and the job's
    scope. ``emit`` builds the event, skips it if its dedupe key was already
    emitted (idempotency), and appends it to the stream — swallowing any
    transport error so a down Redis never fails the job.

    ``seen_keys`` may be pre-seeded (e.g. from a crash-resume scan of the stream)
    so the producer does not re-emit events a prior run already published.
    """

    def __init__(
        self,
        producer: RedisStreamProducer | None,
        *,
        job_id: str,
        project_id: str,
        user_id: str,
        stream: str = LORE_ENRICHMENT_STREAM,
        seen_keys: set[str] | None = None,
    ) -> None:
        self._producer = producer
        self._job_id = job_id
        self._project_id = project_id
        self._user_id = user_id
        self._stream = stream
        self._seen: set[str] = set(seen_keys) if seen_keys else set()
        #: events that were emitted (for tests / observability), in order.
        self.emitted: list[JobEvent] = []
        #: count of emits that failed at the transport (Redis down) — non-fatal.
        self.emit_failures: int = 0

    def _dedupe_key(self, event_type: JobEventType, gap_ref: str | None) -> str:
        base = f"{self._job_id}:{event_type.value}"
        return f"{base}:{gap_ref}" if gap_ref else base

    async def emit(
        self,
        event_type: JobEventType,
        *,
        gap_ref: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> JobEvent | None:
        """Emit one lifecycle event (idempotent + best-effort).

        Returns the :class:`JobEvent` that was appended, or ``None`` if it was a
        duplicate (already-seen dedupe key) and therefore skipped. A transport
        failure does NOT raise — it increments ``emit_failures`` and returns the
        event (the runner proceeds; the DB row is the source of truth)."""
        key = self._dedupe_key(event_type, gap_ref)
        if key in self._seen:
            return None  # idempotent: this logical event already emitted
        event = JobEvent(
            event_type=event_type,
            job_id=self._job_id,
            project_id=self._project_id,
            user_id=self._user_id,
            dedupe_key=key,
            data=dict(data or {}),
        )
        # Mark seen BEFORE the append so a transient append failure cannot cause
        # a later retry to double-publish the same logical event (at-most-once
        # for the logical key; the consumer dedupes on dedupe_key for the
        # at-least-once stream redelivery case).
        self._seen.add(key)
        self.emitted.append(event)
        if self._producer is not None:
            try:
                await self._producer.xadd(
                    self._stream, event.to_fields(), maxlen=STREAM_MAXLEN
                )
            except Exception:  # noqa: BLE001 — Redis down must NOT fail the job
                self.emit_failures += 1
                logger.warning(
                    "job event emit failed (non-fatal): job=%s type=%s",
                    self._job_id, event_type.value, exc_info=True,
                )
        return event
