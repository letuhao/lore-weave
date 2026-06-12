"""M7c-3 — glossary.name_confirmed handler (human name-confirm → source=human).

A user verifying a glossary name (the M6a confirm action) becomes a source='human'
quality_score keyed to the entity, with the source→target pair in the comment.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.db.eval_repo import SCORE_CONFIG_SEED, ScoreValidationError
from app.events.dispatcher import EventData
from app.events.handlers import handle_name_confirmed


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


def _confirm_event(*, outbox_id="nc-1", actor_id=None, entity_id=None,
                   source="提拉米", value="Tirami", lang="vi"):
    ent = entity_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:glossary",
        message_id="1-0",
        event_type="glossary.name_confirmed",
        aggregate_id=ent,
        payload={
            "book_id": str(uuid.uuid4()),
            "glossary_entity_id": ent,
            "source_name": source,
            "kind": "character",
            "language_code": lang,
            "value": value,
            "actor_type": "user",
            "actor_id": actor_id if actor_id is not None else str(uuid.uuid4()),
        },
        source="glossary",
        raw={},
        outbox_id=outbox_id,
    )


# INSERT param order: target_kind, target_id, user_id, book_id, metric_name, value_num,
# value_label, data_type, source, judge_model, comment, origin_service, origin_event_id
P_KIND, P_TARGET, P_METRIC, P_VALUE, P_SOURCE, P_COMMENT, P_ORIGIN_SVC, P_ORIGIN_ID = 0, 1, 4, 5, 8, 10, 11, 12


async def test_name_confirm_persists_human_signal():
    conn = FakeConn()
    ent = str(uuid.uuid4())
    await handle_name_confirmed(_confirm_event(entity_id=ent, outbox_id="nc-1"), pool=FakePool(conn))
    ins = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(ins) == 1
    p = ins[0][1]
    assert p[P_KIND] == "glossary"
    assert p[P_TARGET] == ent
    assert p[P_METRIC] == "glossary_name_confirmed"
    assert p[P_VALUE] == 1.0
    assert p[P_SOURCE] == "human"
    assert p[P_ORIGIN_SVC] == "glossary"
    assert p[P_ORIGIN_ID] == "nc-1"


async def test_source_target_in_comment():
    conn = FakeConn()
    await handle_name_confirmed(_confirm_event(source="暗黑魔殿", value="Hắc Ám Ma Điện"), pool=FakePool(conn))
    detail = json.loads([e for e in conn.execs if "INSERT INTO quality_scores" in e[0]][0][1][P_COMMENT])
    assert detail["source_name"] == "暗黑魔殿"
    assert detail["target_value"] == "Hắc Ám Ma Điện"
    assert detail["language"] == "vi"


async def test_empty_outbox_id_raises_no_write():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_name_confirmed(_confirm_event(outbox_id=""), pool=FakePool(conn))
    assert conn.execs == []


async def test_missing_actor_raises():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_name_confirmed(_confirm_event(actor_id=""), pool=FakePool(conn))
