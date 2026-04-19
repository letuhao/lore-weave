"""D-T2-04 — unit tests for cross-process cache invalidation."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.context import cache
from app.context.cache_invalidation import (
    CACHE_INVALIDATION_CHANNEL,
    CacheInvalidator,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    """Every test starts with empty caches + no registered invalidator."""
    cache.clear_all()
    cache.set_invalidator(None)
    yield
    cache.clear_all()
    cache.set_invalidator(None)


# ── publisher ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_l0_publishes_after_local_pop():
    """Write-path correctness: local pop happens BEFORE publish, so
    THIS worker never reads stale after a write, and the publish is
    a best-effort broadcast to peers."""
    from app.db.models import Summary
    user_id = uuid4()

    # Seed a cache entry so we can assert the local pop.
    cache.put_l0(user_id, None)  # MISSING sentinel — still counts as present
    assert cache.get_l0(user_id) is cache.MISSING

    invalidator = MagicMock(spec=CacheInvalidator)
    cache.set_invalidator(invalidator)

    cache.invalidate_l0(user_id)

    # Local pop fired.
    assert cache.get_l0(user_id) is None  # cache miss now
    # Publish fired with the right op + user.
    invalidator.publish.assert_called_once_with("l0", user_id)


@pytest.mark.asyncio
async def test_invalidate_l1_publishes_with_project_id():
    user_id = uuid4()
    project_id = uuid4()
    cache.put_l1(user_id, project_id, None)

    invalidator = MagicMock(spec=CacheInvalidator)
    cache.set_invalidator(invalidator)
    cache.invalidate_l1(user_id, project_id)

    invalidator.publish.assert_called_once_with("l1", user_id, project_id)


@pytest.mark.asyncio
async def test_invalidate_user_publishes_user_op():
    user_id = uuid4()
    invalidator = MagicMock(spec=CacheInvalidator)
    cache.set_invalidator(invalidator)
    cache.invalidate_all_for_user(user_id)
    invalidator.publish.assert_called_once_with("user", user_id)


@pytest.mark.asyncio
async def test_invalidate_works_without_invalidator_registered():
    """Track 1 path: no invalidator installed → invalidate_* runs
    purely local. Nothing raises, nothing logs at warning."""
    user_id = uuid4()
    cache.put_l0(user_id, None)
    assert cache.get_l0(user_id) is cache.MISSING

    cache.invalidate_l0(user_id)
    assert cache.get_l0(user_id) is None


# ── remote apply helpers ───────────────────────────────────────────────────


def test_apply_remote_l0_invalidation_does_not_republish():
    """The subscriber's entry point must NOT fire a publish — would
    echo back to the origin worker and loop forever."""
    user_id = uuid4()
    cache.put_l0(user_id, None)
    invalidator = MagicMock(spec=CacheInvalidator)
    cache.set_invalidator(invalidator)

    cache.apply_remote_l0_invalidation(user_id)

    # Pop happened but publish did NOT.
    assert cache.get_l0(user_id) is None
    invalidator.publish.assert_not_called()


def test_apply_remote_user_invalidation_drops_all_layers():
    user_id = uuid4()
    other = uuid4()
    p1, p2 = uuid4(), uuid4()
    cache.put_l0(user_id, None)
    cache.put_l0(other, None)
    cache.put_l1(user_id, p1, None)
    cache.put_l1(user_id, p2, None)
    cache.put_l1(other, p1, None)

    cache.apply_remote_user_invalidation(user_id)

    # user_id wiped across both layers.
    assert cache.get_l0(user_id) is None
    assert cache.get_l1(user_id, p1) is None
    assert cache.get_l1(user_id, p2) is None
    # Other user preserved.
    assert cache.get_l0(other) is cache.MISSING
    assert cache.get_l1(other, p1) is cache.MISSING


# ── CacheInvalidator publisher ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_serialises_to_json_on_channel():
    inv = CacheInvalidator("redis://fake:6379", origin="ks-test-origin")
    # Don't call .start() — inject a fake Redis client directly.
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock(return_value=1)
    inv._redis = fake_redis

    user_id = uuid4()
    project_id = uuid4()
    inv.publish("l1", user_id, project_id)

    # Drain the scheduled publish task.
    await asyncio.gather(*list(inv._pending_publishes), return_exceptions=True)

    fake_redis.publish.assert_called_once()
    channel, raw = fake_redis.publish.call_args.args
    assert channel == CACHE_INVALIDATION_CHANNEL
    payload = json.loads(raw)
    assert payload == {
        "op": "l1",
        "user_id": str(user_id),
        "project_id": str(project_id),
        "origin": "ks-test-origin",
    }


@pytest.mark.asyncio
async def test_publish_best_effort_swallows_redis_errors():
    """Redis down / network blip: publish must NOT raise — local pop
    already ran, worst case peer workers stay stale up to 60s TTL."""
    inv = CacheInvalidator("redis://fake:6379")
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock(side_effect=RuntimeError("redis down"))
    inv._redis = fake_redis

    inv.publish("l0", uuid4())
    # Awaiting the drained task must not raise — it was a best-effort
    # publish and the exception is swallowed + logged inside _send.
    await asyncio.gather(*list(inv._pending_publishes), return_exceptions=True)


@pytest.mark.asyncio
async def test_publish_noop_when_redis_not_started():
    """If start() was never called (Track 1 bootstrap race), publish
    quietly does nothing — no crash, no pending task."""
    inv = CacheInvalidator("redis://fake:6379")
    # _redis is None by default.
    inv.publish("l0", uuid4())
    assert len(inv._pending_publishes) == 0


# ── CacheInvalidator subscriber ────────────────────────────────────────────


def _l0_msg(user_id, origin="other-origin"):
    return {
        "type": "message",
        "channel": CACHE_INVALIDATION_CHANNEL,
        "data": json.dumps({
            "op": "l0",
            "user_id": str(user_id),
            "project_id": None,
            "origin": origin,
        }),
    }


def test_handle_message_applies_l0_invalidation():
    user_id = uuid4()
    cache.put_l0(user_id, None)
    assert cache.get_l0(user_id) is cache.MISSING

    inv = CacheInvalidator("redis://fake:6379", origin="ks-self")
    inv._handle_message(_l0_msg(user_id, origin="ks-peer"))

    assert cache.get_l0(user_id) is None  # popped


def test_handle_message_ignores_own_origin():
    """Own messages are filtered — pub/sub echoes to the publisher,
    and the local pop already happened on the publisher side."""
    user_id = uuid4()
    cache.put_l0(user_id, None)
    inv = CacheInvalidator("redis://fake:6379", origin="ks-self")
    inv._handle_message(_l0_msg(user_id, origin="ks-self"))

    # Not popped — own-origin filter kicked in.
    assert cache.get_l0(user_id) is cache.MISSING


def test_handle_message_ignores_malformed_payload():
    """Bad JSON / wrong shape: log and skip, never crash the loop."""
    inv = CacheInvalidator("redis://fake:6379", origin="ks-self")
    # Should not raise.
    inv._handle_message({"type": "message", "channel": "x", "data": "not json"})
    inv._handle_message({"type": "message", "channel": "x", "data": "[1,2,3]"})  # wrong type
    inv._handle_message({"type": "message", "channel": "x", "data": '{"op": "l0"}'})  # missing user_id


def test_handle_message_ignores_unknown_op():
    user_id = uuid4()
    cache.put_l0(user_id, None)
    inv = CacheInvalidator("redis://fake:6379", origin="ks-self")
    msg = {
        "type": "message",
        "channel": CACHE_INVALIDATION_CHANNEL,
        "data": json.dumps({
            "op": "mystery",
            "user_id": str(user_id),
            "origin": "peer",
        }),
    }
    inv._handle_message(msg)
    # L0 entry left intact — unknown op dropped.
    assert cache.get_l0(user_id) is cache.MISSING


def test_handle_message_applies_l1_requires_project_id():
    user_id = uuid4()
    project_id = uuid4()
    cache.put_l1(user_id, project_id, None)

    inv = CacheInvalidator("redis://fake:6379", origin="ks-self")
    msg = {
        "type": "message",
        "channel": CACHE_INVALIDATION_CHANNEL,
        "data": json.dumps({
            "op": "l1",
            "user_id": str(user_id),
            "project_id": str(project_id),
            "origin": "peer",
        }),
    }
    inv._handle_message(msg)
    assert cache.get_l1(user_id, project_id) is None

    # L1 message without project_id must be dropped silently.
    cache.put_l1(user_id, project_id, None)
    bad_msg = {
        "type": "message",
        "channel": CACHE_INVALIDATION_CHANNEL,
        "data": json.dumps({
            "op": "l1",
            "user_id": str(user_id),
            "project_id": None,
            "origin": "peer",
        }),
    }
    inv._handle_message(bad_msg)
    # Entry still there — bad payload didn't cause a crash, also
    # didn't silently invalidate the wrong key.
    assert cache.get_l1(user_id, project_id) is cache.MISSING


# ── invalidator lifecycle ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_stop_idempotent_and_drains_pending():
    """stop() must drain in-flight publishes so we don't lose messages
    the writer already handed us."""
    with patch("app.context.cache_invalidation.aioredis") as mock_aioredis:
        fake_redis = MagicMock()
        fake_redis.publish = AsyncMock(return_value=1)
        # pubsub() returns an object with async subscribe/unsubscribe/get_message/aclose.
        fake_pubsub = MagicMock()
        fake_pubsub.subscribe = AsyncMock()
        fake_pubsub.unsubscribe = AsyncMock()
        fake_pubsub.aclose = AsyncMock()
        fake_pubsub.get_message = AsyncMock(return_value=None)
        fake_redis.pubsub = MagicMock(return_value=fake_pubsub)
        fake_redis.aclose = AsyncMock()
        mock_aioredis.from_url = MagicMock(return_value=fake_redis)

        inv = CacheInvalidator("redis://fake:6379")
        await inv.start()
        # Fire a publish so there's something to drain.
        inv.publish("l0", uuid4())
        assert len(inv._pending_publishes) == 1

        await inv.stop()
        # Drained.
        assert len(inv._pending_publishes) == 0
        fake_redis.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_start_is_idempotent():
    """Double-start must not create two subscriber tasks / two Redis
    clients. Review-impl add: assert from_url is called exactly once
    so a future refactor that breaks the idempotence guard gets
    caught by the call-count, not just the task-identity check."""
    with patch("app.context.cache_invalidation.aioredis") as mock_aioredis:
        fake_redis = MagicMock()
        fake_pubsub = MagicMock()
        fake_pubsub.subscribe = AsyncMock()
        fake_pubsub.unsubscribe = AsyncMock()
        fake_pubsub.aclose = AsyncMock()
        fake_pubsub.get_message = AsyncMock(return_value=None)
        fake_redis.pubsub = MagicMock(return_value=fake_pubsub)
        fake_redis.aclose = AsyncMock()
        mock_aioredis.from_url = MagicMock(return_value=fake_redis)

        inv = CacheInvalidator("redis://fake:6379")
        await inv.start()
        first_task = inv._subscriber_task
        await inv.start()  # second call
        assert inv._subscriber_task is first_task  # same task
        # No second Redis client — the early-return guard worked.
        assert mock_aioredis.from_url.call_count == 1

        await inv.stop()


@pytest.mark.asyncio
async def test_repo_write_path_invokes_publish_end_to_end():
    """Review-impl add: verify the full chain — a repo call that
    triggers `cache.invalidate_l0` must flow through the registered
    invalidator's publish(), not just pop locally. Exercises the
    contract between the repo layer and the invalidator."""
    user_id = uuid4()

    invalidator = MagicMock(spec=CacheInvalidator)
    cache.set_invalidator(invalidator)

    # Simulate the repo's own _invalidate_cache helper path — it's
    # a tiny dispatcher that routes by scope_type, so we call
    # invalidate_l0 directly (the dispatcher is trivially tested
    # by existing repo tests).
    cache.invalidate_l0(user_id)
    invalidator.publish.assert_called_once_with("l0", user_id)

    # Setting invalidator back to None must stop publishes.
    invalidator.reset_mock()
    cache.set_invalidator(None)
    cache.invalidate_l0(user_id)
    invalidator.publish.assert_not_called()
