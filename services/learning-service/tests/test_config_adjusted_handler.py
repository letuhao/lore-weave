"""B2-B-b1 — handle_config_adjusted: persist mapping, dedup, loud-fail."""

import uuid

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import handle_config_adjusted

# Positional param indices for the INSERT in handle_config_adjusted.
P_USER_ID = 0
P_PROJECT_ID = 1
P_TARGET = 5
P_OP = 6
P_BEFORE_STRUCTURAL = 7
P_AFTER_STRUCTURAL = 8
P_BEFORE_CONTENT_HASH = 9
P_ORIGIN_SERVICE = 11
P_ORIGIN_EVENT_ID = 12


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *params):
        self.calls.append(params)


def _adj_event(*, outbox_id="outbox-adj-1", **payload_over):
    payload = {
        "user_id": str(uuid.uuid4()),
        "project_id": str(uuid.uuid4()),
        "actor_type": "user",
        "actor_id": str(uuid.uuid4()),
        "target": "precision_filter",
        "op": "set",
        "before_structural": None,
        "after_structural": {"categories": ["relation"]},
        "emitted_at": "2026-05-31T00:00:00Z",
    }
    payload.update(payload_over)
    return EventData(
        stream="loreweave:events:knowledge",
        message_id="1-0",
        event_type="knowledge.config_adjusted",
        aggregate_id=payload["project_id"],
        payload=payload,
        source="knowledge",
        raw={},
        outbox_id=outbox_id,
    )


async def test_config_adjusted_persisted_with_mapping():
    pool = FakePool()
    await handle_config_adjusted(_adj_event(), pool=pool)
    assert len(pool.calls) == 1
    p = pool.calls[0]
    assert p[P_TARGET] == "precision_filter"
    assert p[P_OP] == "set"
    # before_structural is None; after_structural is JSON-encoded
    assert p[P_BEFORE_STRUCTURAL] is None
    assert '"categories"' in p[P_AFTER_STRUCTURAL]
    # b1 carries no content-hash (raw-prompt targets are b2)
    assert p[P_BEFORE_CONTENT_HASH] is None
    assert p[P_ORIGIN_SERVICE] == "knowledge"
    assert p[P_ORIGIN_EVENT_ID] == "outbox-adj-1"


async def test_empty_outbox_id_raises_for_dlq():
    pool = FakePool()
    with pytest.raises(ValueError, match="empty outbox_id"):
        await handle_config_adjusted(_adj_event(outbox_id=""), pool=pool)
    assert pool.calls == []


@pytest.mark.parametrize("missing", ["user_id", "target"])
async def test_missing_required_field_raises(missing):
    pool = FakePool()
    ev = _adj_event()
    ev.payload[missing] = None
    with pytest.raises(ValueError, match="missing user_id/target"):
        await handle_config_adjusted(ev, pool=pool)
    assert pool.calls == []
