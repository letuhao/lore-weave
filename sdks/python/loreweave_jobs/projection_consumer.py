"""``BaseProjectionConsumer`` — the shared transport scaffold for **multi-stream
projection / collector** consumers (Unified Job Control Plane, the 2nd base).

Where ``BaseTerminalConsumer`` models the single-stream, forward-looking (``id="$"``),
retry→poison terminal-event resume consumers, this models the OTHER hand-rolled family:
the multi-stream collectors that fan a handful of event streams into a projection /
extraction pipeline (knowledge ``EventConsumer``, learning ``EventConsumer``, campaign
``ProjectionConsumer``/``SpendConsumer``). Their genuinely-shared (and copy-pasted, bugs
and all) transport:

- **multiple** streams under one group, created at ``id="0"`` (replay the retained
  backlog on first deploy — a projection must see history, unlike a forward-looking
  resume consumer),
- ``socket_timeout=None`` blocking ``xreadgroup`` over all streams, redis-py-8 idle
  ``TimeoutError`` handling, ``ConnectionError`` reconnect, ``CancelledError`` clean exit,
- a startup PEL drain (``id="0"``) AND a periodic **``XAUTOCLAIM``** reclaim of
  stale-pending messages (the D-PLATFORM-CONSUMER-RECLAIM bug class: a handler failure
  leaves a message pending; ``xreadgroup ">"`` never returns it again, so without a timed
  reclaim its retry counter never advances and it never reaches the DLQ — a tombstoned
  message reclaims with empty fields and must be acked to drain the PEL),
- a **pluggable error policy**: ``retry→DLQ`` (knowledge/learning — bounded retry then a
  durable dead-letter sink + ack) OR ``ack-on-error`` (campaign — best-effort projection,
  no redelivery).

A subclass supplies only ``streams``/``group`` + ``handle(stream, msg_id, fields)`` (parse
+ dispatch; return ⇒ ack, raise ⇒ the error policy) and, for the retry→DLQ policy,
overrides ``on_dlq`` to persist the dead letter (the sink is service-specific — a Postgres
``dead_letter_events`` table, a stream, …).
"""

from __future__ import annotations

import abc
import asyncio
import logging
import platform
from typing import Optional

import redis.asyncio as aioredis

log = logging.getLogger(__name__)


class BaseProjectionConsumer(abc.ABC):
    """Subclass: set ``streams`` (non-empty) + ``group``, implement ``handle``; for the
    default retry→DLQ policy override ``on_dlq``. Run ``await consumer.run()`` as a
    background task; cancel to stop.

    Class attributes:
      - ``streams`` (REQUIRED) — the stream keys this group consumes.
      - ``group`` (REQUIRED) — the consumer-group name.
      - ``start_id`` — group creation offset; default ``"0"`` (replay backlog — a
        projection needs history). Set ``"$"`` for forward-only.
      - ``ack_on_error`` — ``False`` (default) = bounded retry then ``on_dlq`` + ack;
        ``True`` = best-effort ack on any handler error (no retry, no DLQ).
      - ``max_retries`` (3), ``block_ms`` (5000), ``count`` (10), ``consumer_name_prefix``,
        ``retry_prefix``.
      - ``reclaim_every_n_loops`` (12; ``<=0`` disables) + ``reclaim_min_idle_ms`` (30000)
        — periodic XAUTOCLAIM of stale-pending messages.
    """

    streams: list[str] = []
    group: str = ""
    start_id: str = "0"
    ack_on_error: bool = False
    max_retries: int = 3
    block_ms: int = 5000
    count: int = 10
    consumer_name_prefix: str = "projection"
    retry_prefix: str = "jobs:projection:retry"
    reclaim_every_n_loops: int = 12
    reclaim_min_idle_ms: int = 30000

    def __init__(
        self,
        redis_url: str,
        *,
        consumer_name: Optional[str] = None,
        redis_client: Optional[aioredis.Redis] = None,
    ) -> None:
        if not self.streams:
            raise ValueError(f"{type(self).__name__} must set a non-empty `streams`")
        if not self.group:
            raise ValueError(f"{type(self).__name__} must set a non-empty `group`")
        self._redis_url = redis_url
        self._consumer_name = consumer_name or f"{self.consumer_name_prefix}-{platform.node()}"
        self._redis: Optional[aioredis.Redis] = redis_client
        self._running = False

    # ── transport scaffold ───────────────────────────────────────────────────────
    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            # socket_timeout=None is REQUIRED — a per-read timeout < block_ms pre-empts
            # the server-side BLOCK and wedges the consumer.
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True, socket_timeout=None,
            )
        return self._redis

    async def _ensure_groups(self) -> None:
        r = await self._ensure_redis()
        for stream in self.streams:
            try:
                await r.xgroup_create(stream, self.group, id=self.start_id, mkstream=True)
                log.info("created consumer group %s on %s", self.group, stream)
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def run(self) -> None:
        """Long-running consume loop over all ``streams``. Run via create_task; cancel to
        stop. Startup creates the groups, retrying every 5s until Redis is ready, then
        drains each stream's PEL before reading new messages."""
        self._running = True
        log.info(
            "%s starting (group=%s consumer=%s streams=%s)",
            type(self).__name__, self.group, self._consumer_name, self.streams,
        )
        r: Optional[aioredis.Redis] = None
        while self._running:
            try:
                await self._ensure_groups()
                r = await self._ensure_redis()
                await self._process_pending(r)
                break
            except asyncio.CancelledError:
                await self.close()
                return
            except Exception:  # noqa: BLE001 — Redis not ready yet; retry
                log.warning("%s: Redis not ready, retry in 5s", type(self).__name__, exc_info=True)
                self._redis = None
                await asyncio.sleep(5)
        if not self._running or r is None:
            await self.close()
            return

        loop_count = 0
        streams_dict = {s: ">" for s in self.streams}
        while self._running:
            try:
                loop_count += 1
                if self.reclaim_every_n_loops > 0 and loop_count % self.reclaim_every_n_loops == 0:
                    await self._reclaim_stale_pending(r)
                results = await r.xreadgroup(
                    self.group, self._consumer_name, streams_dict,
                    count=self.count, block=self.block_ms,
                )
                for stream_name, messages in results or []:
                    for msg_id, fields in messages:
                        await self._handle_message(r, stream_name, msg_id, fields)
            except asyncio.CancelledError:
                break
            except aioredis.TimeoutError:
                continue  # idle long-poll (redis-py 8)
            except aioredis.ConnectionError:
                log.warning("%s: redis connection lost; reconnecting in 5s", type(self).__name__)
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:  # noqa: BLE001 — one bad iteration must not kill the task
                log.exception("%s loop error; retrying in 2s", type(self).__name__)
                await asyncio.sleep(2)
        await self.close()

    async def _process_pending(self, r: aioredis.Redis) -> None:
        """Startup: re-process this consumer's unacked PEL (id '0') on each stream."""
        for stream in self.streams:
            try:
                results = await r.xreadgroup(
                    self.group, self._consumer_name, {stream: "0"}, count=100,
                )
                for stream_name, messages in results or []:
                    for msg_id, fields in messages:
                        await self._handle_message(r, stream_name, msg_id, fields)
            except Exception:  # noqa: BLE001
                log.exception("%s: error processing pending for %s", type(self).__name__, stream)

    async def _reclaim_stale_pending(self, r: aioredis.Redis) -> None:
        """Re-deliver messages stuck in the PEL (a prior handler failure left them
        pending). ``xreadgroup ">"`` never returns these, so without a timed XAUTOCLAIM a
        failed event would only retry on restart — its retry counter never advances and it
        never reaches the DLQ. A tombstoned (XDEL'd) message reclaims with empty fields →
        ack to drain the PEL rather than loop."""
        for stream in self.streams:
            try:
                start = "0-0"
                while True:
                    next_start, claimed, _deleted = await r.xautoclaim(
                        stream, self.group, self._consumer_name,
                        min_idle_time=self.reclaim_min_idle_ms, start_id=start, count=50,
                    )
                    for msg_id, fields in claimed:
                        if not fields:
                            await r.xack(stream, self.group, msg_id)
                            continue
                        await self._handle_message(r, stream, msg_id, fields)
                    if not next_start or next_start == "0-0":
                        break
                    start = next_start
            except aioredis.ResponseError:
                pass  # NOGROUP / stream not yet created — nothing to reclaim
            except Exception:  # noqa: BLE001
                log.exception("%s: error reclaiming pending for %s", type(self).__name__, stream)

    async def _handle_message(self, r: aioredis.Redis, stream: str, msg_id: str, fields: dict) -> None:
        """``handle`` → ack; on exception apply the error policy. ``handle`` returning
        normally (incl. an unparseable / no-handler no-op) ⇒ ack."""
        try:
            await self.handle(stream, msg_id, fields)
            await r.xack(stream, self.group, msg_id)
        except Exception as exc:  # noqa: BLE001
            await self._on_error(r, stream, msg_id, fields, exc)

    async def _on_error(self, r: aioredis.Redis, stream: str, msg_id: str, fields: dict, exc: Exception) -> None:
        if self.ack_on_error:
            # Best-effort projection: a handler error is logged + acked (no redelivery).
            log.warning(
                "%s: handler error on %s id=%s — ack-on-error policy: %s",
                type(self).__name__, stream, msg_id, exc,
            )
            await r.xack(stream, self.group, msg_id)
            return
        retry_key = f"{self.retry_prefix}:{stream}:{msg_id}"
        count = int(await r.incr(retry_key))
        await r.expire(retry_key, 3600)
        if count < self.max_retries:
            log.warning(
                "%s: handler failed (%d/%d) on %s id=%s — leaving unacked (redelivered): %s",
                type(self).__name__, count, self.max_retries, stream, msg_id, exc,
            )
            return  # stays pending → redelivered (by XREADGROUP "0" drain or the reclaim)
        log.error(
            "%s: DLQ after %d× on %s id=%s: %s",
            type(self).__name__, count, stream, msg_id, exc,
        )
        try:
            await self.on_dlq(stream, msg_id, fields, exc)
        except Exception:  # noqa: BLE001 — DLQ sink failure must not block draining the PEL
            log.exception("%s: on_dlq failed for %s id=%s", type(self).__name__, stream, msg_id)
        await r.xack(stream, self.group, msg_id)
        await r.delete(retry_key)

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ── template-method hooks ─────────────────────────────────────────────────────
    @abc.abstractmethod
    async def handle(self, stream: str, msg_id: str, fields: dict) -> None:
        """Parse + dispatch ONE message. Return normally to ack (incl. an unparseable or
        no-handler no-op — a projection acks those). Raise to trigger the error policy.
        MUST be idempotent under at-least-once delivery + the reclaim."""
        raise NotImplementedError

    async def on_dlq(self, stream: str, msg_id: str, fields: dict, exc: Exception) -> None:
        """Persist a dead letter after ``max_retries`` (retry→DLQ policy). Default no-op;
        override to write the service's durable sink (e.g. a ``dead_letter_events`` row).
        Not called under the ``ack_on_error`` policy."""
        return None
