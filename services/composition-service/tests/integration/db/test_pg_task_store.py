"""M1c — the composition PERSISTENT durable-gate store (PgTaskStore), real Postgres.

Mirror of book-service's Go PgTaskStore DB test. Persistence exists for MULTI-REPLICA:
a propose handled by one replica and its accept by ANOTHER (or after a restart) must
resolve the SAME task exactly once. Two PgTaskStore instances over one pool stand in for
two replicas (all task state lives in the DB; the atomicity is Postgres's, not in-process).

Gated on TEST_COMPOSITION_DB_URL (a throwaway DB).
"""
from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.mcp.pg_task_store import PgTaskStore
from loreweave_mcp.tasks import (
    CANCELLED,
    COMPLETED,
    FAILED,
    INPUT_REQUIRED,
    TaskNotWaiting,
)

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run"),
    pytest.mark.xdist_group("pg"),
]

_DESC = "composition.derive"


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        await run_migrations(p)  # creates mcp_gate_tasks (idempotent)
        async with p.acquire() as c:
            await c.execute("DELETE FROM mcp_gate_tasks WHERE descriptor=$1", _DESC)
        yield p
    finally:
        async with p.acquire() as c:
            await c.execute("DELETE FROM mcp_gate_tasks WHERE descriptor=$1", _DESC)
        await p.close()


def _recording_resolver(hits):
    async def resolver(owner_user_id, payload, inputs):
        hits.append({"owner": owner_user_id, "payload": payload, "inputs": inputs})
        return {"done": True, "src": payload.get("src")}
    return resolver


async def test_multi_replica_propose_on_a_accept_on_b(pool):
    hits = []
    reg = {_DESC: _recording_resolver(hits)}
    replica_a = PgTaskStore(lambda: pool, reg)
    replica_b = PgTaskStore(lambda: pool, reg)  # never saw the Create

    owner = str(uuid.uuid4())
    task = await replica_a.create(
        descriptor=_DESC, owner_user_id=owner,
        payload={"src": "proj-1"}, input_requests={"title": "Derive?"},
    )
    assert task.status == INPUT_REQUIRED

    # Replica B reads the durable row (owner + payload survived cross-instance).
    got_b = await replica_b.get(task.task_id)
    assert got_b.status == INPUT_REQUIRED
    assert got_b.owner_user_id == owner and got_b.payload == {"src": "proj-1"}

    # Accept on B → the resolver runs on B (reconstructed from the row) → completed.
    done = await replica_b.provide_input(task.task_id, {"accepted": True, "note": "x"})
    assert done.status == COMPLETED
    assert done.result == {"done": True, "src": "proj-1"}
    assert len(hits) == 1 and hits[0]["owner"] == owner and hits[0]["inputs"]["note"] == "x"

    # A sees the terminal state; a double-accept on EITHER replica is refused (single-winner).
    got_a = await replica_a.get(task.task_id)
    assert got_a.status == COMPLETED
    with pytest.raises(TaskNotWaiting):
        await replica_a.provide_input(task.task_id, {"accepted": True})
    assert len(hits) == 1  # resolver ran exactly once


async def test_decline_cancels_without_resolver(pool):
    hits = []
    store = PgTaskStore(lambda: pool, {_DESC: _recording_resolver(hits)})
    task = await store.create(descriptor=_DESC, owner_user_id=str(uuid.uuid4()), payload={"src": "p"})
    res = await store.provide_input(task.task_id, {"accepted": False})
    assert res.status == CANCELLED
    assert hits == []
    with pytest.raises(TaskNotWaiting):
        await store.provide_input(task.task_id, {"accepted": True})


async def test_ttl_expiry_lapses_to_failed(pool):
    store = PgTaskStore(lambda: pool, {_DESC: _recording_resolver([])})
    task = await store.create(descriptor=_DESC, owner_user_id=str(uuid.uuid4()), payload={}, ttl_ms=1)
    # A get with `now` past the TTL lapses the row to failed and persists it.
    got = await store.get(task.task_id, now=task.created_at + 3600)
    assert got.status == FAILED and got.error == "task_expired"
    with pytest.raises(TaskNotWaiting):
        await store.provide_input(task.task_id, {"accepted": True})


async def test_cancel_idempotent_then_reject(pool):
    store = PgTaskStore(lambda: pool, {_DESC: _recording_resolver([])})
    task = await store.create(descriptor=_DESC, owner_user_id=str(uuid.uuid4()), payload={})
    c = await store.cancel(task.task_id)
    assert c.status == CANCELLED
    c2 = await store.cancel(task.task_id)  # idempotent on terminal
    assert c2.status == CANCELLED
    with pytest.raises(TaskNotWaiting):
        await store.provide_input(task.task_id, {"accepted": True})


async def test_concurrent_accept_single_winner(pool):
    hits = []
    store = PgTaskStore(lambda: pool, {_DESC: _recording_resolver(hits)})
    task = await store.create(descriptor=_DESC, owner_user_id=str(uuid.uuid4()), payload={"src": "z"})

    # Two concurrent accepts (two replicas racing) → the atomic input_required→working
    # claim makes exactly one win; the resolver runs once.
    results = await asyncio.gather(
        store.provide_input(task.task_id, {"accepted": True}),
        store.provide_input(task.task_id, {"accepted": True}),
        return_exceptions=True,
    )
    wins = sum(1 for r in results if not isinstance(r, Exception) and r.status == COMPLETED)
    refused = sum(1 for r in results if isinstance(r, TaskNotWaiting))
    assert wins == 1 and refused == 1, f"results={results}"
    assert len(hits) == 1
