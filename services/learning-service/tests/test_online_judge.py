"""Q4b — online LLM-judge engine + persistence (mock judge, no real LLM)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from loreweave_eval.llm_judge import ItemVerdict

from app.db.eval_repo import SCORE_CONFIG_SEED, ScoreValidationError
from app.db.online_judge import persist_online_judge, run_online_judge


def _vd(idx, verdict):
    return ItemVerdict(idx=idx, verdict=verdict, reason="")


# ── run_online_judge ──────────────────────────────────────────────────


async def test_precision_credit_and_overall(monkeypatch):
    async def fake_judge(client, *, category, extracted, **kw):
        return {
            "entity": [_vd(0, "supported"), _vd(1, "supported"), _vd(2, "unsupported")],
            "relation": [_vd(0, "partial")],
        }[category]

    monkeypatch.setattr("app.db.online_judge.judge_precision", fake_judge)
    res = await run_online_judge(
        AsyncMock(),
        source_text="src",
        items_by_category={"entity": [{}, {}, {}], "relation": [{}]},
        judge_model="jm",
        model_source="user_model",
        user_id="u",
    )
    assert res["per_category"]["entity"]["precision"] == pytest.approx(2 / 3)
    assert res["per_category"]["relation"]["precision"] == 0.5
    # overall = (1 + 1 + 0 + 0.5) / 4 judged
    assert res["overall_precision"] == pytest.approx(0.625)
    assert res["n_judged"] == 4


async def test_skips_empty_categories(monkeypatch):
    called = []

    async def fake_judge(client, *, category, extracted, **kw):
        called.append(category)
        return [_vd(0, "supported")]

    monkeypatch.setattr("app.db.online_judge.judge_precision", fake_judge)
    res = await run_online_judge(
        AsyncMock(), source_text="s", items_by_category={"entity": [{}]},
        judge_model="jm", model_source="user_model", user_id="u",
    )
    assert called == ["entity"]
    assert res["overall_precision"] == 1.0


async def test_unjudged_excluded_from_denominator(monkeypatch):
    async def fake_judge(client, *, category, extracted, **kw):
        return [_vd(0, "supported"), _vd(1, "unjudged")]

    monkeypatch.setattr("app.db.online_judge.judge_precision", fake_judge)
    res = await run_online_judge(
        AsyncMock(), source_text="s", items_by_category={"entity": [{}, {}]},
        judge_model="jm", model_source="user_model", user_id="u",
    )
    assert res["per_category"]["entity"]["n_judged"] == 1  # unjudged dropped
    assert res["overall_precision"] == 1.0


# ── persist_online_judge (mock conn) ──────────────────────────────────


def _cfg_rows():
    return [
        {"name": s["name"], "data_type": s["data_type"], "min_value": s.get("min_value"),
         "max_value": s.get("max_value"), "categories": None}
        for s in SCORE_CONFIG_SEED
    ]


class FakeConn:
    def __init__(self, eval_run_id):
        self._eval_run_id = eval_run_id
        self._cfg = _cfg_rows()
        self.execs: list = []

    def transaction(self):
        class _T:
            async def __aenter__(s):
                return None

            async def __aexit__(s, *a):
                return False

        return _T()

    async def fetch(self, sql, *params):
        return self._cfg if "FROM score_config" in sql else []

    async def fetchrow(self, sql, *params):
        return {"eval_run_id": self._eval_run_id}

    async def execute(self, sql, *params):
        self.execs.append((sql, params))
        return "OK"


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _A:
            async def __aenter__(s):
                return conn

            async def __aexit__(s, *a):
                return False

        return _A()


def _count(execs, needle):
    return sum(1 for sql, _ in execs if needle in sql)


async def test_persist_writes_run_results_and_score():
    rid, erid = uuid.uuid4(), uuid.uuid4()
    conn = FakeConn(erid)
    result = {
        "per_category": {
            "entity": {"precision": 0.8, "n_judged": 5, "verdicts": [{"idx": 0, "verdict": "supported"}]},
            "relation": {"precision": 0.5, "n_judged": 2, "verdicts": []},
        },
        "overall_precision": 0.7,
        "n_judged": 7,
    }
    out = await persist_online_judge(
        FakePool(conn), run_id=str(rid), user_id=uuid.uuid4(), judge_model="jm", judge_result=result
    )
    assert out == erid
    assert _count(conn.execs, "INSERT INTO eval_results") == 2   # per category
    assert _count(conn.execs, "INSERT INTO quality_scores") == 1
    assert _count(conn.execs, "DELETE FROM eval_results") == 1


async def test_persist_none_when_nothing_judged():
    conn = FakeConn(uuid.uuid4())
    out = await persist_online_judge(
        FakePool(conn), run_id=str(uuid.uuid4()), user_id=uuid.uuid4(),
        judge_model="jm", judge_result={"per_category": {}, "overall_precision": None, "n_judged": 0},
    )
    assert out is None
    assert conn.execs == []  # nothing written


async def test_persist_validates_precision_range():
    conn = FakeConn(uuid.uuid4())
    with pytest.raises(ScoreValidationError):
        await persist_online_judge(
            FakePool(conn), run_id=str(uuid.uuid4()), user_id=uuid.uuid4(), judge_model="jm",
            judge_result={"per_category": {}, "overall_precision": 1.5, "n_judged": 1},
        )
    assert conn.execs == []
