"""M7b — translation.reviewed handler (human accept signal).

Mock-based (mirrors test_translation_quality_handler): a FakeConn returns the
seeded score_config and captures the INSERT, so we assert the human-accept
mapping, source=human, ack-detail-in-comment, validation, and loud-fail → DLQ.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.eval_repo import SCORE_CONFIG_SEED
from app.events.dispatcher import EventData
from app.events.handlers import handle_translation_reviewed


def _cfg_rows():
    return [
        {"name": s["name"], "data_type": s["data_type"],
         "min_value": s.get("min_value"), "max_value": s.get("max_value"), "categories": None}
        for s in SCORE_CONFIG_SEED
    ]


class FakeConn:
    def __init__(self):
        self._cfg = _cfg_rows()
        self.execs: list = []

    async def fetch(self, sql, *params):
        return self._cfg if "FROM score_config" in sql else []

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


def _reviewed_event(*, outbox_id="tr-1", user_id=None, ct_id=None,
                    acknowledged=False, unresolved=0, lang="vi"):
    ct = ct_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:translation",
        message_id="1-0",
        event_type="translation.reviewed",
        aggregate_id=ct,
        payload={
            "user_id": user_id if user_id is not None else str(uuid.uuid4()),
            "book_id": str(uuid.uuid4()),
            "chapter_id": str(uuid.uuid4()),
            "chapter_translation_id": ct,
            "target_language": lang,
            "acknowledged_issues": acknowledged,
            "unresolved_high_count": unresolved,
        },
        source="translation",
        raw={},
        outbox_id=outbox_id,
    )


# INSERT param order: target_kind, target_id, user_id, book_id, metric_name, value_num,
# value_label, data_type, source, judge_model, comment, origin_service, origin_event_id
P_KIND, P_TARGET, P_METRIC, P_VALUE, P_SOURCE, P_COMMENT, P_ORIGIN_SVC, P_ORIGIN_ID = 0, 1, 4, 5, 8, 10, 11, 12


async def test_set_active_persists_human_accept():
    conn = FakeConn()
    ct = str(uuid.uuid4())
    await handle_translation_reviewed(_reviewed_event(ct_id=ct, outbox_id="tr-1"), pool=FakePool(conn))
    ins = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(ins) == 1
    p = ins[0][1]
    assert p[P_KIND] == "translation"
    assert p[P_TARGET] == ct
    assert p[P_METRIC] == "translation_human_accept"
    assert p[P_VALUE] == 1.0
    assert p[P_SOURCE] == "human"
    assert p[P_ORIGIN_SVC] == "translation"
    assert p[P_ORIGIN_ID] == "tr-1"


async def test_acknowledge_issues_captured_in_comment():
    """The verifier-calibration case: human published DESPITE flags → rides in comment."""
    conn = FakeConn()
    await handle_translation_reviewed(
        _reviewed_event(acknowledged=True, unresolved=3), pool=FakePool(conn))
    p = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]][0][1]
    detail = json.loads(p[P_COMMENT])
    assert detail["acknowledged_issues"] is True
    assert detail["unresolved_high_count"] == 3
    assert detail["target_language"] == "vi"


async def test_empty_outbox_id_raises_no_write():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_translation_reviewed(_reviewed_event(outbox_id=""), pool=FakePool(conn))
    assert conn.execs == []


async def test_missing_user_raises():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_translation_reviewed(_reviewed_event(user_id=""), pool=FakePool(conn))
