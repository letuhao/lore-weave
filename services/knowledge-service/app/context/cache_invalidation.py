"""D-T2-04 — cross-process L0/L1 cache invalidation via Redis pub/sub.

The per-worker TTL caches in `app.context.cache` accept up to 60 s
staleness inside a single process because each write path invalidates
the local key after it hits Postgres. That's fine for single-worker
deploys; with multi-worker uvicorn (or ECS tasks scaled horizontally)
worker B's cache keeps a stale row for up to 60 s after worker A wrote
an update. Track 1 accepted that window; this module closes it.

Design:

  - Every call to `cache.invalidate_l0 / invalidate_l1 /
    invalidate_all_for_user` fires a fire-and-forget publish on the
    shared `loreweave:cache-invalidate` pub/sub channel (Redis).
  - Each worker runs `CacheInvalidator.run()` as a background asyncio
    task; it consumes the channel and applies the invalidation to
    *its own* local caches via the `_apply_remote_*` helpers (which
    do NOT re-publish — prevents an echo storm).
  - Messages carry an `origin` field set at worker boot to a fresh
    UUID. A worker ignores its own messages so local writes don't
    double-invalidate through the pub/sub round-trip.
  - Publish is fire-and-forget (`asyncio.create_task`); writes never
    wait on a Redis round-trip.
  - If Redis is unreachable, publish logs a warning and the worker
    silently degrades to local-only invalidation. The TTL still caps
    drift at 60 s across workers.
  - If `settings.redis_url` is empty, the invalidator is never
    installed and everything stays single-process as before (Track 1
    fallback).

Pub/sub semantics are at-most-once: a network blip can drop an
invalidation message. The 60 s TTL is still the ultimate backstop —
this module narrows typical staleness from "TTL" to "one pub/sub
hop" (~1 ms on a healthy Redis) without claiming stronger delivery
guarantees.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from app.context import cache

__all__ = [
    "CACHE_INVALIDATION_CHANNEL",
    "CacheInvalidator",
]

logger = logging.getLogger(__name__)

CACHE_INVALIDATION_CHANNEL = "loreweave:cache-invalidate"

# Backoff ceiling for the subscriber reconnect loop. 10 s is short
# enough that a brief Redis blip recovers quickly without hammering,
# and long enough that a hard outage doesn't flood logs.
_RECONNECT_BACKOFF_CAP_S = 10.0
_RECONNECT_BACKOFF_INITIAL_S = 1.0

# Subscriber poll timeout. `get_message` blocks for up to this long
# waiting for a message, then returns None. Short enough that the
# `_running` flag gets checked several times per second during
# shutdown.
_SUBSCRIBE_POLL_TIMEOUT_S = 1.0


OpName = Literal["l0", "l1", "user"]


class CacheInvalidator:
    """Redis-backed cross-worker invalidation dispatcher.

    One instance per knowledge-service process, started in the
    lifespan hook and registered with `cache.set_invalidator` so the
    existing `cache.invalidate_*` write-path hooks can publish.

    The publisher and subscriber share the same aioredis client —
    aioredis's internal connection pool handles publish while a
    dedicated pubsub() object holds the subscribe connection.
    """

    def __init__(self, redis_url: str, *, origin: str | None = None) -> None:
        self._redis_url = redis_url
        # Per-process origin so a worker can filter its own messages
        # out of the subscription stream (pub/sub delivers to every
        # subscriber including the publisher). UUID, not hostname, so
        # identically-named containers don't collide.
        self.origin = origin or f"ks-{uuid4().hex[:12]}"
        self._redis: aioredis.Redis | None = None
        self._subscriber_task: asyncio.Task[None] | None = None
        self._running = False
        # Track outstanding publish tasks so Python doesn't GC them
        # mid-send. add_done_callback removes the entry once the task
        # finishes — keeps the set bounded to in-flight work.
        self._pending_publishes: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Open the Redis client and start the subscriber loop."""
        if self._running:
            return
        self._redis = aioredis.from_url(
            self._redis_url, decode_responses=True,
        )
        self._running = True
        self._subscriber_task = asyncio.create_task(self._run())
        logger.info(
            "D-T2-04: cache invalidator started origin=%s channel=%s",
            self.origin, CACHE_INVALIDATION_CHANNEL,
        )

    async def stop(self) -> None:
        """Cancel the subscriber and drain pending publishes."""
        self._running = False
        if self._subscriber_task is not None:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except (asyncio.CancelledError, Exception):
                pass
            self._subscriber_task = None
        # Drain any in-flight publishes so we don't lose messages that
        # the writer already handed us. The `add_done_callback` that
        # removes completed tasks from `_pending_publishes` fires on
        # the NEXT event-loop tick, not synchronously on completion,
        # so `gather` alone leaves the set non-empty. A follow-up
        # sleep(0) yields to the loop long enough for the callbacks
        # to fire and the set to drain.
        if self._pending_publishes:
            await asyncio.gather(
                *self._pending_publishes, return_exceptions=True,
            )
            await asyncio.sleep(0)
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                logger.debug(
                    "D-T2-04: redis aclose raised during shutdown",
                    exc_info=True,
                )
            self._redis = None
        logger.info("D-T2-04: cache invalidator stopped")

    # ── publish ────────────────────────────────────────────────────

    def publish(
        self,
        op: OpName,
        user_id: UUID,
        project_id: UUID | None = None,
    ) -> None:
        """Fire-and-forget publish. Safe to call from sync code as
        long as an event loop is running — schedules a task without
        blocking the caller. If Redis is unreachable, the task logs
        a warning; the local pop already succeeded by the time this
        runs so correctness is preserved.
        """
        if self._redis is None:
            return  # invalidator not started — local-only mode
        try:
            task = asyncio.create_task(
                self._send(op, user_id, project_id),
            )
        except RuntimeError:
            # No running event loop (unlikely — all callers are async
            # repo paths). Fall through to local-only; warning would
            # fire every call otherwise.
            return
        self._pending_publishes.add(task)
        task.add_done_callback(self._pending_publishes.discard)

    async def _send(
        self,
        op: OpName,
        user_id: UUID,
        project_id: UUID | None,
    ) -> None:
        payload = {
            "op": op,
            "user_id": str(user_id),
            "project_id": str(project_id) if project_id is not None else None,
            "origin": self.origin,
        }
        try:
            assert self._redis is not None
            await self._redis.publish(
                CACHE_INVALIDATION_CHANNEL,
                json.dumps(payload),
            )
        except Exception as exc:
            # Best-effort publish: local invalidation already ran.
            # Worst case other workers see up-to-60s stale data.
            logger.warning(
                "D-T2-04: publish failed op=%s user=%s err=%s — local invalidation only",
                op, user_id, exc,
            )

    # ── subscribe ──────────────────────────────────────────────────

    async def _run(self) -> None:
        """Main subscriber loop with exponential-backoff reconnect."""
        backoff = _RECONNECT_BACKOFF_INITIAL_S
        while self._running:
            try:
                await self._subscribe_and_dispatch()
                # Clean exit from inner loop → reset backoff.
                backoff = _RECONNECT_BACKOFF_INITIAL_S
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "D-T2-04: subscriber loop error — reconnecting in %.1fs: %s",
                    backoff, exc,
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    raise
                backoff = min(backoff * 2, _RECONNECT_BACKOFF_CAP_S)

    async def _subscribe_and_dispatch(self) -> None:
        """Subscribe and dispatch until the loop is stopped or errors."""
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        try:
            await pubsub.subscribe(CACHE_INVALIDATION_CHANNEL)
            while self._running:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=_SUBSCRIBE_POLL_TIMEOUT_S,
                )
                if msg is None:
                    continue
                self._handle_message(msg)
        finally:
            try:
                await pubsub.unsubscribe(CACHE_INVALIDATION_CHANNEL)
                await pubsub.aclose()
            except Exception:
                logger.debug(
                    "D-T2-04: pubsub cleanup raised", exc_info=True,
                )

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Parse one raw pub/sub message and apply to local caches.

        Malformed messages are dropped with a warning — never raise,
        never stop the subscriber loop for a single bad payload.
        """
        data = msg.get("data")
        if not isinstance(data, str):
            return
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "D-T2-04: malformed invalidation payload err=%s data=%r",
                exc, data[:200],
            )
            return
        if not isinstance(payload, dict):
            return
        # Own-message filter: pub/sub echoes to the publisher.
        if payload.get("origin") == self.origin:
            return

        op = payload.get("op")
        user_id_s = payload.get("user_id")
        project_id_s = payload.get("project_id")

        if not isinstance(op, str) or not isinstance(user_id_s, str):
            return
        try:
            user_id = UUID(user_id_s)
        except (ValueError, TypeError):
            return

        if op == "l0":
            cache.apply_remote_l0_invalidation(user_id)
        elif op == "l1":
            if not isinstance(project_id_s, str):
                return
            try:
                project_id = UUID(project_id_s)
            except (ValueError, TypeError):
                return
            cache.apply_remote_l1_invalidation(user_id, project_id)
        elif op == "user":
            cache.apply_remote_user_invalidation(user_id)
        else:
            logger.debug(
                "D-T2-04: unknown invalidation op=%r — ignoring", op,
            )
