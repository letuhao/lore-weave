"""Q4b — online LLM-judge engine + persistence (mock judge, no real LLM)."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from loreweave_eval.llm_judge import (
    ItemVerdict,
    parse_precision_batch,
    plan_precision_tasks,
)

from app.db.eval_repo import SCORE_CONFIG_SEED, ScoreValidationError
from app.db.online_judge import (
    aggregate_precision_dicts,
    persist_online_judge,
    run_online_judge,
)


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


# ── M1 byte-identical-score invariant: decoupled fold == inline run_online_judge ──
# The DRY-seam refactor (LLM re-arch Phase 3 M1) claims the decoupled judge's fold
# (plan_precision_tasks + parse_precision_batch + aggregate_precision_dicts) scores
# IDENTICALLY to the inline run_online_judge for the same LLM output. This drives both
# paths off the SAME per-batch contents and asserts the judge_result agrees (/review-impl).

_PATTERN = ["supported", "unsupported", "partial"]


def _content_for(task):
    """A deterministic 'LLM output' for one precision batch (varied verdicts)."""
    verdicts = [
        {"idx": i, "verdict": _PATTERN[(task.global_start + i) % 3], "reason": "r"}
        for i in range(task.n_items)
    ]
    return json.dumps({"verdicts": verdicts})


class _SeqClient:
    """A JudgeLLMClient whose submit_and_wait replays prebuilt contents in call order
    (run_online_judge calls _call_judge per batch in category→batch order, matching
    plan_precision_tasks)."""

    def __init__(self, contents):
        self._q = list(contents)
        self.calls = 0

    async def submit_and_wait(self, **kw):
        self.calls += 1
        return SimpleNamespace(
            status="completed", result={"messages": [{"content": self._q.pop(0)}]},
        )


async def test_decoupled_fold_scores_identically_to_inline():
    items = {"entity": [{}, {}, {}, {}], "relation": [{}, {}], "event": [{}]}
    src = "Alice fell down the hole."
    tasks = plan_precision_tasks(source_text=src, items_by_category=items)
    contents = [_content_for(t) for t in tasks]

    # decoupled fold (the durable-judge path, no LLM client — pure seams)
    accum: dict = {}
    for t, c in zip(tasks, contents):
        for v in parse_precision_batch(c, global_start=t.global_start, n_items=t.n_items):
            accum.setdefault(t.category, []).append(
                {"idx": v.idx, "verdict": v.verdict, "reason": v.reason}
            )
    decoupled = aggregate_precision_dicts(accum)

    # inline run_online_judge fed the SAME contents in plan order
    inline = await run_online_judge(
        _SeqClient(contents), source_text=src, items_by_category=items,
        judge_model="jm", model_source="user_model", user_id="u",
    )

    assert decoupled["overall_precision"] == inline["overall_precision"]
    assert decoupled["n_judged"] == inline["n_judged"]
    for cat in ("entity", "relation", "event"):
        assert decoupled["per_category"][cat]["precision"] == inline["per_category"][cat]["precision"]
        assert decoupled["per_category"][cat]["n_judged"] == inline["per_category"][cat]["n_judged"]
        assert decoupled["per_category"][cat]["verdicts"] == inline["per_category"][cat]["verdicts"]


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
