"""A-EVAL — pairwise judge + internal endpoint tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.engine import eval_judge

# asyncio auto-mode (pytest.ini) collects the async pairwise_judge tests; the sync
# parse + TestClient endpoint tests must NOT carry the asyncio mark.


class FakeLLM:
    def __init__(self, content=None, status="completed", raises=False):
        self._content, self._status, self._raises = content, status, raises
        self.calls = 0

    async def submit_and_wait(self, **kw):
        from loreweave_llm.errors import LLMError
        self.calls += 1
        if self._raises:
            raise LLMError("gateway down")
        res = {"messages": [{"content": self._content}]} if self._content is not None else {}
        return SimpleNamespace(status=self._status, result=res)


# ── parse / coerce ──

def test_parse_verdict_full():
    v = eval_judge._parse_verdict(json.dumps({
        "better": "2", "why": "tighter",
        "defects_1": {"continuity_breaks": 2, "dropped_threads": 1, "contradictions": 0, "repetition": 3},
        "defects_2": {"continuity_breaks": 0, "dropped_threads": 0, "contradictions": 0, "repetition": 1},
    }))
    assert v["better"] == "2" and v["why"] == "tighter"
    assert v["defects_1"]["repetition"] == 3 and v["defects_2"]["continuity_breaks"] == 0


def test_parse_verdict_missing_better_defaults_tie():
    v = eval_judge._parse_verdict(json.dumps({"why": "unclear"}))
    assert v["better"] == "tie"  # never crown a winner on a garbled verdict
    assert v["defects_1"] == {"continuity_breaks": 0, "dropped_threads": 0,
                              "contradictions": 0, "repetition": 0}


def test_parse_verdict_garbage_and_bad_defect_types():
    v = eval_judge._parse_verdict("not json at all")
    assert v["better"] == "tie"
    # bool/negative/str defect values are rejected → 0
    v2 = eval_judge._parse_verdict(json.dumps({
        "better": "1", "defects_1": {"continuity_breaks": True, "repetition": -4, "contradictions": "x"}}))
    assert v2["defects_1"] == {"continuity_breaks": 0, "dropped_threads": 0,
                               "contradictions": 0, "repetition": 0}


# ── pairwise_judge ──

async def test_pairwise_judge_happy():
    llm = FakeLLM(content=json.dumps({"better": "1", "why": "ok",
                                      "defects_1": {"repetition": 1},
                                      "defects_2": {"contradictions": 2}}))
    v = await eval_judge.pairwise_judge(llm, user_id="u", model_source="user_model",
                                        model_ref="critic", draft_a="A", draft_b="B")
    assert v["better"] == "1" and v["defects_2"]["contradictions"] == 2
    assert "error" not in v


async def test_pairwise_judge_llm_error_returns_tie_not_raise():
    llm = FakeLLM(raises=True)
    v = await eval_judge.pairwise_judge(llm, user_id="u", model_source="user_model",
                                        model_ref="critic", draft_a="A", draft_b="B")
    assert v["better"] == "tie" and v["error"] == "judge_unavailable"


async def test_pairwise_judge_non_completed_returns_tie():
    llm = FakeLLM(content="{}", status="failed")
    v = await eval_judge.pairwise_judge(llm, user_id="u", model_source="user_model",
                                        model_ref="critic", draft_a="A", draft_b="B")
    assert v["better"] == "tie" and v["error"] == "judge_failed"


# ── internal endpoint ──

def _client(monkeypatch, llm):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_llm_client_dep
    app.dependency_overrides[get_llm_client_dep] = lambda: llm
    return app


def test_pairwise_endpoint_requires_internal_token(monkeypatch):
    app = _client(monkeypatch, FakeLLM(content="{}"))
    body = {"user_id": str(uuid.uuid4()), "model_source": "user_model",
            "model_ref": "critic", "draft_a": "A", "draft_b": "B"}
    with TestClient(app) as c:
        # no token → 401/403
        r = c.post("/internal/composition/eval/pairwise-judge", json=body)
        assert r.status_code in (401, 403)
    app.dependency_overrides.clear()


def test_pairwise_endpoint_happy(monkeypatch):
    llm = FakeLLM(content=json.dumps({"better": "2", "why": "x", "defects_1": {}, "defects_2": {}}))
    app = _client(monkeypatch, llm)
    body = {"user_id": str(uuid.uuid4()), "model_source": "user_model",
            "model_ref": "critic", "draft_a": "A", "draft_b": "B"}
    with TestClient(app) as c:
        r = c.post("/internal/composition/eval/pairwise-judge", json=body,
                   headers={"X-Internal-Token": "test_token"})  # Dockerfile test-stage token
        assert r.status_code == 200 and r.json()["better"] == "2"
    app.dependency_overrides.clear()
