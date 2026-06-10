"""S4d — campaign budget cap consumer.

Consumes the S4b `loreweave:events:campaign_usage` Redis stream (campaign-tagged
usage events emitted by provider-registry's relay) and accumulates each event's
`cost_usd` into the owning campaign's `spent_usd`, auto-pausing it at `budget_usd`.

DISTINCT from the projection consumer (group `campaign-collector`):
  * its own group `campaign-spend`;
  * the usage event is FLAT fields (request_id/campaign_id/cost_usd …) — NOT the
    `{event_type, payload}` envelope the projection streams use;
  * accumulation is a SUM (not convergent), so it dedups on `request_id`
    (campaign_usage_seen PK) AND — unlike projections, which self-heal via the S3
    stuck-timeout — it does NOT ack on a transient failure (money cap must not
    under-count); such entries stay pending and are reclaimed on idle/startup.
"""

from __future__ import annotations

import asyncio
import logging
import platform
from decimal import Decimal, InvalidOperation
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis

from .. import repositories as repo

logger = logging.getLogger(__name__)

CAMPAIGN_USAGE_STREAM = "loreweave:events:campaign_usage"
SPEND_GROUP = "campaign-spend"
BLOCK_MS = 5000

__all__ = ["SpendConsumer", "CAMPAIGN_USAGE_STREAM", "SPEND_GROUP"]


class SpendConsumer:
    """Redis Streams consumer; run() as a lifespan background task."""

    def __init__(
        self,
        redis_url: str,
        pool: asyncpg.Pool,
        *,
        consumer_name: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._pool = pool
        self._consumer_name = consumer_name or f"campaign-spend-{platform.node()}"
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def _ensure_group(self) -> None:
        r = await self._ensure_redis()
        try:
            await r.xgroup_create(CAMPAIGN_USAGE_STREAM, SPEND_GROUP, id="0", mkstream=True)
            logger.info("created consumer group %s on %s", SPEND_GROUP, CAMPAIGN_USAGE_STREAM)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def run(self) -> None:
        self._running = True
        await self._ensure_group()
        r = await self._ensure_redis()
        logger.info("spend consumer started (group=%s, consumer=%s)", SPEND_GROUP, self._consumer_name)
        # Recover entries left pending by a prior run (transient failures).
        await self._drain_pending(r)
        while self._running:
            try:
                results = await r.xreadgroup(
                    SPEND_GROUP, self._consumer_name,
                    {CAMPAIGN_USAGE_STREAM: ">"}, count=50, block=BLOCK_MS,
                )
                if not results:
                    # Idle — retry any entries left pending by a transient failure.
                    await self._drain_pending(r)
                    continue
                for _stream, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(r, msg_id, fields)
            except asyncio.CancelledError:
                break
            except aioredis.TimeoutError:
                continue
            except aioredis.ConnectionError:
                logger.warning("spend consumer redis connection lost, reconnecting in 5s")
                self._redis = None
                await asyncio.sleep(5)
                r = await self._ensure_redis()
            except Exception:
                logger.exception("spend consumer loop error, retrying in 2s")
                await asyncio.sleep(2)
        await self.close()

    async def _drain_pending(self, r: aioredis.Redis) -> None:
        """ONE pass over this consumer's already-delivered-but-unacked entries
        (id "0"). Single pass (no inner loop) so a persistently-failing entry is
        retried on the NEXT drain rather than spun on here."""
        try:
            results = await r.xreadgroup(
                SPEND_GROUP, self._consumer_name, {CAMPAIGN_USAGE_STREAM: "0"}, count=50,
            )
        except aioredis.RedisError:
            return
        for _stream, messages in results:
            for msg_id, fields in messages:
                await self._handle_message(r, msg_id, fields)

    async def _handle_message(self, r: aioredis.Redis, msg_id: str, fields: dict[str, str]) -> None:
        permanent, err = await self._process(fields)
        if err is None:
            await r.xack(CAMPAIGN_USAGE_STREAM, SPEND_GROUP, msg_id)
        elif permanent:
            logger.warning("spend consumer dropping unprocessable event id=%s: %s", msg_id, err)
            await r.xack(CAMPAIGN_USAGE_STREAM, SPEND_GROUP, msg_id)
        else:
            # Transient (DB) — leave pending; reclaimed by _drain_pending. NO ack:
            # the money cap must not under-count on a blip.
            logger.warning("spend consumer transient failure id=%s (will retry): %s", msg_id, err)

    async def _process(self, fields: dict[str, str]) -> tuple[bool, Exception | None]:
        """Returns (permanent, error). permanent=True → a malformed event (drop);
        a non-nil error with permanent=False is transient (retry)."""
        try:
            request_id = UUID(fields.get("request_id") or "")
            campaign_id = UUID(fields.get("campaign_id") or "")
        except (ValueError, TypeError) as e:
            return True, e  # malformed ids — never reprocessable
        # cost_usd is empty for an unpriced model; an unparseable value is treated
        # as 0 (the dedup row is still written so it's not reprocessed).
        cost = Decimal(0)
        raw = fields.get("cost_usd") or ""
        if raw:
            try:
                cost = Decimal(raw)
            except (InvalidOperation, ValueError):
                cost = Decimal(0)
        try:
            await repo.accumulate_and_maybe_pause(
                self._pool, request_id=request_id, campaign_id=campaign_id, cost_usd=cost,
            )
            return False, None
        except Exception as e:  # DB/tx error — transient, retry
            return False, e

    async def stop(self) -> None:
        self._running = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
