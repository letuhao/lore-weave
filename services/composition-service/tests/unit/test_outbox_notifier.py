"""D-C-PRODUCER-OUTBOX — the durable notification producer.

Proves OutboxNotifier writes an `aggregate_type='notification'` outbox row (which
worker-infra's relay delivers to notification-service) carrying the ingest body +
a deterministic dedup_key, instead of the former fire-and-forget POST.
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.clients.outbox_notifier import OutboxNotifier, _dedup_key


class _FakeConn:
    def __init__(self, sink):
        self._sink = sink

    async def fetchval(self, _query, *args):
        # outbox.emit binds (aggregate_id, event_type, payload_json, aggregate_type)
        self._sink["aggregate_id"] = args[0]
        self._sink["event_type"] = args[1]
        self._sink["payload"] = json.loads(args[2])
        self._sink["aggregate_type"] = args[3]
        return uuid4()

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Tx()


class _FakePool:
    def __init__(self, sink):
        self._sink = sink

    def acquire(self):
        conn = _FakeConn(self._sink)

        class _Acq:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acq()


def test_dedup_key_from_run_and_status():
    assert _dedup_key({"run_id": "r1", "status": "report_ready"}) == "authoring:r1:report_ready"
    # A different terminal status is a distinct notification, not a dupe.
    assert _dedup_key({"run_id": "r1", "status": "paused"}) == "authoring:r1:paused"
    # Missing pieces ⇒ no key (relay still delivers, just non-idempotent).
    assert _dedup_key({"run_id": "r1"}) is None
    assert _dedup_key(None) is None


@pytest.mark.asyncio
async def test_emits_notification_typed_outbox_row_with_body():
    sink: dict = {}
    run_id = uuid4()
    user_id = uuid4()
    await OutboxNotifier(pool=_FakePool(sink)).notify(
        user_id,
        title="Autonomous authoring run complete — 2 chapter(s) drafted",
        metadata={"operation": "autonomous_authoring", "run_id": str(run_id), "status": "report_ready"},
        category="system",
    )
    # Routed as a notification (the relay delivers these to notification-service).
    assert sink["aggregate_type"] == "notification"
    assert sink["event_type"] == "notification.requested"
    assert sink["aggregate_id"] == run_id  # anchored to the run
    body = sink["payload"]
    assert body["user_id"] == str(user_id)
    assert body["category"] == "system"
    assert "Autonomous authoring run complete" in body["title"]
    assert body["dedup_key"] == f"authoring:{run_id}:report_ready"
    assert body["metadata"]["operation"] == "autonomous_authoring"


@pytest.mark.asyncio
async def test_notify_swallows_errors_best_effort():
    class _BoomPool:
        def acquire(self):
            raise RuntimeError("db down")

    # Must not raise — a notify blip never affects a run.
    await OutboxNotifier(pool=_BoomPool()).notify(uuid4(), title="t", metadata={})
