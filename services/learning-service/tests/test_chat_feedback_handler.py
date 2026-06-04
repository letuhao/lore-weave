"""Q3 — chat.message_feedback handler + persist_consumed_score.

Mock-based: a FakeConn returns the seeded score_config and captures the INSERT,
so we assert the payload->quality_score mapping, write-time validation, and the
loud-fail (empty outbox_id / missing user / non-numeric rating -> DLQ).
"""

from __future__ import annotations

import uuid

import pytest

from app.db.eval_repo import (
    SCORE_CONFIG_SEED,
    ScoreValidationError,
    persist_consumed_score,
)
from app.events.dispatcher import EventData
from app.events.handlers import handle_chat_feedback


def _cfg_rows():
    return [
        {
            "name": s["name"],
            "data_type": s["data_type"],
            "min_value": s.get("min_value"),
            "max_value": s.get("max_value"),
            "categories": None,
        }
        for s in SCORE_CONFIG_SEED
    ]


class FakeConn:
    def __init__(self):
        self._cfg = _cfg_rows()
        self.execs: list = []

    async def fetch(self, sql, *params):
        if "FROM score_config" in sql:
            return self._cfg
        return []

    async def execute(self, sql, *params):
        self.execs.append((sql, params))
        return "INSERT 0 1"


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False

        return _Acq()


def _feedback_event(*, outbox_id="ob-1", user_id=None, message_id=None, rating=1, reason=None, regen=None):
    mid = message_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:chat",
        message_id="1-0",
        event_type="chat.message_feedback",
        aggregate_id=mid,
        payload={
            "user_id": user_id if user_id is not None else str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "message_id": mid,
            "rating": rating,
            "reason": reason,
            "regenerated_from_message_id": regen,
        },
        source="chat",
        raw={},
        outbox_id=outbox_id,
    )


# quality_scores INSERT param order:
# target_kind, target_id, user_id, book_id, metric_name, value_num,
# value_label, data_type, source, judge_model, comment, origin_service, origin_event_id
P_KIND, P_METRIC, P_VALUE_NUM, P_SOURCE, P_ORIGIN_SVC, P_ORIGIN_ID = 0, 4, 5, 8, 11, 12


async def test_chat_feedback_persists_quality_score():
    conn = FakeConn()
    await handle_chat_feedback(_feedback_event(rating=1, outbox_id="ob-1"), pool=FakePool(conn))
    inserts = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(inserts) == 1
    p = inserts[0][1]
    assert p[P_KIND] == "chat_message"
    assert p[P_METRIC] == "chat_user_rating"
    assert p[P_VALUE_NUM] == 1.0
    assert p[P_SOURCE] == "human"
    assert p[P_ORIGIN_SVC] == "chat"
    assert p[P_ORIGIN_ID] == "ob-1"  # = relay outbox_id (dedup key)


async def test_thumb_down_maps_to_negative_one():
    conn = FakeConn()
    await handle_chat_feedback(_feedback_event(rating=-1), pool=FakePool(conn))
    p = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]][0][1]
    assert p[P_VALUE_NUM] == -1.0


async def test_empty_outbox_id_raises_no_write():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_chat_feedback(_feedback_event(outbox_id=""), pool=FakePool(conn))
    assert conn.execs == []


async def test_missing_user_raises():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_chat_feedback(_feedback_event(user_id=""), pool=FakePool(conn))


async def test_non_numeric_rating_raises():
    conn = FakeConn()
    ev = _feedback_event()
    ev.payload["rating"] = "up"
    with pytest.raises(ValueError):
        await handle_chat_feedback(ev, pool=FakePool(conn))
    assert conn.execs == []


async def test_persist_consumed_score_validates_range():
    """A rating outside score_config [-1,1] is rejected before any write."""
    conn = FakeConn()
    with pytest.raises(ScoreValidationError):
        await persist_consumed_score(
            FakePool(conn),
            target_kind="chat_message",
            target_id="m1",
            user_id=uuid.uuid4(),
            metric_name="chat_user_rating",
            value_num=2.0,  # out of [-1, 1]
            source="human",
            origin_service="chat",
            origin_event_id="ob-9",
        )
    assert conn.execs == []


async def test_persist_consumed_score_empty_origin_raises():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await persist_consumed_score(
            FakePool(conn),
            target_kind="chat_message",
            target_id="m1",
            user_id=uuid.uuid4(),
            metric_name="chat_user_rating",
            value_num=1.0,
            source="human",
            origin_service="chat",
            origin_event_id="",
        )
