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
    def __init__(self): self.work = _work(); self.source = None
    async def get(self, u, p): return self.work
    async def get_by_id(self, u, wid): return self.source


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
        # reinjected_promise_count=2 (non-default) → the response echo (FD-1 S4b)
        # must carry the pack's value, not a hardcoded 0.
        return PackedContext(blocks={}, prompt="GROUNDING", profile=NEUTRAL, token_count=5,
                             dropped_count=0, l4_dropped_no_position=0, grounding_available=True,
                             over_budget=False, reinjected_promise_count=2, warnings=[])

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
    from app.deps import (get_book_client_dep, get_canon_rules_repo, get_derivatives_repo,
                          get_generation_jobs_repo, get_glossary_client_dep,
                          get_knowledge_client_dep, get_llm_client_dep,
                          get_narrative_thread_repo, get_outline_repo, get_scene_links_repo,
                          get_works_repo)
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    works, outline, canon, jobs = StubWorks(), StubOutline(), StubCanon(), StubJobs()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_canon_rules_repo] = lambda: canon
    app.dependency_overrides[get_generation_jobs_repo] = lambda: jobs
    app.dependency_overrides[get_scene_links_repo] = lambda: object()
    # FD-1: unused unless work.settings.narrative_thread_enabled (off in these tests).
    app.dependency_overrides[get_narrative_thread_repo] = lambda: object()
    # C25 — derivatives repo (StubWorks returns non-derivative works → never read).
    app.dependency_overrides[get_derivatives_repo] = lambda: SimpleNamespace(
        list_overrides_for_work=lambda *a, **k: [])
    app.dependency_overrides[get_book_client_dep] = lambda: object()
    app.dependency_overrides[get_glossary_client_dep] = lambda: object()
    app.dependency_overrides[get_knowledge_client_dep] = lambda: object()
    app.dependency_overrides[get_llm_client_dep] = lambda: SimpleNamespace(sdk=object())
    with TestClient(app) as c:
        yield c, works, outline, canon, jobs, judge_stub, captured
    app.dependency_overrides.clear()


def _gen_body():
    return {"outline_node_id": str(NODE), "model_source": "user_model", "model_ref": str(DRAFTER)}


# ── T3.2 selection-edit (SSE) ──

def test_selection_edit_does_not_tag_the_scene_node(ctx):
    """/review-impl HIGH regression-lock: a selection edit must NOT carry
    outline_node_id — else (DISTINCT ON node, latest completed) it masquerades as
    the scene's draft in chapter_scene_drafts (stitch), prior_scene_drafts (S1
    reinjection), and the publish-gate canon count. The scene id is grounding-only,
    kept in input.scene_context."""
    c, _, _, _, jobs, _, captured = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/selection-edit", json={
        "operation": "rewrite", "selection": "the gate of ash rose",
        "scene_context": str(NODE), "model_source": "user_model", "model_ref": str(DRAFTER)})
    assert r.status_code == 200
    assert jobs._last_create["outline_node_id"] is None              # NOT the scene node
    assert jobs._last_create["input"]["scene_context"] == str(NODE)  # traceability only
    assert jobs._last_create["input"]["selection_edit"] is True
    assert jobs._last_create["operation"] == "rewrite"
    # the SELECTED passage reached the drafter (a selection prompt, not a scene draft).
    assert "the gate of ash rose" in captured["messages"][1]["content"]


def test_selection_edit_worker_enabled_enqueues_202(ctx, monkeypatch):
    # M4: flag-on → the endpoint persists the built message list into job.input +
    # enqueues + 202; the worker drains stream_draft (no inline stream).
    c, _, _, _, jobs, _, _ = ctx
    monkeypatch.setattr("app.routers.engine.settings.composition_worker_enabled", True)
    enq = {"n": 0}

    async def fake_enqueue(redis_url, *, job_id, user_id, project_id):
        enq["n"] += 1
        return True

    async def must_not_stream(sdk, **kw):
        raise AssertionError("worker path must not stream inline")
        yield  # noqa — make it an async generator

    monkeypatch.setattr("app.routers.engine.enqueue_job", fake_enqueue)
    monkeypatch.setattr("app.routers.engine.stream_draft", must_not_stream)
    r = c.post(f"/v1/composition/works/{PROJECT}/selection-edit", json={
        "operation": "rewrite", "selection": "the gate of ash rose",
        "scene_context": str(NODE), "model_source": "user_model", "model_ref": str(DRAFTER)})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending" and body["selection_edit"] is True and body["enqueued"] == "ok"
    assert enq["n"] == 1
    inp = jobs._last_create["input"]
    assert inp["worker_op"] == "selection_edit" and inp["selection_edit"] is True
    assert "the gate of ash rose" in inp["messages"][1]["content"]  # message list serialized
    assert jobs._last_create["status"] == "pending"
    assert jobs._last_create["outline_node_id"] is None  # HIGH: still not tagged to the scene


def test_selection_edit_rejects_unknown_operation(ctx):
    c, *_ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/selection-edit", json={
        "operation": "summarize", "selection": "x",
        "model_source": "user_model", "model_ref": str(DRAFTER)})
    assert r.status_code == 422  # Literal — no silent fallback at the API boundary


# ── generate (SSE) ──

def test_generate_streams_and_completes_job(ctx):
    c, _, _, _, jobs, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 200
    body = r.text
    assert '"type": "job"' in body and '"type": "token"' in body and '"type": "done"' in body
    # the job was completed with the metered tokens
    assert any(s == "completed" for _, s, _ in jobs.updates)
    # D-COMP-TRUNCATION-SURFACING: a clean stop (fake metering finish_reason None) →
    # the done frame reports truncated=false (non-default contrast for the test below).
    assert '"truncated": false' in body


def test_generate_done_surfaces_truncated(ctx, monkeypatch):
    # D-COMP-TRUNCATION-SURFACING: when the stream's terminal metering reports
    # finish_reason="length", the SSE done frame carries truncated=true.
    c, *_ = ctx

    async def trunc_stream(sdk, **kw):
        yield {"type": "token", "delta": "Hello"}
        yield {"type": "usage", "text": "Hello",
               "metering": DraftMetering(40, 2, True, finish_reason="length"), "capped": False}

    monkeypatch.setattr("app.routers.engine.stream_draft", trunc_stream)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 200
    assert '"truncated": true' in r.text and '"finish_reason": "length"' in r.text


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


# ── generate mode=auto (V1 A1 diverge→converge) ──

def test_generate_auto_returns_reranked_winner_as_json(ctx, monkeypatch):
    c, _, _, _, jobs, _, _ = ctx
    from app.engine.select import Candidate, Selection

    async def fake_select(llm, judge, **kw):
        cands = [Candidate("draft A", DraftMetering(10, 5, False)),
                 Candidate("draft B", DraftMetering(10, 6, False))]
        assert kw["k"] == 3  # config default reached select
        return Selection(winner=cands[1], winner_index=1, candidates=cands,
                         rerank_reason="B tightest", rerank_measured=True)

    monkeypatch.setattr("app.routers.engine.select_draft", fake_select)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "mode": "auto"})
    assert r.status_code == 200
    body = r.json()  # JSON, NOT an SSE stream
    assert body["mode"] == "auto" and body["text"] == "draft B"
    assert body["winner_index"] == 1 and body["k"] == 2 and body["rerank_measured"] is True
    assert body["reinjected_promise_count"] == 2  # FD-1 S4b — echoes the pack value
    # slice 3: the K candidate texts are in the response so the FE shows all cards
    assert body["candidates"] == ["draft A", "draft B"]
    # the job completed with the winner persisted (incl. the candidates for transparency)
    completed = [k for _, s, k in jobs.updates if s == "completed"]
    assert completed and completed[0]["result"]["text"] == "draft B"
    assert completed[0]["result"]["candidates"] == ["draft A", "draft B"]
    # D-COMP-TRUNCATION-SURFACING: clean winner (finish_reason None) → truncated false
    # (non-default contrast for test_generate_auto_surfaces_truncated below).
    assert body["truncated"] is False


def test_generate_auto_surfaces_truncated(ctx, monkeypatch):
    # D-COMP-TRUNCATION-SURFACING: the auto path derives truncated from the
    # select_draft winner's metering — a "length" stop → truncated=True.
    c, *_ = ctx
    from app.engine.select import Candidate, Selection

    async def trunc_select(llm, judge, **kw):
        cands = [Candidate("draft A", DraftMetering(10, 9, True, finish_reason="length"))]
        return Selection(winner=cands[0], winner_index=0, candidates=cands,
                         rerank_reason="", rerank_measured=False)

    monkeypatch.setattr("app.routers.engine.select_draft", trunc_select)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "mode": "auto"})
    assert r.status_code == 200
    body = r.json()
    assert body["truncated"] is True and body["finish_reason"] == "length"


def test_generate_auto_uses_adaptive_k_from_node_tension(ctx, monkeypatch):
    # A3: the auto path must derive K from the node's structural weight, NOT the
    # fixed compose_diverge_k. A low-tension connective scene (tension 10 on the
    # 0..100 scale) → K=1. This regression-locks the wiring + the tension SCALE:
    # with a 1-5 mis-scale, tension 10 would read as "high" → ceiling 3 and fail.
    c, _, outline, _, _, _, _ = ctx
    from app.engine.select import Candidate, Selection
    outline.node = OutlineNode(id=NODE, user_id=USER, project_id=PROJECT, kind="scene",
                               rank="a0", chapter_id=uuid.uuid4(), goal="walk",
                               synopsis="a quiet transition", tension=10)
    seen: dict = {}

    async def fake_select(llm, judge, **kw):
        seen["k"] = kw["k"]
        cands = [Candidate("only", DraftMetering(10, 5, False))]
        return Selection(winner=cands[0], winner_index=0, candidates=cands,
                         rerank_reason="", rerank_measured=False)

    monkeypatch.setattr("app.routers.engine.select_draft", fake_select)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "mode": "auto"})
    assert r.status_code == 200
    assert seen["k"] == 1  # tension 10 (low, 0..100) → K=1, not the fixed default 3


def test_generate_auto_select_failure_fails_job_502(ctx, monkeypatch):
    c, _, _, _, jobs, _, _ = ctx

    async def boom(llm, judge, **kw):
        raise RuntimeError("diverge produced no candidates")

    monkeypatch.setattr("app.routers.engine.select_draft", boom)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "mode": "auto"})
    assert r.status_code == 502
    assert any(s == "failed" for _, s, _ in jobs.updates)


def test_generate_auto_idempotent_replay_returns_existing(ctx, monkeypatch):
    c, _, _, _, jobs, _, _ = ctx
    jobs.created = False
    called = {"n": 0}

    async def fake_select(llm, judge, **kw):
        called["n"] += 1
        raise AssertionError("must not run on replay")

    monkeypatch.setattr("app.routers.engine.select_draft", fake_select)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate",
               json={**_gen_body(), "mode": "auto", "idempotency_key": "k1"})
    assert r.status_code == 200 and r.json()["replay"] is True
    assert called["n"] == 0  # short-circuited before select


def test_generate_auto_worker_enabled_enqueues_202(ctx, monkeypatch):
    # M4: COMPOSITION_WORKER_ENABLED → the auto path persists the resolved pack
    # context into job.input + enqueues + 202 (the worker runs select/reflect). No
    # inline select_draft runs. cowrite STREAM stays inline (not tested here).
    c, _, _, _, jobs, _, _ = ctx
    monkeypatch.setattr("app.routers.engine.settings.composition_worker_enabled", True)
    enq = {"n": 0}

    async def fake_enqueue(redis_url, *, job_id, user_id, project_id):
        enq["n"] += 1
        return True

    async def must_not_run(llm, judge, **kw):
        raise AssertionError("worker path must not run select_draft inline")

    monkeypatch.setattr("app.routers.engine.enqueue_job", fake_enqueue)
    monkeypatch.setattr("app.routers.engine.select_draft", must_not_run)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "mode": "auto"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending" and body["mode"] == "auto" and body["enqueued"] == "ok"
    assert enq["n"] == 1
    # the FULLY-RESOLVED pack context + canonical worker_op landed in job.input
    inp = jobs._last_create["input"]
    assert inp["worker_op"] == "generate" and inp["packed_prompt"] == "GROUNDING"
    assert inp["reinjected_promise_count"] == 2  # echoed from the pack
    assert jobs._last_create["status"] == "pending"
    # no terminal update happened inline (the worker will complete it)
    assert not [s for _, s, _ in jobs.updates if s == "completed"]


def test_generate_cowrite_stays_inline_when_worker_enabled(ctx, monkeypatch):
    # The worker decouples ONLY auto; cowrite still streams inline even flag-on.
    c, *_ = ctx
    monkeypatch.setattr("app.routers.engine.settings.composition_worker_enabled", True)

    async def fake_enqueue(redis_url, **kw):
        raise AssertionError("cowrite must not enqueue")

    monkeypatch.setattr("app.routers.engine.enqueue_job", fake_enqueue)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "mode": "cowrite"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]  # still an SSE stream


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


def test_critique_derivative_dimension_FIRES_at_call_site(ctx, monkeypatch):
    """C26 WIRING (anti-no-op) — the derivative critic dimension actually FIRES at
    the real /critique handler for a DERIVATIVE Work: the override slip surfaces as
    `critic.derivative_findings`, persisted, WITHOUT a distinct critic LLM model. A
    wired-but-uninvoked dimension would leave critic=None (the nil-tolerant-decorator
    bug class)."""
    c, works, _, _, jobs, judge, _ = ctx
    src_proj, deriv_proj = uuid.uuid4(), uuid.uuid4()
    tid = uuid.uuid4()
    # A derivative Work: source_work_id set + its OWN delta project. NO critic model.
    deriv = CompositionWork(project_id=deriv_proj, user_id=USER, book_id=BOOK,
                            id=uuid.uuid4(), source_work_id=uuid.uuid4(),
                            branch_point=3, settings={})
    works.work = deriv
    works.source = CompositionWork(project_id=src_proj, user_id=USER, book_id=BOOK,
                                   id=deriv.source_work_id)

    # derivatives repo returns the active override (the genderbend slip).
    from app.deps import get_derivatives_repo
    from app.main import app

    async def _list_overrides(u, wid):
        return [SimpleNamespace(target_entity_id=tid,
                                overridden_fields={"description": "now a woman (genderbend)"})]
    app.dependency_overrides[get_derivatives_repo] = lambda: SimpleNamespace(
        list_overrides_for_work=_list_overrides)

    # the BASE present lens (source project) surfaces the entity at its canon value.
    async def fake_base_present(*, glossary, knowledge, book, book_id, user_id, project_id, bearer):
        assert project_id == src_proj  # base lens hit the SOURCE project
        return [{"entity_id": str(tid), "name": "张若尘", "summary": "a young man, the male lead"}]
    monkeypatch.setattr("app.engine.critic_override._gather_base_present", fake_base_present)
    # no anchor resolve round-trip in this unit (target already == base key)
    async def _no_anchors(knowledge, bearer, overrides): return {}
    monkeypatch.setattr("app.engine.critic_override._resolve_override_anchors", _no_anchors)

    # the drafted passage REVERTS 张若尘 to the canon/base value → override slip.
    jobs.job = _job(result={"text": "张若尘 stood there, a young man, the male lead."})

    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={"target_revision_id": str(uuid.uuid4())})
    body = r.json()
    assert r.status_code == 200
    crit = body["critic"]
    assert crit is not None and "derivative_findings" in crit
    slips = [f for f in crit["derivative_findings"] if f["kind"] == "override_slip"]
    assert slips and slips[0]["entity_id"] == str(tid) and slips[0]["field"] == "description"
    # PERSISTED (the regeneration loop reads it back off the job).
    assert any("derivative_findings" in upd[2].get("critic", {}) for upd in jobs.updates)


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


# ── M4 Option A: accept/persist a worker-computed chapter result ──

class _StubBook:
    def __init__(self):
        self.patched: list = []

    async def get_draft(self, book_id, chapter_id, bearer):
        return {"draft_version": 7}

    async def patch_draft(self, book_id, chapter_id, bearer, *, body,
                          expected_draft_version, body_format, commit_message):
        self.patched.append(commit_message)
        return {"draft_version": 8}


def _use_book(stub):
    from app.main import app
    from app.deps import get_book_client_dep
    app.dependency_overrides[get_book_client_dep] = lambda: stub


def test_persist_job_writes_draft_and_stamps_result(ctx):
    c, _, _, _, jobs, _, _ = ctx
    book = _StubBook()
    _use_book(book)
    CH = uuid.uuid4()
    jobs.job = _job(status="completed", result={
        "text": "stitched chapter", "chapter_id": str(CH),
        "assembly_mode": "per_scene_stitch", "persisted": False})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["persisted"] is True and body["draft_version"] == 8
    assert book.patched == ["AI chapter draft (per_scene_stitch, accepted)"]
    # the result is re-stamped persisted=True (idempotent re-accept guard)
    last = jobs.updates[-1]
    assert last[1] == "completed" and last[2]["result"]["persisted"] is True


def test_persist_job_idempotent_when_already_persisted(ctx):
    c, _, _, _, jobs, _, _ = ctx
    book = _StubBook()
    _use_book(book)
    jobs.job = _job(status="completed", result={
        "text": "x", "chapter_id": str(uuid.uuid4()), "persisted": True, "draft_version": 4})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 200 and r.json() == {
        "job_id": str(JOB), "persisted": True, "draft_version": 4, "already": True}
    assert book.patched == []  # no second PATCH


def test_persist_job_422_when_no_chapter_id(ctx):
    c, _, _, _, jobs, _, _ = ctx
    _use_book(_StubBook())
    jobs.job = _job(status="completed", result={"text": "a per-scene draft"})  # no chapter_id
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "JOB_NOT_PERSISTABLE"


def test_persist_job_409_when_not_completed(ctx):
    c, _, _, _, jobs, _, _ = ctx
    _use_book(_StubBook())
    jobs.job = _job(status="running", result={"text": "x", "chapter_id": str(uuid.uuid4())})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "JOB_NOT_COMPLETED"


def test_persist_job_404_when_missing(ctx):
    c, _, _, _, jobs, _, _ = ctx
    _use_book(_StubBook())
    jobs.job = None
    assert c.post(f"/v1/composition/jobs/{JOB}/persist", json={}).status_code == 404
