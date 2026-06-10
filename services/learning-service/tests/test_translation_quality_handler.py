"""M7a — translation.quality handler + persist_consumed_score.

Mock-based (mirrors test_chat_feedback_handler): a FakeConn returns the seeded
score_config and captures the INSERT, so we assert the payload->quality_score
mapping, source=auto, the detail-in-comment, write-time validation, and loud-fail
(empty outbox_id / missing user / non-numeric score -> DLQ).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.db.eval_repo import SCORE_CONFIG_SEED, ScoreValidationError
from app.events.dispatcher import EventData
from app.events.handlers import handle_translation_quality


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


def _quality_event(*, outbox_id="tq-1", user_id=None, ct_id=None, score=0.92,
                   unresolved_high=1, qa_rounds=2, issues=None, lang="vi", pv="v3"):
    ct = ct_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:translation",
        message_id="1-0",
        event_type="translation.quality",
        aggregate_id=ct,
        payload={
            "user_id": user_id if user_id is not None else str(uuid.uuid4()),
            "book_id": str(uuid.uuid4()),
            "chapter_id": str(uuid.uuid4()),
            "chapter_translation_id": ct,
            "target_language": lang,
            "pipeline_version": pv,
            "quality_score": score,
            "unresolved_high_count": unresolved_high,
            "qa_rounds_used": qa_rounds,
            "issue_counts": issues if issues is not None else {"wrong_name": 1, "omission": 2},
        },
        source="translation",
        raw={},
        outbox_id=outbox_id,
    )


# quality_scores INSERT param order:
# target_kind, target_id, user_id, book_id, metric_name, value_num,
# value_label, data_type, source, judge_model, comment, origin_service, origin_event_id
P_KIND, P_TARGET, P_METRIC, P_VALUE_NUM, P_SOURCE, P_COMMENT, P_ORIGIN_SVC, P_ORIGIN_ID = 0, 1, 4, 5, 8, 10, 11, 12


async def test_translation_quality_persists_auto_score():
    conn = FakeConn()
    ct = str(uuid.uuid4())
    await handle_translation_quality(_quality_event(ct_id=ct, score=0.92, outbox_id="tq-1"), pool=FakePool(conn))
    inserts = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(inserts) == 1
    p = inserts[0][1]
    assert p[P_KIND] == "translation"
    assert p[P_TARGET] == ct
    assert p[P_METRIC] == "translation_quality_score"
    assert p[P_VALUE_NUM] == 0.92
    assert p[P_SOURCE] == "auto"          # LLM-action log, not human
    assert p[P_ORIGIN_SVC] == "translation"
    assert p[P_ORIGIN_ID] == "tq-1"       # = relay outbox_id (dedup key)


async def test_breakdown_stashed_in_comment():
    """The single persisted metric is the score; the rest rides in `comment`."""
    conn = FakeConn()
    await handle_translation_quality(
        _quality_event(unresolved_high=3, qa_rounds=2, issues={"omission": 4}), pool=FakePool(conn))
    p = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]][0][1]
    detail = json.loads(p[P_COMMENT])
    assert detail["unresolved_high_count"] == 3
    assert detail["qa_rounds_used"] == 2
    assert detail["issue_counts"] == {"omission": 4}
    assert detail["target_language"] == "vi"
    assert detail["pipeline_version"] == "v3"


async def test_empty_outbox_id_raises_no_write():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_translation_quality(_quality_event(outbox_id=""), pool=FakePool(conn))
    assert conn.execs == []


async def test_missing_user_raises():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_translation_quality(_quality_event(user_id=""), pool=FakePool(conn))


async def test_non_numeric_score_raises():
    conn = FakeConn()
    ev = _quality_event()
    ev.payload["quality_score"] = "good"
    with pytest.raises(ValueError):
        await handle_translation_quality(ev, pool=FakePool(conn))
    assert conn.execs == []


async def test_score_out_of_range_rejected():
    """A score outside score_config [0,1] is rejected before any write."""
    conn = FakeConn()
    with pytest.raises(ScoreValidationError):
        await handle_translation_quality(_quality_event(score=1.5), pool=FakePool(conn))
    assert conn.execs == []


# ── S5b-eval: per-campaign judge model + verdict emit ─────────────────────────

async def test_campaign_eval_judge_uses_event_model_and_emits(mocker):
    """A campaign-chosen eval_judge model on the event runs the judge with THAT
    model (not the service-wide config) even with both global flags OFF, and emits
    translation.eval_judged for the campaign projection."""
    from types import SimpleNamespace

    judge = mocker.patch(
        "app.db.online_translation_judge.run_translation_judge",
        new_callable=AsyncMock, return_value=SimpleNamespace(score=0.83, reason="ok"))
    mocker.patch("app.db.online_translation_judge.persist_translation_judge",
                 new_callable=AsyncMock)
    mocker.patch("app.clients.llm_client.build_judge_client", return_value=object())
    emit = mocker.patch("app.events.handlers._emit_eval_judged", new_callable=AsyncMock)

    CAMPAIGN_MODEL = str(uuid.uuid4())
    ev = _quality_event()
    ev.payload["eval_judge_model_source"] = "user_model"
    ev.payload["eval_judge_model_ref"] = CAMPAIGN_MODEL
    ev.payload["source_text"] = "原文内容"
    ev.payload["translated_text"] = "nội dung"

    await handle_translation_quality(ev, pool=FakePool(FakeConn()))

    judge.assert_awaited_once()
    assert judge.call_args.kwargs["judge_model"] == CAMPAIGN_MODEL  # event model, not global config
    emit.assert_awaited_once()  # verdict surfaced to the campaign projection


async def test_no_campaign_judge_and_flags_off_is_inert(mocker):
    """Without a campaign model and with the global flags off (default), the judge
    never runs (today's behavior preserved)."""
    judge = mocker.patch(
        "app.db.online_translation_judge.run_translation_judge", new_callable=AsyncMock)
    emit = mocker.patch("app.events.handlers._emit_eval_judged", new_callable=AsyncMock)
    ev = _quality_event()
    ev.payload["source_text"] = "原文"
    ev.payload["translated_text"] = "dịch"
    await handle_translation_quality(ev, pool=FakePool(FakeConn()))
    judge.assert_not_awaited()
    emit.assert_not_awaited()
