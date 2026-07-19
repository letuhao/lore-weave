"""ext-tasks durable-gate CORE — store + lifecycle (T1a).

Covers the full task lifecycle the MCP-Tasks durable human gate runs on:
input_required → completed | cancelled | failed, the double-confirm guard, TTL
expiry, and cancel idempotency. Pure/stdlib — no transport, no FastMCP.
"""
from __future__ import annotations

import asyncio

import pytest

from loreweave_mcp.tasks import (
    CANCELLED,
    COMPLETED,
    FAILED,
    INPUT_REQUIRED,
    InMemoryTaskStore,
    TaskNotFound,
    TaskNotWaiting,
    WORKING,
)


async def _noop_executor(inputs):
    return {"ok": True, "echo": inputs}


@pytest.mark.asyncio
async def test_create_starts_input_required():
    s = InMemoryTaskStore()
    t = await s.create(descriptor="book.publish", executor=_noop_executor,
                       input_requests={"title": "Publish chapter 3?"})
    assert t.status == INPUT_REQUIRED
    assert t.task_id.startswith("task_")
    assert t.descriptor == "book.publish"
    assert t.input_requests == {"title": "Publish chapter 3?"}
    # get returns the same task
    got = await s.get(t.task_id)
    assert got.task_id == t.task_id and got.status == INPUT_REQUIRED


@pytest.mark.asyncio
async def test_create_requires_descriptor():
    s = InMemoryTaskStore()
    with pytest.raises(ValueError):
        await s.create(descriptor="  ", executor=_noop_executor)


@pytest.mark.asyncio
async def test_get_unknown_raises_not_found():
    s = InMemoryTaskStore()
    with pytest.raises(TaskNotFound):
        await s.get("task_nope")


@pytest.mark.asyncio
async def test_accept_runs_executor_and_completes_with_result():
    s = InMemoryTaskStore()
    ran = {}

    async def executor(inputs):
        ran["called"] = inputs
        return {"deleted": True}

    t = await s.create(descriptor="book.publish", executor=executor)
    done = await s.provide_input(t.task_id, {"accepted": True, "note": "go"})
    assert done.status == COMPLETED
    assert done.result == {"deleted": True}
    assert ran["called"] == {"accepted": True, "note": "go"}  # inputs threaded through


@pytest.mark.asyncio
async def test_decline_cancels_without_running_executor():
    s = InMemoryTaskStore()
    ran = {"called": False}

    async def executor(inputs):
        ran["called"] = True
        return None

    t = await s.create(descriptor="book.publish", executor=executor)
    for inputs in ({"accepted": False}, {"action": "decline"}):
        s2 = InMemoryTaskStore()
        t2 = await s2.create(descriptor="d", executor=executor)
        res = await s2.provide_input(t2.task_id, inputs)
        assert res.status == CANCELLED
    # the first store's executor never ran
    assert ran["called"] is False


@pytest.mark.asyncio
async def test_executor_error_marks_failed():
    s = InMemoryTaskStore()

    async def boom(inputs):
        raise RuntimeError("write conflict 409")

    t = await s.create(descriptor="book.publish", executor=boom)
    res = await s.provide_input(t.task_id, {"accepted": True})
    assert res.status == FAILED
    assert "409" in res.error


@pytest.mark.asyncio
async def test_double_confirm_is_blocked():
    """A second accept on a resolved task must NOT re-run the executor (the
    double-commit race chat_suspended_runs already guards)."""
    s = InMemoryTaskStore()
    calls = {"n": 0}

    async def executor(inputs):
        calls["n"] += 1
        return {"n": calls["n"]}

    t = await s.create(descriptor="book.publish", executor=executor)
    await s.provide_input(t.task_id, {"accepted": True})
    with pytest.raises(TaskNotWaiting):
        await s.provide_input(t.task_id, {"accepted": True})
    assert calls["n"] == 1  # executor ran exactly once


@pytest.mark.asyncio
async def test_concurrent_provide_input_single_winner():
    """Two concurrent accepts → the executor runs exactly once."""
    s = InMemoryTaskStore()
    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_executor(inputs):
        calls["n"] += 1
        started.set()
        await release.wait()
        return {"n": calls["n"]}

    t = await s.create(descriptor="book.publish", executor=slow_executor)
    first = asyncio.create_task(s.provide_input(t.task_id, {"accepted": True}))
    await started.wait()  # first is inside the executor, holding the resolving flag
    # a second accept while the first is in-flight must be rejected
    with pytest.raises(TaskNotWaiting):
        await s.provide_input(t.task_id, {"accepted": True})
    release.set()
    done = await first
    assert done.status == COMPLETED and calls["n"] == 1


@pytest.mark.asyncio
async def test_cancel_then_terminal_idempotent():
    s = InMemoryTaskStore()
    t = await s.create(descriptor="book.publish", executor=_noop_executor)
    c = await s.cancel(t.task_id)
    assert c.status == CANCELLED
    # cancel again — idempotent, still cancelled, no error
    c2 = await s.cancel(t.task_id)
    assert c2.status == CANCELLED
    # provide_input after cancel is rejected (terminal)
    with pytest.raises(TaskNotWaiting):
        await s.provide_input(t.task_id, {"accepted": True})


@pytest.mark.asyncio
async def test_ttl_expiry_lapses_to_failed_on_get():
    s = InMemoryTaskStore()
    t = await s.create(descriptor="book.publish", executor=_noop_executor, ttl_ms=10)
    # a get far in the future sees the task lapsed to failed (token_expired analogue)
    future = t.created_at + 100  # seconds
    got = await s.get(t.task_id, now=future)
    assert got.status == FAILED and got.error == "task_expired"
    # and a post-expiry accept is refused
    with pytest.raises(TaskNotWaiting):
        await s.provide_input(t.task_id, {"accepted": True})


@pytest.mark.asyncio
async def test_completed_task_not_expired_by_ttl():
    """A terminal task is never re-lapsed by TTL (its result must survive polling)."""
    s = InMemoryTaskStore()
    t = await s.create(descriptor="book.publish", executor=_noop_executor, ttl_ms=10)
    await s.provide_input(t.task_id, {"accepted": True})
    got = await s.get(t.task_id, now=t.created_at + 100)
    assert got.status == COMPLETED  # not FAILED
