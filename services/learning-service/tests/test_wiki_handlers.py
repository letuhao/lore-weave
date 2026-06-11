"""D-WIKI-M8-LEARNING-CONSUMER — wiki.corrected + wiki.suggestion_reviewed handlers.

wiki.corrected → a `wiki_article` correction (structural AI→human pointer; the gold
prose stays in glossary wiki_revisions). wiki.suggestion_reviewed → a `source='human'`
quality_score (accept=1/reject=0), only on AI-generated articles. Both are gated by
`wiki_learning_enabled` (collect-by-default) and DLQ on a missing dedup key / owner.
Mock-based, mirrors test_generation_corrected_handler + test_translation_quality_handler.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.config import settings
from app.db.eval_repo import SCORE_CONFIG_SEED
from app.events.dispatcher import EventData
from app.events.handlers import handle_wiki_corrected, handle_wiki_suggestion_reviewed


# ── wiki.corrected → corrections (FakePool.execute) ───────────────────────────

# _persist_correction INSERT positional params (see test_generation_corrected_handler).
P_USER_ID, P_BOOK_ID, P_TARGET_TYPE, P_TARGET_ID, P_OP = 0, 2, 3, 4, 5
P_BEFORE_STRUCTURAL, P_AFTER_STRUCTURAL = 6, 7
P_DIFF_CLASS, P_ACTOR_TYPE, P_ORIGIN_SERVICE, P_ORIGIN_EVENT_ID = 12, 16, 18, 19


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *params):
        self.calls.append(params)


def _corrected_event(*, outbox_id="wc-1", user_id=None, article_id=None,
                     book_id=None, prior="needs_review"):
    art = article_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:glossary",
        message_id="1-0",
        event_type="wiki.corrected",
        aggregate_id=art,
        payload={
            "book_id": book_id or str(uuid.uuid4()),
            "article_id": art,
            "entity_id": str(uuid.uuid4()),
            "user_id": user_id if user_id is not None else str(uuid.uuid4()),
            "prior_generation_status": prior,
            "emitted_at": "2026-06-11T00:00:00Z",
        },
        source="glossary",
        raw={},
        outbox_id=outbox_id,
    )


async def test_wiki_corrected_persists_wiki_article_correction():
    pool = FakePool()
    owner, art = str(uuid.uuid4()), str(uuid.uuid4())
    await handle_wiki_corrected(
        _corrected_event(outbox_id="wc-x", user_id=owner, article_id=art, prior="needs_review"),
        pool=pool,
    )
    assert len(pool.calls) == 1
    p = pool.calls[0]
    assert p[P_TARGET_TYPE] == "wiki_article"
    assert p[P_TARGET_ID] == art
    assert p[P_OP] == "human_edit"
    assert p[P_ACTOR_TYPE] == "user"
    assert p[P_ORIGIN_SERVICE] == "glossary"
    assert p[P_ORIGIN_EVENT_ID] == "wc-x"  # = outbox_id (dedup), not aggregate_id
    assert str(p[P_USER_ID]) == owner
    # a non-None `after` → a generic edit, NOT a spurious-drop misclassification
    assert p[P_DIFF_CLASS] == "other"
    before = json.loads(p[P_BEFORE_STRUCTURAL])
    after = json.loads(p[P_AFTER_STRUCTURAL])
    assert before == {"author_type": "ai", "generation_status": "needs_review"}
    assert after == {"author_type": "human"}


async def test_wiki_corrected_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "wiki_learning_enabled", False)
    pool = FakePool()
    await handle_wiki_corrected(_corrected_event(), pool=pool)
    assert pool.calls == []  # collect toggled off → ack, no row


async def test_wiki_corrected_empty_outbox_id_raises():
    pool = FakePool()
    with pytest.raises(ValueError):
        await handle_wiki_corrected(_corrected_event(outbox_id=""), pool=pool)
    assert pool.calls == []


async def test_wiki_corrected_missing_user_raises():
    pool = FakePool()
    with pytest.raises(ValueError):
        await handle_wiki_corrected(_corrected_event(user_id=""), pool=pool)
    assert pool.calls == []


# ── wiki.suggestion_reviewed → quality_scores (FakeConn/FakePool.acquire) ──────

PS_KIND, PS_TARGET, PS_METRIC, PS_VALUE_NUM, PS_SOURCE, PS_COMMENT, PS_ORIGIN_SVC, PS_ORIGIN_ID = (
    0, 1, 4, 5, 8, 10, 11, 12
)


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


class ScorePool:
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


def _reviewed_event(*, outbox_id="sr-1", user_id=None, article_id=None,
                    action="accept", was_ai=True):
    art = article_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:glossary",
        message_id="1-0",
        event_type="wiki.suggestion_reviewed",
        aggregate_id=art,
        payload={
            "book_id": str(uuid.uuid4()),
            "article_id": art,
            "suggestion_id": str(uuid.uuid4()),
            "user_id": user_id if user_id is not None else str(uuid.uuid4()),
            "action": action,
            "was_ai_generated": was_ai,
            "emitted_at": "2026-06-11T00:00:00Z",
        },
        source="glossary",
        raw={},
        outbox_id=outbox_id,
    )


async def test_suggestion_accept_scores_one():
    conn = FakeConn()
    art = str(uuid.uuid4())
    await handle_wiki_suggestion_reviewed(
        _reviewed_event(outbox_id="sr-a", article_id=art, action="accept"), pool=ScorePool(conn))
    ins = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(ins) == 1
    p = ins[0][1]
    assert p[PS_KIND] == "wiki_article"
    assert p[PS_TARGET] == art
    assert p[PS_METRIC] == "wiki_suggestion_reviewed"
    assert p[PS_VALUE_NUM] == 1.0
    assert p[PS_SOURCE] == "human"
    assert p[PS_ORIGIN_SVC] == "glossary"
    assert p[PS_ORIGIN_ID] == "sr-a"
    assert json.loads(p[PS_COMMENT])["action"] == "accept"


async def test_suggestion_reject_scores_zero():
    conn = FakeConn()
    await handle_wiki_suggestion_reviewed(_reviewed_event(action="reject"), pool=ScorePool(conn))
    p = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]][0][1]
    assert p[PS_VALUE_NUM] == 0.0


async def test_suggestion_on_non_ai_article_skipped():
    conn = FakeConn()
    await handle_wiki_suggestion_reviewed(_reviewed_event(was_ai=False), pool=ScorePool(conn))
    assert conn.execs == []  # only AI-article reviews are an AI-quality signal


async def test_suggestion_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "wiki_learning_enabled", False)
    conn = FakeConn()
    await handle_wiki_suggestion_reviewed(_reviewed_event(), pool=ScorePool(conn))
    assert conn.execs == []


async def test_suggestion_empty_outbox_id_raises():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_wiki_suggestion_reviewed(_reviewed_event(outbox_id=""), pool=ScorePool(conn))
    assert conn.execs == []


async def test_suggestion_bad_action_raises():
    conn = FakeConn()
    with pytest.raises(ValueError):
        await handle_wiki_suggestion_reviewed(_reviewed_event(action="maybe"), pool=ScorePool(conn))
    assert conn.execs == []


def test_wiki_handlers_registered():
    from app.main import build_dispatcher
    d = build_dispatcher()
    assert "wiki.corrected" in d.registered_types
    assert "wiki.suggestion_reviewed" in d.registered_types
