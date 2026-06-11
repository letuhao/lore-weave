"""D-WIKI-M8-EVAL-PLUS — the on-demand wiki groundedness judge endpoint + persist.

The endpoint is internal-token gated and INERT unless a judge model is configured or
supplied (the human audit opt-in). Judging + persistence are mocked at their module
boundaries (the endpoint imports them lazily). A separate test pins the persisted
quality_scores row shape (metric + run-scoped dedup key).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreweave_eval.llm_judge import GroundednessVerdict

from app.config import settings
from app.deps import get_db
from app.routers import wiki_judge

TOK = settings.internal_service_token  # whatever the test env configured


def _app(mocker, *, verdicts):
    app = FastAPI()
    app.include_router(wiki_judge.router)
    app.dependency_overrides[get_db] = lambda: object()
    mocker.patch("app.clients.llm_client.build_judge_client", return_value=object())
    persist = mocker.patch(
        "app.db.online_wiki_judge.persist_wiki_judge", new_callable=AsyncMock, return_value=True)
    rj = mocker.patch(
        "app.db.online_wiki_judge.run_wiki_judge", new_callable=AsyncMock, side_effect=verdicts)
    return app, persist, rj


def _article(**over):
    a = {
        "article_id": str(uuid.uuid4()), "book_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()), "article_text": "Mina is a teacher.",
        "sources": ["Mina taught school."],
    }
    a.update(over)
    return a


def test_requires_internal_token(mocker):
    app, _, _ = _app(mocker, verdicts=[])
    r = TestClient(app).post("/internal/learning/wiki/judge", json={"articles": []})
    assert r.status_code == 401


def test_inert_when_no_model_and_flag_off(mocker):
    app, persist, rj = _app(mocker, verdicts=[])
    r = TestClient(app).post(
        "/internal/learning/wiki/judge", json={"articles": [_article()]},
        headers={"X-Internal-Token": TOK})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False and body["scored"] == 0
    rj.assert_not_called()
    persist.assert_not_called()


def test_request_model_opts_in_and_persists(mocker):
    app, persist, rj = _app(mocker, verdicts=[GroundednessVerdict(score=0.8, reason="ok")])
    r = TestClient(app).post(
        "/internal/learning/wiki/judge",
        json={"judge_model": "model-x", "articles": [_article()]},
        headers={"X-Internal-Token": TOK})
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["scored"] == 1
    assert body["scores"][0]["score"] == 0.8
    rj.assert_awaited_once()
    persist.assert_awaited_once()


def test_global_flag_uses_configured_model(mocker):
    # flag ON + a configured model, NO request model → judges with the configured model.
    mocker.patch.object(settings, "wiki_llm_judge_enabled", True)
    mocker.patch.object(settings, "wiki_llm_judge_model_ref", "cfg-model")
    app, persist, rj = _app(mocker, verdicts=[GroundednessVerdict(score=0.7, reason="ok")])
    r = TestClient(app).post(
        "/internal/learning/wiki/judge", json={"articles": [_article()]},
        headers={"X-Internal-Token": TOK})
    body = r.json()
    assert body["enabled"] is True and body["scored"] == 1
    rj.assert_awaited_once()
    assert rj.await_args.kwargs["judge_model"] == "cfg-model"


def test_verdict_none_is_skipped(mocker):
    app, persist, _ = _app(mocker, verdicts=[None])
    r = TestClient(app).post(
        "/internal/learning/wiki/judge",
        json={"judge_model": "model-x", "articles": [_article()]},
        headers={"X-Internal-Token": TOK})
    body = r.json()
    assert body["enabled"] is True and body["scored"] == 0
    persist.assert_not_called()


def test_article_without_owner_skipped_before_judge(mocker):
    app, persist, rj = _app(mocker, verdicts=[GroundednessVerdict(score=0.9, reason="ok")])
    r = TestClient(app).post(
        "/internal/learning/wiki/judge",
        json={"judge_model": "model-x", "articles": [_article(user_id=None)]},
        headers={"X-Internal-Token": TOK})
    body = r.json()
    assert body["scored"] == 0
    rj.assert_not_called()  # no owner to bill/attribute → skip before spending a judge call


# ── persist row shape (FakeConn) ──────────────────────────────────────────────

from app.db.eval_repo import SCORE_CONFIG_SEED  # noqa: E402

PS_KIND, PS_TARGET, PS_METRIC, PS_VALUE_NUM, PS_SOURCE, PS_ORIGIN_SVC, PS_ORIGIN_ID = (
    0, 1, 4, 5, 8, 11, 12
)


class _FakeConn:
    def __init__(self):
        self._cfg = [
            {"name": s["name"], "data_type": s["data_type"],
             "min_value": s.get("min_value"), "max_value": s.get("max_value"), "categories": None}
            for s in SCORE_CONFIG_SEED
        ]
        self.execs: list = []

    async def fetch(self, sql, *params):
        return self._cfg if "FROM score_config" in sql else []

    async def execute(self, sql, *params):
        self.execs.append((sql, params))
        return "INSERT 0 1"


class _ScorePool:
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


async def test_persist_wiki_judge_row_shape():
    from app.db.online_wiki_judge import persist_wiki_judge

    conn = _FakeConn()
    art = str(uuid.uuid4())
    await persist_wiki_judge(
        _ScorePool(conn),
        article_id=art,
        user_id=uuid.uuid4(),
        book_id=uuid.uuid4(),
        verdict=GroundednessVerdict(score=0.73, reason="mostly grounded"),
        judge_model="model-x",
        run_id="run42",
    )
    ins = [e for e in conn.execs if "INSERT INTO quality_scores" in e[0]]
    assert len(ins) == 1
    p = ins[0][1]
    assert p[PS_KIND] == "wiki_article"
    assert p[PS_TARGET] == art
    assert p[PS_METRIC] == "wiki_llm_judge_groundedness"
    assert p[PS_VALUE_NUM] == 0.73
    assert p[PS_SOURCE] == "auto"
    assert p[PS_ORIGIN_SVC] == "wiki-judge"
    assert p[PS_ORIGIN_ID] == f"run42:{art}"  # run-scoped dedup
