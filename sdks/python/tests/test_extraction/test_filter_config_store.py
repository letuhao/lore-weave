"""Cycle 73f — unit tests for filter_config_store (Redis-backed config store).

Covers serialization round-trip + parser defensiveness + pubsub plumbing.
Mocks the Redis client (duck-typed per RedisClientProtocol)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from loreweave_extraction.filter_config_store import (
    FILTER_CONFIG_REDIS_KEY,
    FILTER_RELOAD_PUBSUB_CHANNEL,
    WIRE_SCHEMA_VERSION,
    _deserialize_config,
    _serialize_config,
    delete_filter_config,
    get_filter_config,
    set_filter_config,
)
from loreweave_extraction.pass2_filter import PrecisionFilterConfig


# ── Serialization round-trip ────────────────────────────────────────


def test_serialize_deserialize_round_trip_preserves_config():
    """JSON round-trip preserves all fields incl. categories tuple shape."""
    original = PrecisionFilterConfig(
        model_ref="claude-uuid-x",
        model_source="user_model",
        partial_policy="drop",
        categories=("relation",),
        max_items_per_batch=5,
        transient_retry_budget=2,
    )

    raw = _serialize_config(original)
    parsed = _deserialize_config(raw)

    assert parsed is not None
    assert parsed.model_ref == "claude-uuid-x"
    assert parsed.model_source == "user_model"
    assert parsed.partial_policy == "drop"
    assert parsed.categories == ("relation",)  # round-tripped as tuple
    assert parsed.max_items_per_batch == 5
    assert parsed.transient_retry_budget == 2


def test_serialize_wraps_in_schema_version_envelope():
    """Wire payload has schema_version envelope for rolling-deploy safety."""
    config = PrecisionFilterConfig(model_ref="x")
    raw = _serialize_config(config)
    parsed = json.loads(raw)

    assert parsed["schema_version"] == WIRE_SCHEMA_VERSION
    assert "config" in parsed
    assert parsed["config"]["model_ref"] == "x"


def test_deserialize_skips_unknown_schema_version():
    """Rolling-deploy safety: subscriber on old code sees newer
    schema_version → logs warning + returns None (fall through to env)."""
    payload = json.dumps({
        "schema_version": WIRE_SCHEMA_VERSION + 99,
        "config": {"model_ref": "x"},
    })
    result = _deserialize_config(payload)
    assert result is None  # rejected — schema mismatch


def test_deserialize_skips_malformed_json():
    """Defensive: malformed Redis payload doesn't crash subscribers."""
    result = _deserialize_config("{not valid json")
    assert result is None


def test_deserialize_skips_missing_config_field():
    """Wrong-shape payload (missing 'config') → None."""
    payload = json.dumps({"schema_version": WIRE_SCHEMA_VERSION, "other": "junk"})
    assert _deserialize_config(payload) is None


def test_deserialize_skips_invalid_config_field_types():
    """PrecisionFilterConfig validation failure → None."""
    # max_items_per_batch must be >= 1; __post_init__ raises ValueError.
    payload = json.dumps({
        "schema_version": WIRE_SCHEMA_VERSION,
        "config": {"model_ref": "x", "max_items_per_batch": 0},
    })
    assert _deserialize_config(payload) is None


def test_deserialize_handles_bytes_input():
    """Real Redis returns bytes; deserializer tolerates both bytes + str."""
    config = PrecisionFilterConfig(model_ref="x")
    raw_str = _serialize_config(config)
    raw_bytes = raw_str.encode("utf-8")
    assert _deserialize_config(raw_bytes) is not None


# ── Redis client interactions (duck-typed mocks) ─────────────────


@pytest.mark.asyncio
async def test_get_filter_config_returns_none_on_missing_key():
    """Empty Redis (key absent) → returns None → caller falls through to env."""
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=None)

    result = await get_filter_config(mock_client)
    assert result is None
    mock_client.get.assert_called_once_with(FILTER_CONFIG_REDIS_KEY)


@pytest.mark.asyncio
async def test_set_filter_config_writes_key_and_publishes():
    """set_filter_config writes Redis key + publishes reload signal."""
    mock_client = MagicMock()
    mock_client.set = AsyncMock()
    mock_client.publish = AsyncMock()

    config = PrecisionFilterConfig(
        model_ref="x", categories=("relation",), partial_policy="drop",
    )
    await set_filter_config(mock_client, config)

    mock_client.set.assert_called_once()
    args, _ = mock_client.set.call_args
    assert args[0] == FILTER_CONFIG_REDIS_KEY
    # value is a JSON string — verify it round-trips
    parsed = json.loads(args[1])
    assert parsed["schema_version"] == WIRE_SCHEMA_VERSION
    assert parsed["config"]["model_ref"] == "x"

    mock_client.publish.assert_called_once_with(
        FILTER_RELOAD_PUBSUB_CHANNEL, "reload",
    )


@pytest.mark.asyncio
async def test_delete_filter_config_deletes_key_and_publishes():
    """delete_filter_config DELETEs the key + publishes signal (so
    subscribers re-GET, find empty, fall through to env)."""
    mock_client = MagicMock()
    mock_client.delete = AsyncMock(return_value=1)
    mock_client.publish = AsyncMock()

    await delete_filter_config(mock_client)

    mock_client.delete.assert_called_once_with(FILTER_CONFIG_REDIS_KEY)
    mock_client.publish.assert_called_once_with(
        FILTER_RELOAD_PUBSUB_CHANNEL, "reload",
    )
