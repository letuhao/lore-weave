"""M6 engine router tests (TestClient; pack/stream/judge stubbed)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CanonRule, CompositionWork, GenerationJob, OutlineNode
from app.engine.cowrite import DraftMetering
from app.packer.profile import NEUTRAL, BookProfile
from app.packer.pack import PackedContext

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
BOOK = uuid.uuid4()
NODE = uuid.uuid4()
JOB = uuid.uuid4()
DRAFTER = uuid.uuid4()
CRITIC = uuid.uuid4()


def _work(settings=None):
    return CompositionWork(project_id=PROJECT, user_id=USER, book_id=BOOK, settings=settings or {})


def _node():
    return OutlineNode(id=NODE, user_id=USER, project_id=PROJECT, kind="scene", rank="a0",
                       chapter_id=uuid.uuid4(), goal="escape", synopsis="the run")


def _job(**kw):
    return GenerationJob(id=JOB, user_id=USER, project_id=PROJECT, operation="draft_scene",
                         input=kw.get("input", {"model_ref": str(DRAFTER)}),
                         critic=kw.get("critic"), status=kw.get("status", "completed"),
                         result=kw.get("result", {"text": "drafted prose"}))


class StubWorks:
    def __init__(self): self.work = _work()
    async def get(self, u, p): return self.work


class StubOutline:
    def __init__(self): self.node = _node()
    async def get_node(self, u, n): return self.node


class StubCanon:
    def __init__(self, rules=None): self.rules = rules or []
    async def list_active(self, u, p): return self.rules


class StubJobs:
    def __init__(self):
        self.active = []
        self.created = True
        self.job = _job()
        self.updates = []
    async def list_active_for_node(self, u, p, n): return self.active
    async def create(self, u, p, **kw):
        self._last_create = kw
        return self.job, self.created
    async def update_status(self, u, jid, status, **kw):
        self.updates.append((str(jid), status, kw))
        return self.job
    async def get(self, u, jid): return self.job


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    async def fake_pack(req, **kw):
        return PackedContext(blocks={}, prompt="GROUNDING", profile=NEUTRAL, token_count=5,
                             dropped_count=0, l4_dropped_no_position=0, grounding_available=True,
                             over_budget=False, warnings=[])

    captured: dict = {}

    async def fake_stream(sdk, **kw):
        captured.update(kw)  # so tests can assert what actually reached stream_draft
        yield {"type": "token", "delta": "Hello"}
        yield {"type": "usage", "text": "Hello", "metering": DraftMetering(40, 2, True), "capped": False}

    judge_stub = AsyncMock(return_value={"coherence": 4, "voice_match": 3, "pacing": 3,
                                         "canon_consistency": 5, "violations": []})
    monkeypatch.setattr("app.routers.engine.pack", fake_pack)
    monkeypatch.setattr("app.routers.engine.stream_draft", fake_stream)
    monkeypatch.setattr("app.routers.engine.judge_prose", judge_stub)

    from app.main import app
    from app.deps import (get_book_client_dep, get_canon_rules_repo, get_generation_jobs_repo,
                          get_glossary_client_dep, get_knowledge_client_dep, get_llm_client_dep,
                          get_outline_repo, get_scene_links_repo, get_works_repo)
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    works, outline, canon, jobs = StubWorks(), StubOutline(), StubCanon(), StubJobs()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_canon_rules_repo] = lambda: canon
    app.dependency_overrides[get_generation_jobs_repo] = lambda: jobs
    app.dependency_overrides[get_scene_links_repo] = lambda: object()
    app.dependency_overrides[get_book_client_dep] = lambda: object()
    app.dependency_overrides[get_glossary_client_dep] = lambda: object()
    app.dependency_overrides[get_knowledge_client_dep] = lambda: object()
    app.dependency_overrides[get_llm_client_dep] = lambda: SimpleNamespace(sdk=object())
    with TestClient(app) as c:
        yield c, works, outline, canon, jobs, judge_stub, captured
    app.dependency_overrides.clear()


def _gen_body():
    return {"outline_node_id": str(NODE), "model_source": "user_model", "model_ref": str(DRAFTER)}


# ── generate (SSE) ──

def test_generate_streams_and_completes_job(ctx):
    c, _, _, _, jobs, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 200
    body = r.text
    assert '"type": "job"' in body and '"type": "token"' in body and '"type": "done"' in body
    # the job was completed with the metered tokens
    assert any(s == "completed" for _, s, _ in jobs.updates)


def test_generate_reasoning_off_is_user_none(ctx):
    # explicit author override → reasoning_effort="none", source="user".
    c, *_, captured = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "reasoning": "off"})
    assert r.status_code == 200
    assert '"reasoning_source": "user"' in r.text
    assert '"reasoning_effort": "none"' in r.text
    # /review-impl MED#1: the resolved effort must actually REACH stream_draft.
    assert captured["reasoning_effort"] == "none"


def test_generate_reasoning_auto_on_effort_model_uses_scorer(ctx):
    # auto + a reasoning model hint (qwen3) → the rule-based scorer decides.
    c, *_, captured = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={
        **_gen_body(), "reasoning": "auto",
        "model_kind": "lm_studio", "model_name": "qwen/qwen3.6-35b-a3b"})
    assert r.status_code == 200
    assert '"reasoning_source": "rule_based"' in r.text
    # draft_scene + 0 canon → medium, and it must reach stream_draft.
    assert captured["reasoning_effort"] == "medium"


def test_generate_reasoning_auto_on_adaptive_model_passes_through(ctx):
    # auto + an adaptive model (Anthropic) → pass through, omit effort.
    c, *_, captured = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={
        **_gen_body(), "reasoning": "auto",
        "model_kind": "anthropic", "model_name": "claude-opus-4-8"})
    assert r.status_code == 200
    assert '"reasoning_source": "adaptive"' in r.text
    assert '"reasoning_effort": null' in r.text
    # passthrough → stream_draft must receive None (let the model self-decide).
    assert captured["reasoning_effort"] is None


def test_generate_cancels_in_flight_job_s2(ctx):
    c, _, _, _, jobs, _, _ = ctx
    prior = uuid.uuid4()
    jobs.active = [GenerationJob(id=prior, user_id=USER, project_id=PROJECT, operation="x", status="running")]
    c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert (str(prior), "cancelled", {}) in [(j, s, k) for j, s, k in jobs.updates]


def test_generate_idempotent_replay_does_not_restream_or_cancel(ctx):
    # /review-impl M6 #1: a replay (created=False) must NOT cancel the original
    # in-flight job (which is still streaming) nor re-stream.
    c, _, _, _, jobs, _, _ = ctx
    jobs.created = False  # idempotency_key already used
    jobs.active = [GenerationJob(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, operation="x", status="running")]
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "idempotency_key": "k1"})
    assert '"replay": true' in r.text and '"type": "token"' not in r.text
    assert not any(s == "cancelled" for _, s, _ in jobs.updates)  # original survives


def test_generate_rejects_invalid_model_source(ctx):
    # /review-impl M6 #2: bad enum → 422 BEFORE any job/stream (not a 500).
    c, _, _, _, jobs, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate",
               json={**_gen_body(), "model_source": "bogus"})
    assert r.status_code == 422


# ── critique ──

def test_critique_runs_with_distinct_critic_and_fresh_canon(ctx):
    c, works, _, canon, jobs, judge, _ = ctx
    works.work = _work({"critic_model_source": "user_model", "critic_model_ref": str(CRITIC)})
    canon.rules = [CanonRule(id=uuid.uuid4(), user_id=USER, project_id=PROJECT, text="no guns")]
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={"target_revision_id": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["critic"]["canon_consistency"] == 5
    # CC2: judge_prose got the freshly-resolved ACTIVE rule
    assert judge.call_args.kwargs["active_rules"][0]["text"] == "no guns"
    assert judge.call_args.kwargs["model_ref"] == str(CRITIC)  # distinct critic ref


def test_critique_skipped_when_critic_equals_drafter(ctx):
    c, works, _, _, _, judge, _ = ctx
    works.work = _work({"critic_model_source": "user_model", "critic_model_ref": str(DRAFTER)})  # == drafter
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={"target_revision_id": str(uuid.uuid4())})
    assert r.json()["critic"] is None and "skipped" in r.json()["warning"]
    judge.assert_not_called()


def test_critique_skipped_when_no_critic_configured(ctx):
    c, works, _, _, _, judge, _ = ctx
    works.work = _work({})  # no critic model
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={"target_revision_id": str(uuid.uuid4())})
    assert r.json()["critic"] is None
    judge.assert_not_called()


# ── dismiss-violation + get_job + suggest-cast ──

def test_dismiss_violation_marks_dismissed(ctx):
    c, _, _, _, jobs, _, _ = ctx
    jobs.job = _job(critic={"violations": [{"rule_id": "r1", "violated": True}]})
    r = c.post(f"/v1/composition/jobs/{JOB}/dismiss-violation", json={"rule_id": "r1"})
    assert r.status_code == 200 and r.json()["critic"]["violations"][0]["dismissed"] is True


def test_dismiss_unknown_violation_404(ctx):
    c, _, _, _, jobs, _, _ = ctx
    jobs.job = _job(critic={"violations": []})
    assert c.post(f"/v1/composition/jobs/{JOB}/dismiss-violation", json={"rule_id": "zzz"}).status_code == 404


def test_get_job_404_and_happy(ctx):
    c, _, _, _, jobs, _, _ = ctx
    r = c.get(f"/v1/composition/jobs/{JOB}")
    assert r.status_code == 200 and r.json()["id"] == str(JOB)
