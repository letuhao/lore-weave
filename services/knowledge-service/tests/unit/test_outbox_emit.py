"""Phase B — KS correction outbox emit (best-effort, cross-store §6.6)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.events.outbox_emit import (
    ENTITY_CORRECTED,
    emit_correction,
    entity_correction_payload,
    entity_snapshot,
)

_CANON_ID = "a0eebc999c0b4ef8bb6d6bb9bd380a11"  # 32-hex canonical id (UUID-coercible)


def test_entity_snapshot_shape():
    snap = entity_snapshot("Kai", "character", ["Kai", "Master Kai"])
    assert snap == {"name": "Kai", "kind": "character", "aliases": ["Kai", "Master Kai"]}
    # None aliases normalise to [].
    assert entity_snapshot("X", "k", None)["aliases"] == []


def test_entity_correction_payload_core():
    p = entity_correction_payload(
        user_id="u-1", project_id="p-1", book_id=None, target_id=_CANON_ID,
        op="update", before={"kind": "person"}, after={"kind": "location"}, actor_id="u-1",
    )
    assert p["target_type"] == "entity"
    assert p["target_id"] == _CANON_ID
    assert p["op"] == "update"
    assert p["actor_type"] == "user"
    assert p["actor_id"] == "u-1"
    assert p["before"] == {"kind": "person"} and p["after"] == {"kind": "location"}
    assert "emitted_at" in p


@pytest.mark.asyncio
@patch("app.events.outbox_emit.get_knowledge_pool")
async def test_emit_correction_inserts_with_knowledge_aggregate(mock_get_pool):
    pool = AsyncMock()
    mock_get_pool.return_value = pool
    payload = entity_correction_payload(
        user_id="u-1", project_id=None, book_id=None, target_id=_CANON_ID,
        op="delete", before={"kind": "person"}, after=None, actor_id="u-1",
    )
    await emit_correction(event_type=ENTITY_CORRECTED, aggregate_id=_CANON_ID, payload=payload)

    pool.execute.assert_awaited_once()
    args = pool.execute.await_args.args
    sql = args[0]
    assert "outbox_events" in sql and "'knowledge'" in sql
    # aggregate_id coerced to UUID from the 32-hex canonical id.
    import uuid
    assert args[1] == uuid.UUID(_CANON_ID)
    assert args[2] == ENTITY_CORRECTED
    # payload is JSON-encoded.
    assert json.loads(args[3])["target_id"] == _CANON_ID


@pytest.mark.asyncio
@patch("app.events.outbox_emit.get_knowledge_pool")
async def test_emit_correction_swallows_pool_failure(mock_get_pool):
    # §6.6: a missing/unhealthy pool must NEVER raise (graph write already
    # committed; correction log just under-counts).
    mock_get_pool.side_effect = RuntimeError("pool not initialised")
    # Must not raise:
    await emit_correction(
        event_type=ENTITY_CORRECTED, aggregate_id=_CANON_ID,
        payload={"target_id": _CANON_ID},
    )


@pytest.mark.asyncio
@patch("app.events.outbox_emit.get_knowledge_pool")
async def test_emit_correction_permanent_failure_surfaced(mock_get_pool):
    """FD-19/053: a non-UUID-coercible aggregate_id is a PERMANENT failure — it
    never reaches outbox_events (no replay backstop), so it's counted as
    `permanent` (ERROR + metric), not hidden behind the best-effort warning."""
    from app.metrics import correction_emit_failure_total
    pool = AsyncMock()
    mock_get_pool.return_value = pool
    before = correction_emit_failure_total.labels(kind="permanent")._value.get()
    # uuid.UUID("not-a-uuid") raises ValueError before pool.execute is reached.
    await emit_correction(event_type=ENTITY_CORRECTED, aggregate_id="not-a-uuid", payload={})
    after = correction_emit_failure_total.labels(kind="permanent")._value.get()
    assert after == before + 1
    pool.execute.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.events.outbox_emit.get_knowledge_pool")
async def test_emit_correction_transient_failure_counted(mock_get_pool):
    """A PG/connection error is TRANSIENT (the §10.1 replay backstop applies) →
    counted as `transient`, still swallowed (never fails the committed edit)."""
    import asyncpg
    from app.metrics import correction_emit_failure_total
    pool = AsyncMock()
    pool.execute = AsyncMock(side_effect=asyncpg.PostgresError("connection reset"))
    mock_get_pool.return_value = pool
    before = correction_emit_failure_total.labels(kind="transient")._value.get()
    await emit_correction(
        event_type=ENTITY_CORRECTED, aggregate_id=_CANON_ID, payload={"target_id": _CANON_ID},
    )
    after = correction_emit_failure_total.labels(kind="transient")._value.get()
    assert after == before + 1
