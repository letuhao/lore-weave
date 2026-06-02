"""B2-A — handle_run_completed: registry upsert + run insert, dedup, loud-fail."""

import uuid

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import handle_run_completed


class FakeConn:
    def __init__(self):
        self.calls = []  # list of (sql, params)

    async def execute(self, sql, *params):
        self.calls.append((sql, params))

    def transaction(self):
        class _Txn:
            async def __aenter__(self_):
                return None

            async def __aexit__(self_, *a):
                return False

        return _Txn()


class FakePool:
    def __init__(self):
        self.conn = FakeConn()

    def acquire(self):
        conn = self.conn

        class _Acq:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False

        return _Acq()


def _run_event(*, outbox_id="outbox-run-1", **payload_over):
    payload = {
        "run_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "project_id": str(uuid.uuid4()),
        "book_id": str(uuid.uuid4()),
        "job_id": str(uuid.uuid4()),
        "scope": "chapter",
        "chapter_ref": "ch-01",
        "config_hash": "a" * 64,
        "resolved_config": {"model_ref": "m"},
        "prompt_versions": {"entity": "v1-entity-aaaaaaaa"},
        "base_default_version": "deadbeef",
        "model_ref": "m",
        "metrics": {"entities_merged": 3, "relations_created": 2},
        "outcome": "succeeded",
        "outcome_source": "pipeline",
        "emitted_at": "2026-05-31T00:00:00Z",
    }
    payload.update(payload_over)
    return EventData(
        stream="loreweave:events:knowledge",
        message_id="1-0",
        event_type="knowledge.extraction_run_completed",
        aggregate_id=payload["run_id"],
        payload=payload,
        source="knowledge",
        raw={},
        outbox_id=outbox_id,
    )


async def test_run_completed_upserts_registry_then_inserts_run():
    pool = FakePool()
    ev = _run_event()
    await handle_run_completed(ev, pool=pool)

    calls = pool.conn.calls
    assert len(calls) == 2
    registry_sql, registry_params = calls[0]
    run_sql, run_params = calls[1]
    assert "config_registry" in registry_sql
    assert "ON CONFLICT (config_hash) DO NOTHING" in registry_sql
    assert registry_params[0] == "a" * 64                     # config_hash PK
    assert "extraction_runs" in run_sql
    assert "ON CONFLICT (origin_service, origin_event_id) DO NOTHING" in run_sql
    # run insert positional params (see handler INSERT order)
    assert isinstance(run_params[0], uuid.UUID)                # run_id
    assert run_params[7] == "a" * 64                           # config_hash FK
    assert run_params[10] == "succeeded"                       # outcome
    assert run_params[11] == "pipeline"                        # outcome_source
    # [12] = genre (None for events that predate E2)
    assert run_params[13] == "knowledge"                       # origin_service
    assert run_params[14] == "outbox-run-1"                    # origin_event_id (dedup key)


async def test_outcome_source_defaults_to_pipeline_when_missing():
    pool = FakePool()
    ev = _run_event()
    ev.payload.pop("outcome_source")
    await handle_run_completed(ev, pool=pool)
    assert pool.conn.calls[1][1][11] == "pipeline"


async def test_empty_outbox_id_raises_for_dlq():
    pool = FakePool()
    with pytest.raises(ValueError, match="empty outbox_id"):
        await handle_run_completed(_run_event(outbox_id=""), pool=pool)
    assert pool.conn.calls == []


@pytest.mark.parametrize("missing", ["run_id", "user_id", "config_hash"])
async def test_missing_required_field_raises(missing):
    pool = FakePool()
    ev = _run_event()
    ev.payload[missing] = None
    with pytest.raises(ValueError, match="missing run_id/user_id/config_hash"):
        await handle_run_completed(ev, pool=pool)
    assert pool.conn.calls == []


async def test_run_completed_stores_genre():
    """E2 — genre from payload stored at param[12] in the runs INSERT."""
    pool = FakePool()
    ev = _run_event(genre="Tiên hiệp")
    await handle_run_completed(ev, pool=pool)
    _, run_params = pool.conn.calls[1]
    assert run_params[12] == "Tiên hiệp"


async def test_run_completed_genre_none_when_absent():
    """E2 — genre absent from payload → NULL in DB (no KeyError)."""
    pool = FakePool()
    ev = _run_event()
    # no "genre" key in payload (pre-E2 event)
    ev.payload.pop("genre", None)
    await handle_run_completed(ev, pool=pool)
    _, run_params = pool.conn.calls[1]
    assert run_params[12] is None
