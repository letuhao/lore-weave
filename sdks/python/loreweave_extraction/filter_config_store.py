"""Cycle 73f — shared Redis-backed config store for the Pass2 precision filter.

Both knowledge-service and worker-ai use this module to share the
runtime-overridable filter config. Architecture:

  - Redis key ``loreweave:precision-filter-config`` is the source of truth
  - JSON payload contains ``schema_version`` + serialized ``PrecisionFilterConfig``
  - Pub/sub channel ``loreweave:precision-filter-reload`` signals "go re-read"
  - Each service caches the config module-level; refreshes on (a) startup
    GET, (b) pubsub message received

Redis is intentionally NOT a hard dependency of the SDK — callers pass
their own ``redis.asyncio.Redis`` client (duck-typed). If a caller never
uses this module, they don't import redis.

Persistence semantics: the Redis key persists across container restarts.
To reset to env-config, ops must explicitly call the reload endpoint with
``disable=true`` (which DELETEs the key).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from loreweave_extraction.pass2_filter import (
    Category,
    PartialPolicy,
    PrecisionFilterConfig,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FILTER_CONFIG_REDIS_KEY",
    "FILTER_RELOAD_PUBSUB_CHANNEL",
    "WIRE_SCHEMA_VERSION",
    "RedisClientProtocol",
    "get_filter_config",
    "set_filter_config",
    "delete_filter_config",
    "subscribe_filter_reload",
]


# Wire constants. Drift between KS publisher and worker subscriber would
# silently break propagation; this module is the single source of truth.
FILTER_CONFIG_REDIS_KEY = "loreweave:precision-filter-config"
FILTER_RELOAD_PUBSUB_CHANNEL = "loreweave:precision-filter-reload"
# Wire schema version. Subscribers that see an unknown version log + skip
# (don't crash) so a rolling-deploy where KS leads doesn't break workers.
WIRE_SCHEMA_VERSION = 1


class RedisClientProtocol(Protocol):
    """Minimal duck-typed interface for the bits we use from
    ``redis.asyncio.Redis``. Lets the SDK avoid a hard redis dep."""

    async def get(self, name: str) -> bytes | str | None: ...
    async def set(self, name: str, value: str) -> Any: ...
    async def delete(self, *names: str) -> int: ...
    async def publish(self, channel: str, message: str) -> int: ...
    def pubsub(self) -> Any: ...


@dataclass(frozen=True)
class _StoredPayload:
    """Internal wire shape for the Redis-stored config JSON.

    Wraps the PrecisionFilterConfig dict in a schema_version envelope so
    we can evolve the on-wire format without breaking deployed services.
    """

    schema_version: int
    config: dict[str, Any]


def _serialize_config(config: PrecisionFilterConfig) -> str:
    """PrecisionFilterConfig → JSON string for Redis storage.

    `dataclasses.asdict` converts the frozen dataclass to dict; tuple
    fields (categories) serialize as JSON arrays. Wrapped in
    schema_version envelope.
    """
    config_dict = dataclasses.asdict(config)
    # categories is Tuple → list for JSON
    if "categories" in config_dict and isinstance(config_dict["categories"], tuple):
        config_dict["categories"] = list(config_dict["categories"])
    payload = {
        "schema_version": WIRE_SCHEMA_VERSION,
        "config": config_dict,
    }
    return json.dumps(payload, sort_keys=True)


def _deserialize_config(raw: bytes | str) -> PrecisionFilterConfig | None:
    """JSON string → PrecisionFilterConfig.

    Returns None on:
      - empty raw
      - malformed JSON
      - unknown schema_version (rolling-deploy safety)
      - missing/wrong-typed fields (defensive — ops could SET garbage)

    Caller treats None as "fall through to env config".
    """
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "filter_config_store: malformed JSON in Redis key %r; "
            "falling through to env config",
            FILTER_CONFIG_REDIS_KEY,
        )
        return None
    if not isinstance(payload, dict):
        logger.warning(
            "filter_config_store: Redis payload is not a dict (got %s); "
            "falling through to env config",
            type(payload).__name__,
        )
        return None
    version = payload.get("schema_version")
    if version != WIRE_SCHEMA_VERSION:
        logger.warning(
            "filter_config_store: unknown schema_version %r in Redis "
            "(expected %d); falling through to env config — "
            "rolling-deploy safety",
            version, WIRE_SCHEMA_VERSION,
        )
        return None
    config_dict = payload.get("config")
    if not isinstance(config_dict, dict):
        logger.warning(
            "filter_config_store: 'config' field missing or wrong type; "
            "falling through to env config",
        )
        return None
    # categories list → tuple for dataclass constructor
    if "categories" in config_dict and isinstance(config_dict["categories"], list):
        config_dict["categories"] = tuple(config_dict["categories"])
    try:
        return PrecisionFilterConfig(**config_dict)
    except (TypeError, ValueError, NotImplementedError) as exc:
        logger.warning(
            "filter_config_store: PrecisionFilterConfig validation "
            "failed (%s); falling through to env config",
            exc,
        )
        return None


async def get_filter_config(
    redis_client: RedisClientProtocol,
) -> PrecisionFilterConfig | None:
    """GET the filter config from Redis. Returns None if key absent or
    payload invalid. Caller treats None as 'use env-config fallback'."""
    raw = await redis_client.get(FILTER_CONFIG_REDIS_KEY)
    return _deserialize_config(raw) if raw else None


async def set_filter_config(
    redis_client: RedisClientProtocol,
    config: PrecisionFilterConfig,
) -> None:
    """SET the filter config + PUBLISH a reload signal. Caller wraps
    in try/except to convert Redis failures into 5xx response."""
    serialized = _serialize_config(config)
    await redis_client.set(FILTER_CONFIG_REDIS_KEY, serialized)
    await redis_client.publish(FILTER_RELOAD_PUBSUB_CHANNEL, "reload")


async def delete_filter_config(
    redis_client: RedisClientProtocol,
) -> None:
    """DELETE the filter config + PUBLISH a reload signal. Subscribers
    re-GET, find empty, fall through to env-config."""
    await redis_client.delete(FILTER_CONFIG_REDIS_KEY)
    await redis_client.publish(FILTER_RELOAD_PUBSUB_CHANNEL, "reload")


async def subscribe_filter_reload(
    redis_client: RedisClientProtocol,
    on_reload: Callable[[], Awaitable[None]],
    *,
    stop_event: Any | None = None,
) -> None:
    """Subscribe to the reload pubsub channel. Calls ``on_reload()`` on
    each message. Loops indefinitely until `stop_event` is set OR the
    coroutine is cancelled.

    Resilient: outer try/except with backoff so subscriber faults don't
    kill the parent task. Mirrors the summary_consumer pattern.
    """
    import asyncio

    backoff_seconds = 2.0
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        pubsub = None
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(FILTER_RELOAD_PUBSUB_CHANNEL)
            logger.info(
                "filter_config_store: subscribed to %s",
                FILTER_RELOAD_PUBSUB_CHANNEL,
            )
            async for message in pubsub.listen():
                if stop_event is not None and stop_event.is_set():
                    return
                # First message after subscribe is the subscribe ack;
                # skip non-message types.
                msg_type = message.get("type") if isinstance(message, dict) else None
                if msg_type != "message":
                    continue
                try:
                    await on_reload()
                except Exception:
                    logger.exception(
                        "filter_config_store: on_reload handler raised — "
                        "subscriber continues",
                    )
            # listen() ended without exception (unusual) → loop back
        except asyncio.CancelledError:
            logger.info("filter_config_store: subscriber cancelled")
            raise
        except Exception:
            logger.exception(
                "filter_config_store: subscriber loop error — "
                "retrying in %.1fs",
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(FILTER_RELOAD_PUBSUB_CHANNEL)
                    await pubsub.aclose()
                except Exception:
                    pass  # best-effort cleanup
