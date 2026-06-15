"""``BaseTerminalConsumer`` — the shared Redis-Streams transport scaffold (L2, H4).

Generalises the IDENTICAL transport hand-rolled (and copy-pasted, bugs and all) across
video-gen / translation / worker-ai / learning / knowledge / composition / lore-enrichment
/ campaign consumers. It is a **transport scaffold ONLY** (H4): a subclass supplies the
divergent business logic via template-method hooks; the base deliberately does NOT unify
``handle``/``sweep_once`` (those legitimately differ — over-unifying re-introduces the very
bugs we are deduplicating).

The base owns the bug-copy surface:
- BUSYGROUP-safe ``xgroup_create`` (idempotent group creation),
- startup PEL drain (re-process this consumer's unacked messages from a prior run),
- the blocking read loop with ``socket_timeout=None`` (REQUIRED — a per-read socket
  timeout shorter than ``block_ms`` pre-empts the server-side BLOCK and raises
  ``redis.TimeoutError``, which would crash the task),
- redis-py-8 idle ``TimeoutError``-as-benign (5.x returned ``[]``; 8.x raises),
- an optional ``operation`` pre-filter (drop a foreign event sharing the stream WITHOUT a
  DB round-trip — the D-…-PREFILTER lesson),
- bounded retry → poison-ack (Redis ``INCR`` counter + ``expire``; ack after
  ``max_retries`` so a poison can't redeliver-storm; optional DLQ ``XADD``),
- a periodic sweeper scaffold (``run_sweeper`` → ``sweep_once``).

Cancel-safe: shutdown raises ``CancelledError`` out of the blocking read.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import platform
from typing import Optional

import redis.asyncio as aioredis

from .contract import TERMINAL_STREAM

log = logging.getLogger(__name__)


class BaseTerminalConsumer(abc.ABC):
    """Subclass and set the class attributes + implement ``handle`` (and optionally
    ``sweep_once``). Run ``await consumer.run()`` as a background task; cancel the task
    to stop. ``run_sweeper(...)`` is a separate optional background task.

    Class attributes a subclass MUST/MAY set:
      - ``group`` (REQUIRED) — the consumer-group name.
      - ``stream`` — the stream key (default: the provider-terminal stream).
      - ``operation`` — if set, drop any event whose ``operation`` field is present and
        ≠ this value WITHOUT calling ``handle`` (no DB hit). ``None`` ⇒ always handle.
      - ``consumer_name_prefix`` — used to build the default per-process consumer name.
      - ``retry_prefix`` — Redis key prefix for the per-message retry counter.
      - ``max_retries`` (default 3), ``block_ms`` (default 5000), ``start_id`` (default
        ``"$"`` — new events only; a job in flight at first deploy used the inline path).
      - ``dlq_stream`` — if set, a poisoned message's fields are ``XADD``-ed here before
        the poison-ack (default ``None`` = log + ack only, the current behaviour).
    """

    # ── subclass-overridable transport config ───────────────────────────────────
    stream: str = TERMINAL_STREAM
    group: str = ""  # REQUIRED — a subclass must set this
    operation: Optional[str] = None
    consumer_name_prefix: str = "consumer"
    retry_prefix: str = "jobs:consumer:retry"
    max_retries: int = 3
    block_ms: int = 5000
    start_id: str = "$"
    dlq_stream: Optional[str] = None

    def __init__(
        self,
        redis_url: str,
        *,
        consumer_name: Optional[str] = None,
        redis_client: Optional[aioredis.Redis] = None,
    ) -> None:
        if not self.group:
            raise ValueError(
                f"{type(self).__name__} must set a non-empty `group` class attribute"
            )
        self._redis_url = redis_url
        self._consumer_name = consumer_name or f"{self.consumer_name_prefix}-{platform.node()}"
        # ``redis_client`` is an injection seam for tests (a fake). Production passes None.
        self._redis: Optional[aioredis.Redis] = redis_client
        self._running = False

    # ── transport scaffold (base owns) ───────────────────────────────────────────
    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            # socket_timeout=None is REQUIRED (see module docstring).
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True, socket_timeout=None,
            )
        return self._redis

    async def _ensure_group(self) -> None:
        r = await self._ensure_redis()
        try:
            await r.xgroup_create(self.stream, self.group, id=self.start_id, mkstream=True)
            log.info("created consumer group %s on %s", self.group, self.stream)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise  # a real error — surface it

    async def run(self) -> None:
        """Long-running consume loop. Run via ``asyncio.create_task``/``gather``; cancel
        to stop. Startup: create group + drain this consumer's PEL (recover a prior run's
        unacked), retrying every 5s until Redis is ready."""
        self._running = True
        log.info(
            "%s starting (group=%s consumer=%s stream=%s)",
            type(self).__name__, self.group, self._consumer_name, self.stream,
        )
        r: Optional[aioredis.Redis] = None
        while self._running:
            try:
                await self._ensure_group()
                r = await self._ensure_redis()
                await self._drain(r, "0")  # recover unacked from a prior run
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

        while self._running:
            try:
                results = await r.xreadgroup(
                    self.group, self._consumer_name, {self.stream: ">"},
                    count=10, block=self.block_ms,
                )
                for _stream, messages in results or []:
                    for msg_id, fields in messages:
                        await self._process_msg(r, msg_id, fields)
            except asyncio.CancelledError:
                break
            except aioredis.TimeoutError:
                continue  # idle long-poll — no new events this block window (redis-py 8)
            except aioredis.ConnectionError:
                log.warning("%s: redis connection lost; reconnecting in 5s", type(self).__name__)
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:  # noqa: BLE001 — one bad loop iteration must not kill the task
                log.exception("%s loop error; retrying in 2s", type(self).__name__)
                await asyncio.sleep(2)
        await self.close()

    async def _drain(self, r: aioredis.Redis, start_id: str) -> None:
        """Re-process this consumer's unacked PEL (id '0') — recovers transient-failed
        messages left unacked by a prior run."""
        try:
            results = await r.xreadgroup(
                self.group, self._consumer_name, {self.stream: start_id}, count=100,
            )
            for _stream, messages in results or []:
                for msg_id, fields in messages:
                    await self._process_msg(r, msg_id, fields)
        except Exception:  # noqa: BLE001
            log.exception("%s: error draining pending events", type(self).__name__)

    async def _process_msg(self, r: aioredis.Redis, msg_id: str, fields: dict) -> None:
        """Operation pre-filter → ``handle`` → ack; on exception, bounded retry then
        poison-ack. ``handle`` returning normally (incl. a no-op/ignore) ⇒ ack; raising
        ⇒ leave unacked (redelivered) until ``max_retries``, then ack to stop a storm."""
        # Cheap pre-filter: a foreign operation sharing this stream is dropped without a
        # DB round-trip. A MISSING operation field falls through (back-compat with older
        # events that predate the field). Presence is checked explicitly (not via `or`) so
        # a falsy-but-present value — e.g. an empty-string operation — is still compared
        # and dropped, matching the original `operation is not None` drop semantics.
        if self.operation is not None:
            op = fields.get("operation")
            if op is None:
                op = fields.get(b"operation")
            if op is not None:
                op = op.decode() if isinstance(op, bytes) else str(op)
                if op != self.operation:
                    await r.xack(self.stream, self.group, msg_id)
                    return
        try:
            await self.handle(fields)
            await r.xack(self.stream, self.group, msg_id)
        except Exception as exc:  # noqa: BLE001
            retry_key = f"{self.retry_prefix}:{msg_id}"
            count = int(await r.incr(retry_key))
            await r.expire(retry_key, 3600)
            if count >= self.max_retries:
                if self.dlq_stream:
                    try:
                        await r.xadd(self.dlq_stream, _dlq_fields(fields, exc))
                    except Exception:  # noqa: BLE001 — DLQ best-effort; never block the ack
                        log.exception("%s: DLQ XADD failed for msg=%s", type(self).__name__, msg_id)
                log.error(
                    "%s: msg=%s POISON after %d× — acking to stop redelivery: %s",
                    type(self).__name__, msg_id, count, exc,
                )
                await r.xack(self.stream, self.group, msg_id)
                await r.delete(retry_key)
            else:
                log.warning(
                    "%s: msg=%s failed (%d/%d) — leaving unacked (redelivered): %s",
                    type(self).__name__, msg_id, count, self.max_retries, exc,
                )

    async def run_sweeper(self, *, interval_s: int, timeout_s: int, batch: int) -> None:
        """Periodic stuck-job sweeper (a Redis stream gives no post-ack redelivery, so a
        consumer crash / lost terminal event / submit→persist gap can strand a row).
        Calls ``sweep_once`` each tick. ``interval_s <= 0`` ⇒ disabled."""
        if interval_s <= 0:
            log.info("%s sweeper disabled (interval<=0)", type(self).__name__)
            return
        log.info(
            "%s sweeper started (interval=%ds timeout=%ds batch=%d)",
            type(self).__name__, interval_s, timeout_s, batch,
        )
        while True:
            try:
                n = await self.sweep_once(timeout_s=timeout_s, batch=batch)
                if n:
                    log.info("%s sweep: re-drove %d stuck row(s)", type(self).__name__, n)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad tick must not kill the loop
                log.exception("%s sweeper tick failed", type(self).__name__)
            await asyncio.sleep(interval_s)

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ── template-method hooks (subclass supplies the divergent business logic) ────
    @abc.abstractmethod
    async def handle(self, fields: dict) -> None:
        """Fold ONE message. Return normally to ack (a no-op/ignore — e.g. a foreign job
        with no matching row — is a normal return). Raise to trigger bounded retry /
        poison. MUST be idempotent under at-least-once delivery + sweeper races."""
        raise NotImplementedError

    async def sweep_once(self, *, timeout_s: int, batch: int) -> int:
        """Re-drive rows stranded past ``timeout_s`` (service-specific SQL; use
        ``FOR UPDATE SKIP LOCKED`` so concurrent replicas claim disjoint rows). Return the
        number re-driven. Default: no-op (a consumer with no sweeper leaves this unset)."""
        return 0


def _dlq_fields(fields: dict, exc: Exception) -> dict:
    """Build the DLQ stream entry from a poisoned message's fields (string-keyed)."""
    out: dict[str, str] = {}
    for k, v in fields.items():
        k = k.decode() if isinstance(k, bytes) else str(k)
        v = v.decode() if isinstance(v, bytes) else str(v)
        out[k] = v
    out["_dlq_error"] = str(exc)
    return out
