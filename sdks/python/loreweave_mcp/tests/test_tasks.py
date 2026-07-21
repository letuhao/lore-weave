"""ext-tasks durable-gate CORE — store + lifecycle (T1a).

Covers the full task lifecycle the MCP-Tasks durable human gate runs on:
input_required → completed | cancelled | failed, the double-confirm guard, TTL
expiry, and cancel idempotency. Pure/stdlib — no transport, no FastMCP.

M1a: the store binds a resolver REGISTRY (descriptor → the write) at construction,
not a per-create closure — so the SAME interface serves in-memory + a persistent
multi-replica store. A resolver receives the durable {owner_user_id, payload} + the
human's inputs, reconstructed on any replica.
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


async def _noop_resolver(owner_user_id, payload, inputs):
    return {"ok": True, "echo": inputs}


def _store(resolver=_noop_resolver):
    """A store whose registry runs `resolver` for the descriptors the tests use."""
    return InMemoryTaskStore({"book.publish": resolver, "d": resolver})


@pytest.mark.asyncio
async def test_create_starts_input_required():
    s = _store()
    t = await s.create(descriptor="book.publish", owner_user_id="u1",
                       payload={"chapter_id": "ch3"},
                       input_requests={"title": "Publish chapter 3?"})
    assert t.status == INPUT_REQUIRED
    assert t.task_id.startswith("task_")
    assert t.descriptor == "book.publish"
    assert t.owner_user_id == "u1" and t.payload == {"chapter_id": "ch3"}
    assert t.input_requests == {"title": "Publish chapter 3?"}
    # get returns the same task
    got = await s.get(t.task_id)
    assert got.task_id == t.task_id and got.status == INPUT_REQUIRED


@pytest.mark.asyncio
async def test_create_requires_descriptor():
    s = _store()
    with pytest.raises(ValueError):
        await s.create(descriptor="  ", owner_user_id="u1", payload={})


@pytest.mark.asyncio
async def test_get_unknown_raises_not_found():
    s = _store()
    with pytest.raises(TaskNotFound):
        await s.get("task_nope")


@pytest.mark.asyncio
async def test_accept_runs_resolver_and_completes_with_result():
    ran = {}

    async def resolver(owner_user_id, payload, inputs):
        ran["args"] = (owner_user_id, payload, inputs)
        return {"deleted": True}

    s = InMemoryTaskStore({"book.publish": resolver})
    t = await s.create(descriptor="book.publish", owner_user_id="u9", payload={"chapter_id": "ch1"})
    done = await s.provide_input(t.task_id, {"accepted": True, "note": "go"})
    assert done.status == COMPLETED
    assert done.result == {"deleted": True}
    # the resolver got the durable {owner, payload} + the human's inputs — not a closure
    assert ran["args"] == ("u9", {"chapter_id": "ch1"}, {"accepted": True, "note": "go"})


@pytest.mark.asyncio
async def test_accept_with_no_resolver_fails():
    """A descriptor with no registered resolver is a wiring bug → failed with a clear
    message, never a silent no-op."""
    s = InMemoryTaskStore()  # empty registry
    t = await s.create(descriptor="book.publish", owner_user_id="u1", payload={})
    res = await s.provide_input(t.task_id, {"accepted": True})
    assert res.status == FAILED
    assert "resolver" in res.error


@pytest.mark.asyncio
async def test_decline_cancels_without_running_resolver():
    ran = {"called": False}

    async def resolver(owner_user_id, payload, inputs):
        ran["called"] = True
        return None

    for inputs in ({"accepted": False}, {"action": "decline"}):
        s = InMemoryTaskStore({"d": resolver})
        t = await s.create(descriptor="d", owner_user_id="u1", payload={})
        res = await s.provide_input(t.task_id, inputs)
        assert res.status == CANCELLED
    assert ran["called"] is False


@pytest.mark.asyncio
async def test_resolver_error_marks_failed():
    async def boom(owner_user_id, payload, inputs):
        raise RuntimeError("write conflict 409")

    s = InMemoryTaskStore({"book.publish": boom})
    t = await s.create(descriptor="book.publish", owner_user_id="u1", payload={})
    res = await s.provide_input(t.task_id, {"accepted": True})
    assert res.status == FAILED
    assert "409" in res.error


@pytest.mark.asyncio
async def test_double_confirm_is_blocked():
    """A second accept on a resolved task must NOT re-run the resolver (the
    double-commit race chat_suspended_runs already guards)."""
    calls = {"n": 0}

    async def resolver(owner_user_id, payload, inputs):
        calls["n"] += 1
        return {"n": calls["n"]}

    s = InMemoryTaskStore({"book.publish": resolver})
    t = await s.create(descriptor="book.publish", owner_user_id="u1", payload={})
    await s.provide_input(t.task_id, {"accepted": True})
    with pytest.raises(TaskNotWaiting):
        await s.provide_input(t.task_id, {"accepted": True})
    assert calls["n"] == 1  # resolver ran exactly once


@pytest.mark.asyncio
async def test_concurrent_provide_input_single_winner():
    """Two concurrent accepts → the resolver runs exactly once."""
    calls = {"n": 0}
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_resolver(owner_user_id, payload, inputs):
        calls["n"] += 1
        started.set()
        await release.wait()
        return {"n": calls["n"]}

    s = InMemoryTaskStore({"book.publish": slow_resolver})
    t = await s.create(descriptor="book.publish", owner_user_id="u1", payload={})
    first = asyncio.create_task(s.provide_input(t.task_id, {"accepted": True}))
    await started.wait()  # first is inside the resolver, holding the resolving flag
    # a second accept while the first is in-flight must be rejected
    with pytest.raises(TaskNotWaiting):
        await s.provide_input(t.task_id, {"accepted": True})
    release.set()
    done = await first
    assert done.status == COMPLETED and calls["n"] == 1


@pytest.mark.asyncio
async def test_cancel_then_terminal_idempotent():
    s = _store()
    t = await s.create(descriptor="book.publish", owner_user_id="u1", payload={})
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
    s = _store()
    t = await s.create(descriptor="book.publish", owner_user_id="u1", payload={}, ttl_ms=10)
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
    s = _store()
    t = await s.create(descriptor="book.publish", owner_user_id="u1", payload={}, ttl_ms=10)
    await s.provide_input(t.task_id, {"accepted": True})
    got = await s.get(t.task_id, now=t.created_at + 100)
    assert got.status == COMPLETED  # not FAILED
