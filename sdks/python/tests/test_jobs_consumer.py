"""Unified Job Control Plane P1 — `loreweave_jobs.consumer.BaseTerminalConsumer`.

The base is a transport scaffold; these prove the genuinely-shared (bug-copy-prone) bits:
BUSYGROUP-safe group creation, PEL drain, the operation pre-filter, ack-on-success,
bounded-retry-then-poison-ack (+ optional DLQ), and the sweeper scaffold. A tiny in-memory
``FakeRedis`` stands in for redis.asyncio (no fakeredis dependency)."""

from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as aioredis

from loreweave_jobs import BaseTerminalConsumer


class FakeRedis:
    def __init__(self, *, busygroup: bool = False, group_error: Exception | None = None):
        self.acked: list[tuple] = []
        self.counters: dict[str, int] = {}
        self.expired: list[tuple] = []
        self.deleted: list[str] = []
        self.xadds: list[tuple] = []
        self.groups: list[tuple] = []
        self.pending: list = []  # queued xreadgroup responses
        self.closed = False
        self._busygroup = busygroup
        self._group_error = group_error

    async def xgroup_create(self, stream, group, id="$", mkstream=False):
        if self._group_error is not None:
            raise self._group_error
        if self._busygroup:
            raise aioredis.ResponseError("BUSYGROUP Consumer Group name already exists")
        self.groups.append((stream, group, id))

    async def xreadgroup(self, group, consumer, streams, count=None, block=None):
        return self.pending.pop(0) if self.pending else []

    async def xack(self, stream, group, msg_id):
        self.acked.append((stream, group, msg_id))
        return 1

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, ttl):
        self.expired.append((key, ttl))

    async def delete(self, key):
        self.deleted.append(key)
        self.counters.pop(key, None)

    async def xadd(self, stream, fields):
        self.xadds.append((stream, fields))

    async def aclose(self):
        self.closed = True


class _Consumer(BaseTerminalConsumer):
    group = "test-group"
    stream = "loreweave:events:llm_job_terminal"
    operation = "video_gen"
    consumer_name_prefix = "test"
    retry_prefix = "test:retry"
    max_retries = 3

    def __init__(self, *a, always_raise: bool = False, **k):
        super().__init__(*a, **k)
        self.handled: list[dict] = []
        self.always_raise = always_raise

    async def handle(self, fields: dict) -> None:
        self.handled.append(fields)
        if self.always_raise:
            raise RuntimeError("boom")


def _mk(**kw) -> tuple[_Consumer, FakeRedis]:
    fake = FakeRedis(**{k: kw.pop(k) for k in list(kw) if k in ("busygroup", "group_error")})
    return _Consumer("redis://x", redis_client=fake, **kw), fake


def test_missing_group_attr_raises():
    class Bad(BaseTerminalConsumer):
        group = ""  # not set
        async def handle(self, fields):  # pragma: no cover
            pass

    with pytest.raises(ValueError):
        Bad("redis://x")


@pytest.mark.asyncio
async def test_ensure_group_busygroup_is_safe():
    c, _ = _mk(busygroup=True)
    await c._ensure_group()  # must NOT raise


@pytest.mark.asyncio
async def test_ensure_group_other_response_error_reraises():
    c, _ = _mk(group_error=aioredis.ResponseError("WRONGTYPE something else"))
    with pytest.raises(aioredis.ResponseError):
        await c._ensure_group()


@pytest.mark.asyncio
async def test_operation_prefilter_drops_foreign_without_handle():
    c, fake = _mk()
    await c._process_msg(fake, "1-0", {"operation": "chat", "job_id": "x"})
    assert c.handled == []                       # never hit the business fold (no DB round-trip)
    assert fake.acked == [(c.stream, c.group, "1-0")]  # but acked (dealt with)


@pytest.mark.asyncio
async def test_operation_prefilter_passes_matching():
    c, fake = _mk()
    await c._process_msg(fake, "1-0", {"operation": "video_gen", "job_id": "x"})
    assert len(c.handled) == 1
    assert fake.acked == [(c.stream, c.group, "1-0")]


@pytest.mark.asyncio
async def test_operation_none_always_handles():
    class NoFilter(_Consumer):
        operation = None

    fake = FakeRedis()
    c = NoFilter("redis://x", redis_client=fake)
    await c._process_msg(fake, "1-0", {"operation": "anything", "job_id": "x"})
    assert len(c.handled) == 1  # no pre-filter → handle runs regardless of operation


@pytest.mark.asyncio
async def test_handle_missing_operation_field_falls_through():
    c, fake = _mk()  # operation='video_gen' but the event has no operation field
    await c._process_msg(fake, "1-0", {"job_id": "x"})
    assert len(c.handled) == 1  # back-compat — older events without the field still handled


@pytest.mark.asyncio
async def test_empty_string_operation_is_dropped_not_handled():
    # MED-2 regression: a falsy-but-PRESENT operation ("") must be compared + dropped
    # (matches the original `operation is not None` semantics), not collapsed to None.
    c, fake = _mk()
    await c._process_msg(fake, "1-0", {"operation": "", "job_id": "x"})
    assert c.handled == []                              # dropped without a DB round-trip
    assert fake.acked == [(c.stream, c.group, "1-0")]


@pytest.mark.asyncio
async def test_ack_on_success():
    c, fake = _mk()
    await c._process_msg(fake, "9-0", {"operation": "video_gen", "job_id": "x"})
    assert fake.acked == [(c.stream, c.group, "9-0")]
    assert fake.counters == {}  # no retry counter on the happy path


@pytest.mark.asyncio
async def test_bounded_retry_then_poison_ack():
    c, fake = _mk(always_raise=True)
    fields = {"operation": "video_gen", "job_id": "x"}
    # 1st + 2nd delivery: left UNACKED (redelivered), counter climbs.
    await c._process_msg(fake, "5-0", fields)
    await c._process_msg(fake, "5-0", fields)
    assert fake.acked == []
    assert fake.counters["test:retry:5-0"] == 2
    # 3rd delivery (== max_retries): poison-ack + retry key deleted.
    await c._process_msg(fake, "5-0", fields)
    assert fake.acked == [(c.stream, c.group, "5-0")]
    assert "test:retry:5-0" in fake.deleted
    assert ("test:retry:5-0", 3600) in fake.expired


@pytest.mark.asyncio
async def test_poison_writes_dlq_when_configured():
    class WithDLQ(_Consumer):
        dlq_stream = "loreweave:events:llm_job_terminal:dlq"

    fake = FakeRedis()
    c = WithDLQ("redis://x", redis_client=fake, always_raise=True)
    fields = {"operation": "video_gen", "job_id": "x"}
    for _ in range(3):
        await c._process_msg(fake, "7-0", fields)
    assert len(fake.xadds) == 1
    dlq_stream, dlq_fields = fake.xadds[0]
    assert dlq_stream == "loreweave:events:llm_job_terminal:dlq"
    assert dlq_fields["job_id"] == "x"
    assert "_dlq_error" in dlq_fields


@pytest.mark.asyncio
async def test_drain_processes_pel():
    c, fake = _mk()
    fake.pending = [[(c.stream, [("0-1", {"operation": "video_gen", "job_id": "a"})])]]
    await c._drain(fake, "0")
    assert len(c.handled) == 1
    assert fake.acked == [(c.stream, c.group, "0-1")]


@pytest.mark.asyncio
async def test_default_sweep_once_is_noop():
    c, _ = _mk()
    assert await c.sweep_once(timeout_s=60, batch=10) == 0


@pytest.mark.asyncio
async def test_run_sweeper_disabled_returns_immediately():
    c, _ = _mk()
    # interval<=0 must return without entering the loop (no hang).
    await c.run_sweeper(interval_s=0, timeout_s=60, batch=10)


class ScriptedRedis(FakeRedis):
    """FakeRedis whose main-loop xreadgroup ('>' reads) is driven by a script of
    ('batch', data) | ('timeout',) | ('cancel',) steps; the startup drain ('0') is empty.
    When the script is exhausted it raises CancelledError so run() exits cleanly."""

    def __init__(self, script):
        super().__init__()
        self.script = script
        self.calls = 0

    async def xreadgroup(self, group, consumer, streams, count=None, block=None):
        sid = list(streams.values())[0]
        if sid == "0":
            return []  # empty PEL on startup
        if self.calls >= len(self.script):
            raise asyncio.CancelledError()
        step = self.script[self.calls]
        self.calls += 1
        if step[0] == "batch":
            return step[1]
        if step[0] == "timeout":
            raise aioredis.TimeoutError()
        if step[0] == "cancel":
            raise asyncio.CancelledError()
        return []


@pytest.mark.asyncio
async def test_run_dispatches_then_idle_then_cancel_clean_exit():
    # A batch (dispatched + acked), then an idle TimeoutError (must continue, not crash),
    # then script exhaustion → CancelledError → clean break + close.
    batch = [("video-gen-resume", [("1-0", {"operation": "video_gen", "job_id": "a"})])]
    fake = ScriptedRedis([("batch", batch), ("timeout",)])
    c = _Consumer("redis://x", redis_client=fake)
    await asyncio.wait_for(c.run(), timeout=2)
    assert len(c.handled) == 1                          # the batch was folded
    assert fake.acked == [(c.stream, c.group, "1-0")]   # and acked
    assert fake.closed is True                          # CancelledError → close()


@pytest.mark.asyncio
async def test_run_cancel_on_first_read_exits_cleanly():
    fake = ScriptedRedis([("cancel",)])
    c = _Consumer("redis://x", redis_client=fake)
    await asyncio.wait_for(c.run(), timeout=2)
    assert c.handled == []
    assert fake.closed is True


@pytest.mark.asyncio
async def test_close_is_idempotent():
    c, fake = _mk()
    await c.close()
    assert fake.closed is True
    await c.close()  # no error when already closed
