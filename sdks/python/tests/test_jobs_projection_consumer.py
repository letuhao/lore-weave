"""Unified Job Control Plane — `loreweave_jobs.BaseProjectionConsumer` (the 2nd base).

Covers the multi-stream collector scaffold: per-stream BUSYGROUP-safe group create at
``id="0"``, startup PEL drain, XAUTOCLAIM reclaim (incl. tombstone-ack), and the two
error policies (retry→DLQ vs ack-on-error). A tiny in-memory ``FakeRedis`` stands in for
redis.asyncio."""

from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as aioredis

from loreweave_jobs import BaseProjectionConsumer


class FakeRedis:
    def __init__(self, *, busygroup: bool = False):
        self.acked: list[tuple] = []
        self.counters: dict[str, int] = {}
        self.deleted: list[str] = []
        self.groups: list[tuple] = []
        self.pending: dict[str, list] = {}     # stream -> xreadgroup "0" response messages
        self.autoclaim: dict[str, list] = {}   # stream -> [(msg_id, fields), ...]
        self._busygroup = busygroup

    async def xgroup_create(self, stream, group, id="0", mkstream=False):
        if self._busygroup:
            raise aioredis.ResponseError("BUSYGROUP already exists")
        self.groups.append((stream, group, id))

    async def xreadgroup(self, group, consumer, streams, count=None, block=None):
        # id "0" → pending drain; ">" → main loop (always empty here, tests drive via pending/autoclaim)
        out = []
        for stream, sid in streams.items():
            if sid == "0" and self.pending.get(stream):
                out.append((stream, self.pending.pop(stream)))
        return out

    async def xautoclaim(self, stream, group, consumer, min_idle_time, start_id, count):
        msgs = self.autoclaim.pop(stream, [])
        return ("0-0", msgs, [])

    async def xack(self, stream, group, msg_id):
        self.acked.append((stream, group, msg_id))

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, ttl):
        pass

    async def delete(self, key):
        self.deleted.append(key)

    async def aclose(self):
        pass


class _Collector(BaseProjectionConsumer):
    streams = ["loreweave:events:a", "loreweave:events:b"]
    group = "test-collector"
    retry_prefix = "test:proj:retry"

    def __init__(self, *a, raise_on=None, **k):
        super().__init__(*a, **k)
        self.handled: list[tuple] = []
        self.dlq: list[tuple] = []
        self._raise_on = raise_on or set()

    async def handle(self, stream, msg_id, fields):
        self.handled.append((stream, msg_id, fields))
        if msg_id in self._raise_on:
            raise RuntimeError("boom")

    async def on_dlq(self, stream, msg_id, fields, exc):
        self.dlq.append((stream, msg_id, str(exc)))


def test_missing_streams_or_group_raises():
    class NoStreams(BaseProjectionConsumer):
        group = "g"
        async def handle(self, stream, msg_id, fields):  # pragma: no cover
            pass

    class NoGroup(BaseProjectionConsumer):
        streams = ["s"]
        async def handle(self, stream, msg_id, fields):  # pragma: no cover
            pass

    with pytest.raises(ValueError):
        NoStreams("redis://x")
    with pytest.raises(ValueError):
        NoGroup("redis://x")


@pytest.mark.asyncio
async def test_ensure_groups_per_stream_at_id_zero():
    fake = FakeRedis()
    c = _Collector("redis://x", redis_client=fake)
    await c._ensure_groups()
    assert {g[0] for g in fake.groups} == set(_Collector.streams)
    assert all(g[2] == "0" for g in fake.groups)  # collectors replay the backlog


@pytest.mark.asyncio
async def test_ensure_groups_busygroup_safe():
    fake = FakeRedis(busygroup=True)
    c = _Collector("redis://x", redis_client=fake)
    await c._ensure_groups()  # must not raise


@pytest.mark.asyncio
async def test_process_pending_drains_each_stream():
    fake = FakeRedis()
    fake.pending["loreweave:events:a"] = [("1-0", {"event_type": "x"})]
    fake.pending["loreweave:events:b"] = [("2-0", {"event_type": "y"})]
    c = _Collector("redis://x", redis_client=fake)
    await c._process_pending(fake)
    assert len(c.handled) == 2
    assert ("loreweave:events:a", "test-collector", "1-0") in fake.acked
    assert ("loreweave:events:b", "test-collector", "2-0") in fake.acked


@pytest.mark.asyncio
async def test_handle_success_acks():
    fake = FakeRedis()
    c = _Collector("redis://x", redis_client=fake)
    await c._handle_message(fake, "loreweave:events:a", "5-0", {"event_type": "x"})
    assert fake.acked == [("loreweave:events:a", "test-collector", "5-0")]


@pytest.mark.asyncio
async def test_retry_then_dlq_policy():
    fake = FakeRedis()
    c = _Collector("redis://x", redis_client=fake, raise_on={"9-0"})  # ack_on_error False (default)
    fields = {"event_type": "x"}
    # below max: unacked, no DLQ
    await c._handle_message(fake, "loreweave:events:a", "9-0", fields)
    await c._handle_message(fake, "loreweave:events:a", "9-0", fields)
    assert fake.acked == []
    assert c.dlq == []
    # at max: DLQ + ack + retry key cleared
    await c._handle_message(fake, "loreweave:events:a", "9-0", fields)
    assert c.dlq == [("loreweave:events:a", "9-0", "boom")]
    assert ("loreweave:events:a", "test-collector", "9-0") in fake.acked
    assert "test:proj:retry:loreweave:events:a:9-0" in fake.deleted


@pytest.mark.asyncio
async def test_ack_on_error_policy_acks_without_retry_or_dlq():
    class AckOnError(_Collector):
        ack_on_error = True

    fake = FakeRedis()
    c = AckOnError("redis://x", redis_client=fake, raise_on={"7-0"})
    await c._handle_message(fake, "loreweave:events:a", "7-0", {"event_type": "x"})
    assert fake.acked == [("loreweave:events:a", "test-collector", "7-0")]  # acked immediately
    assert c.dlq == []                                                       # no DLQ
    assert fake.counters == {}                                              # no retry counter


@pytest.mark.asyncio
async def test_reclaim_handles_claimed_and_tombstones():
    fake = FakeRedis()
    # one real stale-pending message + one tombstone (empty fields)
    fake.autoclaim["loreweave:events:a"] = [("3-0", {"event_type": "x"}), ("4-0", {})]
    c = _Collector("redis://x", redis_client=fake)
    await c._reclaim_stale_pending(fake)
    assert ("loreweave:events:a", "3-0", {"event_type": "x"}) in c.handled
    # the tombstone is acked to drain the PEL (not handled)
    assert ("loreweave:events:a", "test-collector", "4-0") in fake.acked
    assert all(h[1] != "4-0" for h in c.handled)


@pytest.mark.asyncio
async def test_reclaim_swallows_nogroup():
    fake = FakeRedis()

    async def boom(*a, **k):
        raise aioredis.ResponseError("NOGROUP no such group")

    fake.xautoclaim = boom
    c = _Collector("redis://x", redis_client=fake)
    await c._reclaim_stale_pending(fake)  # must not raise


@pytest.mark.asyncio
async def test_ensure_redis_disables_socket_read_timeout(monkeypatch):
    # The blocking xreadgroup loop MUST use socket_timeout=None (a per-read timeout <
    # block_ms pre-empts the server-side BLOCK and wedges the consumer). Central
    # invariant for both bases — service-level copies of this test are now redundant.
    import loreweave_jobs.projection_consumer as pc

    captured = {}

    def _from_url(url, **kw):
        captured.update(kw)
        return object()

    monkeypatch.setattr(pc.aioredis, "from_url", _from_url)
    c = _Collector("redis://x")  # no injected client → builds via from_url
    await c._ensure_redis()
    assert captured.get("socket_timeout", "MISSING") is None


@pytest.mark.asyncio
async def test_stop_and_close():
    fake = FakeRedis()
    c = _Collector("redis://x", redis_client=fake)
    await c.stop()
    await c.close()  # no error
