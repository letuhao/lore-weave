"""LE-PROD-2 P3b — eval-run route (POST /internal/eval/{project}/run) + judge binding.

Drives the FastAPI handler via TestClient. The DB repos + book-profile read are
faked (monkeypatched module globals); ``run_eval`` + the real deterministic scorers
+ the real suite TOML run for real (no judges → fail-closed gate). The judge binding
is unit-tested against a mocked provider-registry."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import eval as eval_api
from app.config import settings
from app.deps import get_db

PROJECT = UUID("019e7850-aa1c-7cd3-a25c-c2f9ad84fd39")
USER = UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
TOKEN = {"X-Internal-Token": settings.internal_service_token}


def _row(**over):
    base = dict(
        proposal_id=uuid4(), canonical_name="蓬萊", target_ref=None,
        entity_kind="location", origin="enrichment", technique="retrieval",
        confidence=0.30, review_status="proposed",
        provenance_json={
            "dimensions": {"历史": "蓬萊乃东海仙山，自上古为群仙修真之所。",
                            "地理": "孤悬东海之上，云雾缭绕。",
                            "文化": "岛上仙家崇尚清修无为。"},
            "technique": "retrieval", "model_ref": "r1",
            "canon_verify": {"flags": []},
        },
        source_refs_json=[{"corpus_id": "c1", "chunk_id": "k1", "score": 0.8}],
    )
    base.update(over)
    return SimpleNamespace(**base)


class _FakeProposalsRepo:
    rows: list = []

    def __init__(self, pool):  # noqa: D401 — matches ProposalsRepo(pool)
        pass

    async def list(self, *, user_id, project_id=None, book_id=None,
                   review_status=None, job_id=None, limit=20, offset=0):
        return list(type(self).rows), len(type(self).rows)


class _FakeEvalRunsRepo:
    persisted: list = []

    def __init__(self, pool):
        pass

    async def persist(self, **kw):
        type(self).persisted.append(kw)
        return None


async def _fake_get_book_profile(pool, book_id):
    return None  # NEUTRAL — legacy scorer behavior


def _client(monkeypatch, rows) -> TestClient:
    _FakeProposalsRepo.rows = rows
    _FakeEvalRunsRepo.persisted = []
    monkeypatch.setattr(eval_api, "ProposalsRepo", _FakeProposalsRepo)
    monkeypatch.setattr(eval_api, "EvalRunsRepo", _FakeEvalRunsRepo)
    monkeypatch.setattr(eval_api, "get_book_profile", _fake_get_book_profile)
    app = FastAPI()
    app.include_router(eval_api.router)
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def _post(client, body):
    return client.post(f"/internal/eval/{PROJECT}/run", json=body, headers=TOKEN)


def test_no_proposals_is_422(monkeypatch):
    resp = _post(_client(monkeypatch, []), {"user_id": str(USER)})
    assert resp.status_code == 422, resp.text


def test_run_without_judges_persists_and_is_fail_closed(monkeypatch):
    resp = _post(_client(monkeypatch, [_row()]), {"user_id": str(USER)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # no judges → usefulness 0 + ensemble unacceptable → gate BLOCKED (fail-closed).
    assert body["judge_ensemble_acceptable"] is False
    assert body["passed"] is False and body["p2_p3_unlocked"] is False
    assert body["n_proposals"] == 1
    # the deterministic sub-scores ran for real (schema found the 3 location dims).
    assert body["subscores"]["schema"] > 0
    # the scorecard was persisted (the gate now has a real run).
    assert len(_FakeEvalRunsRepo.persisted) == 1
    assert _FakeEvalRunsRepo.persisted[0]["project_id"] == PROJECT


def test_rejected_proposals_excluded(monkeypatch):
    # a single rejected row → nothing to score → 422 (not scored as a proposal).
    resp = _post(_client(monkeypatch, [_row(review_status="rejected")]), {"user_id": str(USER)})
    assert resp.status_code == 422, resp.text


def test_missing_internal_token_is_401(monkeypatch):
    client = _client(monkeypatch, [_row()])
    resp = client.post(f"/internal/eval/{PROJECT}/run", json={"user_id": str(USER)})
    assert resp.status_code == 401, resp.text


def test_suite_path_resolves_in_repo():
    p = eval_api._suite_path()
    assert p.is_file() and p.name == "enrichment-eval-suite.toml"


def test_suite_candidates_depth_safe_for_in_container_path():
    # REGRESSION (P3c live-found): in-container /app/app/api/eval.py has only 4
    # parents — parents[4] must NOT be indexed eagerly (it IndexError'd before the
    # /app/eval candidate could be checked). A shallow path → just the /app/eval
    # candidate, no raise.
    from pathlib import Path
    shallow = Path("/app/app/api/eval.py")  # parents: /app/app/api, /app/app, /app, /
    cands = eval_api._suite_candidates(shallow)
    assert cands[0] == Path("/app/eval/enrichment-eval-suite.toml")
    assert all("enrichment-eval-suite.toml" in str(c) for c in cands)
    # a deep (repo) path DOES add the repo-root candidate.
    deep = Path("/r/services/svc/app/api/eval.py")
    assert any("/r/eval/" in str(c).replace("\\", "/") for c in eval_api._suite_candidates(deep))


# ── judge binding (provider-registry /internal/llm/stream) ───────────────────────

@pytest.mark.asyncio
@respx.mock
async def test_judge_binding_calls_provider_registry_and_raises_on_error():
    from app.eval.judge_binding import make_judge_fn_for
    from app.eval.judge_usefulness import JudgeSpec

    base = "http://provider-registry:8080"
    ref = str(uuid4())
    route = respx.post(f"{base}/internal/llm/stream").mock(
        return_value=httpx.Response(500, text="boom")
    )
    judge_fn_for = make_judge_fn_for(base, "tok", {ref: str(USER)})
    fn = judge_fn_for(JudgeSpec(label="j1", model_ref=ref, family="qwen"))
    with pytest.raises(RuntimeError):
        await fn("system", "user")
    # the call carried the model_ref + the owner user_id + the internal token.
    assert route.called
    sent = route.calls.last.request
    assert sent.headers.get("x-internal-token") == "tok"
    assert ref.encode() in sent.content
    assert b"chat" in sent.content
