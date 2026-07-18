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
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK, settings=settings or {})


def _node():
    return OutlineNode(id=NODE, created_by=USER, project_id=PROJECT, book_id=BOOK,
                       kind="scene", rank="a0",
                       chapter_id=uuid.uuid4(), goal="escape", synopsis="the run")


def _job(**kw):
    return GenerationJob(id=JOB, created_by=USER, project_id=PROJECT, book_id=BOOK,
                         operation="draft_scene",
                         input=kw.get("input", {"model_ref": str(DRAFTER)}),
                         critic=kw.get("critic"), status=kw.get("status", "completed"),
                         result=kw.get("result", {"text": "drafted prose"}))


class StubWorks:
    def __init__(self): self.work = _work(); self.source = None
    async def get(self, p): return self.work
    async def get_by_id(self, wid): return self.source


class StubOutline:
    def __init__(self):
        self.node = _node()
        self.chapter_scenes: list = []
    async def get_node(self, n, *, conn=None): return self.node
    async def scenes_for_chapter(self, p, ch): return self.chapter_scenes


class StubCanon:
    def __init__(self, rules=None): self.rules = rules or []
    async def list_active(self, p): return self.rules


class StubJobs:
    def __init__(self):
        self.active = []
        self.created = True
        self.job = _job()
        self.updates = []
    async def list_active_for_node(self, p, n): return self.active
    async def create(self, p, **kw):
        self._last_create = kw
        return self.job, self.created
    async def update_status(self, jid, status, **kw):
        self.updates.append((str(jid), status, kw))
        return self.job
    async def get(self, jid): return self.job


class StubCorrections:
    """S-09 W1 — list_for_job returns the rows a test sets; correction_stats keeps the
    existing route happy (unused here)."""
    def __init__(self): self.rows: list = []
    async def list_for_job(self, project_id, job_id): return list(self.rows)
    async def correction_stats(self, project_id):
        return SimpleNamespace(model_dump=lambda mode=None: {})


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    captured: dict = {}

    async def fake_pack(req, **kw):
        # reinjected_promise_count=2 (non-default) → the response echo (FD-1 S4b)
        # must carry the pack's value, not a hardcoded 0.
        # T3.4 — record the grounding-pins repo so a test can LOCK that the engine
        # threads it into pack (else a refactor silently stops honoring per-scene pins).
        captured["pack_grounding_pins_repo"] = kw.get("grounding_pins_repo", "__missing__")
        return PackedContext(blocks={}, prompt="GROUNDING", profile=NEUTRAL, token_count=5,
                             dropped_count=0, l4_dropped_no_position=0, grounding_available=True,
                             over_budget=False, reinjected_promise_count=2, warnings=[])

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
                          get_embedding_client_dep, get_generation_corrections_repo,
                          get_generation_jobs_repo,
                          get_glossary_client_dep, get_grant_client_dep,
                          get_grounding_pins_repo,
                          get_knowledge_client_dep, get_llm_client_dep,
                          get_narrative_thread_repo, get_outline_repo, get_references_repo,
                          get_scene_links_repo, get_style_profile_repo, get_voice_profile_repo,
                          get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    # E0 book-grant authority stubbed at OWNER; the engine endpoints _gate_work
    # (resolve the Work's book, then gate VIEW/EDIT) before acting (25 PM-8/PM-9).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, outline, canon, jobs = StubWorks(), StubOutline(), StubCanon(), StubJobs()
    corrections = StubCorrections()
    captured["corrections"] = corrections  # so a test can set corrections.rows (yield tuple is fixed)
    app.dependency_overrides[get_generation_corrections_repo] = lambda: corrections
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_canon_rules_repo] = lambda: canon
    app.dependency_overrides[get_generation_jobs_repo] = lambda: jobs
    app.dependency_overrides[get_scene_links_repo] = lambda: object()
    # FD-1: unused unless work.settings.narrative_thread_enabled (off in these tests).
    app.dependency_overrides[get_narrative_thread_repo] = lambda: object()
    # T3.4: pack is patched in these tests, so the repo only needs to satisfy DI.
    app.dependency_overrides[get_grounding_pins_repo] = lambda: object()
    # T3.5: same — style/voice repos only need to satisfy DI (pack is patched).
    app.dependency_overrides[get_style_profile_repo] = lambda: object()
    app.dependency_overrides[get_voice_profile_repo] = lambda: object()
    # T3.6: references repo + embed client only need to satisfy DI (pack is patched).
    app.dependency_overrides[get_references_repo] = lambda: object()
    app.dependency_overrides[get_embedding_client_dep] = lambda: object()
    # C25 — derivatives repo (StubWorks returns non-derivative works → never read).
    app.dependency_overrides[get_derivatives_repo] = lambda: SimpleNamespace(
        list_overrides_for_work=lambda *a, **k: [])
    app.dependency_overrides[get_book_client_dep] = lambda: object()
    app.dependency_overrides[get_glossary_client_dep] = lambda: object()
    app.dependency_overrides[get_knowledge_client_dep] = lambda: object()
    async def _resolve_context_length(model_source, model_ref):
        return None  # unresolved in tests — the flat default budget applies
    app.dependency_overrides[get_llm_client_dep] = lambda: SimpleNamespace(
        sdk=object(), resolve_context_length=_resolve_context_length)
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
    # T3.4 lock — selection_edit must thread grounding_pins_repo into pack.
    assert captured["pack_grounding_pins_repo"] not in (None, "__missing__")


def test_selection_edit_threads_styled_profile(ctx, monkeypatch):
    """T3.5 /review-impl lock: a selection edit builds its prompt from the PACK's
    STYLED profile (density/pace/voice), not the neutral settings profile — the bug
    was passing the from_settings profile to build_selection_messages instead of
    pc.profile, silently dropping Style & Voice on rewrite/expand/describe."""
    c, _, _, _, _, _, captured = ctx
    from app.packer.profile import BookProfile

    async def styled_pack(req, **kw):
        return PackedContext(blocks={}, prompt="GROUNDING",
                             profile=BookProfile(density_level=90),  # lush
                             token_count=5, dropped_count=0, l4_dropped_no_position=0,
                             grounding_available=True, over_budget=False,
                             reinjected_promise_count=0, warnings=[])
    monkeypatch.setattr("app.routers.engine.pack", styled_pack)
    r = c.post(f"/v1/composition/works/{PROJECT}/selection-edit", json={
        "operation": "rewrite", "selection": "x", "scene_context": str(NODE),
        "model_source": "user_model", "model_ref": str(DRAFTER)})
    assert r.status_code == 200
    # the styled profile reached build_selection_messages → its directive is in the system msg
    assert "lush" in captured["messages"][0]["content"].lower()


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


def test_generate_errored_no_content_marks_failed_not_completed(ctx, monkeypatch):
    # D-ENGINE-ERRORED-JOB-MARKED-COMPLETED: a resolve failure emits an error frame
    # then a terminal usage frame with EMPTY text (stream_draft always terminates).
    # The job MUST land 'failed' — never 'completed' with 0 tokens (which a retry/
    # idempotency layer would treat as done).
    c, _, _, _, jobs, _, _ = ctx

    async def errored_stream(sdk, **kw):
        yield {"type": "error", "error": "model_ref could not be resolved"}
        yield {"type": "usage", "text": "",
               "metering": DraftMetering(10, 0, False, finish_reason=None),
               "capped": False, "error": "model_ref could not be resolved"}

    monkeypatch.setattr("app.routers.engine.stream_draft", errored_stream)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 200
    assert any(s == "failed" for _, s, _ in jobs.updates)
    assert not any(s == "completed" for _, s, _ in jobs.updates)
    assert '"status": "failed"' in r.text
    assert "model_ref could not be resolved" in r.text  # error surfaced to the client


def test_generate_error_after_content_still_completes(ctx, monkeypatch):
    # The taxonomy boundary: an error AFTER partial content keeps the drafted prose,
    # so the job stays 'completed' (truncated territory), not failed — only the
    # zero-content case flips to failed.
    c, _, _, _, jobs, _, _ = ctx

    async def partial_then_error(sdk, **kw):
        yield {"type": "token", "delta": "partial"}
        yield {"type": "error", "error": "dropped mid-flight"}
        yield {"type": "usage", "text": "partial",
               "metering": DraftMetering(10, 2, True, finish_reason=None),
               "capped": False, "error": "dropped mid-flight"}

    monkeypatch.setattr("app.routers.engine.stream_draft", partial_then_error)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 200
    assert any(s == "completed" for _, s, _ in jobs.updates)
    assert not any(s == "failed" for _, s, _ in jobs.updates)
    # review MED: the cut-short draft must be flagged truncated + carry the error, not look clean.
    completed_kw = next(kw for _, s, kw in jobs.updates if s == "completed")
    assert completed_kw["result"]["truncated"] is True
    assert completed_kw["result"]["error"] == "dropped mid-flight"
    assert '"truncated": true' in r.text and "dropped mid-flight" in r.text


def test_generate_reasoning_off_is_user_none(ctx):
    # explicit author override → reasoning_effort="none", source="user".
    c, *_, captured = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "reasoning": "off"})
    assert r.status_code == 200
    assert '"reasoning_source": "user"' in r.text
    # T3.4 lock — the scene generate path must thread grounding_pins_repo into pack.
    assert captured["pack_grounding_pins_repo"] not in (None, "__missing__")
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
    jobs.active = [GenerationJob(id=prior, created_by=USER, project_id=PROJECT, book_id=BOOK, operation="x", status="running")]
    c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert (str(prior), "cancelled", {}) in [(j, s, k) for j, s, k in jobs.updates]


def test_generate_idempotent_replay_does_not_restream_or_cancel(ctx):
    # /review-impl M6 #1: a replay (created=False) must NOT cancel the original
    # in-flight job (which is still streaming) nor re-stream.
    c, _, _, _, jobs, _, _ = ctx
    jobs.created = False  # idempotency_key already used
    jobs.active = [GenerationJob(id=uuid.uuid4(), created_by=USER, project_id=PROJECT, book_id=BOOK, operation="x", status="running")]
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
    outline.node = OutlineNode(id=NODE, created_by=USER, project_id=PROJECT, book_id=BOOK,
                               kind="scene",
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
    canon.rules = [CanonRule(id=uuid.uuid4(), created_by=USER, project_id=PROJECT, text="no guns")]
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
    deriv = CompositionWork(project_id=deriv_proj, created_by=USER, book_id=BOOK,
                            id=uuid.uuid4(), source_work_id=uuid.uuid4(),
                            branch_point=3, settings={})
    works.work = deriv
    works.source = CompositionWork(project_id=src_proj, created_by=USER, book_id=BOOK,
                                   id=deriv.source_work_id)

    # derivatives repo returns the active override (the genderbend slip).
    from app.deps import get_derivatives_repo
    from app.main import app

    async def _list_overrides(wid):
        return [SimpleNamespace(target_entity_id=tid,
                                overridden_fields={"description": "now a woman (genderbend)"})]
    app.dependency_overrides[get_derivatives_repo] = lambda: SimpleNamespace(
        list_overrides_for_work=_list_overrides)

    # the BASE present lens (source project) surfaces the entity at its canon value.
    async def fake_base_present(*, glossary, knowledge, book, book_id, user_id, project_id,
                                bearer, present_entity_ids=None, query="",
                                override_target_anchors=None):
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


def _derivative_ctx(c, works, jobs, monkeypatch, *, passage, override_fields,
                    base_summary="a young man, the male lead", prior_attempts=0):
    """Wire a derivative Work + base lens + override for the gate tests. Returns the
    override target id."""
    src_proj = uuid.uuid4()
    tid = uuid.uuid4()
    deriv = CompositionWork(project_id=uuid.uuid4(), created_by=USER, book_id=BOOK,
                            id=uuid.uuid4(), source_work_id=uuid.uuid4(),
                            branch_point=3, settings={})
    works.work = deriv
    works.source = CompositionWork(project_id=src_proj, created_by=USER, book_id=BOOK,
                                   id=deriv.source_work_id)
    from app.deps import get_derivatives_repo
    from app.main import app

    async def _list_overrides(wid):
        return [SimpleNamespace(target_entity_id=tid, overridden_fields=override_fields)]
    app.dependency_overrides[get_derivatives_repo] = lambda: SimpleNamespace(
        list_overrides_for_work=_list_overrides)

    async def fake_base_present(*, glossary, knowledge, book, book_id, user_id,
                                project_id, bearer, present_entity_ids=None, query="",
                                override_target_anchors=None):
        return [{"entity_id": str(tid), "name": "张若尘", "summary": base_summary}]
    monkeypatch.setattr("app.engine.critic_override._gather_base_present", fake_base_present)

    async def _no_anchors(knowledge, bearer, overrides): return {}
    monkeypatch.setattr("app.engine.critic_override._resolve_override_anchors", _no_anchors)

    crit = {"derivative_findings": [], "regen_attempts": prior_attempts} if prior_attempts else None
    jobs.job = _job(result={"text": passage}, critic=crit)
    return tid


def test_critique_derivative_slip_GATES_needs_regeneration(ctx, monkeypatch):
    """C26 GATE — a slipped derivative scene marks the critique needs_regeneration
    (blocks accept / feeds the existing regenerate loop), not merely advisory."""
    c, works, _, _, jobs, _, _ = ctx
    _derivative_ctx(c, works, jobs, monkeypatch,
                    passage="张若尘 stood there, a young man, the male lead.",
                    override_fields={"description": "now a woman (genderbend)"})
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={})
    body = r.json()
    assert r.status_code == 200
    crit = body["critic"]
    assert crit["needs_regeneration"] is True
    assert crit["regen_exhausted"] is False
    assert crit["regen_attempts"] == 1
    # persisted so the regenerate loop + a later critique read the attempt count back.
    assert any(upd[2].get("critic", {}).get("needs_regeneration") is True for upd in jobs.updates)


def test_critique_derivative_compliant_NOT_gated(ctx, monkeypatch):
    """False-positive guard — a correctly-overridden scene (override honoured) is NOT
    flagged: no slip, no needs_regeneration (no spurious regen loop)."""
    c, works, _, _, jobs, _, _ = ctx
    _derivative_ctx(c, works, jobs, monkeypatch,
                    passage="张若尘, now a woman, the heroine, raised her hand.",
                    override_fields={"description": "now a woman (genderbend)"})
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={})
    crit = r.json()["critic"]
    # no derivative findings at all → critic stays the plain (skipped) contract / None.
    if crit is not None:
        assert not crit.get("derivative_findings")
        assert crit.get("needs_regeneration") in (None, False)


def test_critique_derivative_regen_cap_surfaces_to_human(ctx, monkeypatch):
    """The regeneration attempt cap stops a forced loop: once prior_attempts reaches
    the cap, a still-slipping scene flips to regen_exhausted (surface to human) and
    needs_regeneration False — no infinite loop."""
    from app.engine import critic_override as co
    c, works, _, _, jobs, _, _ = ctx
    _derivative_ctx(c, works, jobs, monkeypatch,
                    passage="张若尘 stood there, a young man, the male lead.",
                    override_fields={"description": "now a woman (genderbend)"},
                    prior_attempts=co.REGEN_ATTEMPT_CAP)
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={})
    crit = r.json()["critic"]
    assert crit["needs_regeneration"] is False
    assert crit["regen_exhausted"] is True
    assert crit["regen_attempts"] == co.REGEN_ATTEMPT_CAP + 1


def test_critique_canon_work_not_gated(ctx, monkeypatch):
    """Anti-no-op / canon untouched — a NON-derivative (canon) Work never gets the
    derivative gate even with a distinct critic model."""
    c, works, _, canon, jobs, judge, _ = ctx
    works.work = _work({"critic_model_source": "user_model", "critic_model_ref": str(CRITIC)})
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={})
    crit = r.json()["critic"]
    # the LLM critic ran (canon path) but NO derivative gate fields.
    assert "needs_regeneration" not in crit
    assert "derivative_findings" not in crit


def test_critique_clean_llm_critic_carries_regen_attempts_forward(ctx, monkeypatch):
    """FIX 3 (MED) — a clean LLM-critic run BETWEEN two slips must NOT reset the
    regen-cap counter. The old code read prior_attempts off job.critic but the whole
    critic was COALESCE-replaced on write, dropping regen_attempts → a later slip
    restarted at 0 (the cap stopped bounding). A clean critique now carries the prior
    regen_attempts forward in the persisted critic so the cap still bounds total ≤ N."""
    c, works, _, canon, jobs, judge, _ = ctx
    # distinct critic model → the LLM critic path runs (clean, no derivative findings).
    works.work = _work({"critic_model_source": "user_model", "critic_model_ref": str(CRITIC)})
    # the job already carries a non-zero attempt count from a PRIOR slip critique.
    jobs.job = _job(critic={"regen_attempts": 2}, result={"text": "ordinary prose"})
    r = c.post(f"/v1/composition/jobs/{JOB}/critique", json={})
    assert r.status_code == 200
    crit = r.json()["critic"]
    # the clean critic ran (LLM dims present) AND carried the counter forward.
    assert crit["regen_attempts"] == 2
    # persisted with the carried-forward counter (so a later slip reads 2, not 0).
    persisted = [upd[2].get("critic", {}) for upd in jobs.updates if "critic" in upd[2]]
    assert persisted and persisted[-1].get("regen_attempts") == 2


# ── FIX 2 (HIGH) — the gate actually BLOCKS accept (/persist 409) ──

def _persistable_job(critic=None):
    return _job(status="completed", critic=critic, result={
        "text": "stitched chapter", "chapter_id": str(uuid.uuid4()),
        "assembly_mode": "chapter", "persisted": False})


def test_persist_blocked_when_needs_regeneration(ctx):
    """A slipped critique (needs_regeneration, NOT exhausted) BLOCKS accept with a
    409 OVERRIDE_SLIP_NEEDS_REGEN + surfaces the findings — the gate is no longer
    advisory."""
    c, _, _, _, jobs, _, _ = ctx
    _use_book(_StubBook())
    jobs.job = _persistable_job(critic={
        "needs_regeneration": True, "regen_exhausted": False, "regen_attempts": 1,
        "derivative_findings": [{"kind": "override_slip", "name": "张若尘",
                                 "field": "description", "expected": "现在是女性",
                                 "found": "少年天才"}]})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "OVERRIDE_SLIP_NEEDS_REGEN"
    # the findings are surfaced so the FE/user sees WHY accept is blocked.
    assert detail["derivative_findings"]


def test_persist_allowed_when_compliant(ctx):
    """A compliant critique (no needs_regeneration) → accept succeeds."""
    c, _, _, _, jobs, _, _ = ctx
    book = _StubBook()
    _use_book(book)
    jobs.job = _persistable_job(critic={"needs_regeneration": False})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 200 and r.json()["persisted"] is True


def test_persist_allowed_when_no_critic(ctx):
    """A job with no critic at all (e.g. canon Work, critique never ran) is never
    blocked."""
    c, _, _, _, jobs, _, _ = ctx
    book = _StubBook()
    _use_book(book)
    jobs.job = _persistable_job(critic=None)
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 200 and r.json()["persisted"] is True


def test_persist_fails_open_when_regen_exhausted(ctx):
    """FAIL-OPEN — once the regen cap is reached (regen_exhausted) the gate STOPS
    blocking: accept succeeds even though a slip was found (surface, don't loop
    forever)."""
    c, _, _, _, jobs, _, _ = ctx
    book = _StubBook()
    _use_book(book)
    jobs.job = _persistable_job(critic={
        "needs_regeneration": False, "regen_exhausted": True, "regen_attempts": 4,
        "derivative_findings": [{"kind": "override_slip", "name": "张若尘"}]})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 200 and r.json()["persisted"] is True


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
        self.bodies: list = []

    async def get_draft(self, book_id, chapter_id, bearer):
        return {"draft_version": 7}

    async def patch_draft(self, book_id, chapter_id, bearer, *, body,
                          expected_draft_version, body_format, commit_message):
        self.patched.append(commit_message)
        self.bodies.append(body)
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


def test_persist_job_emits_scene_markers(ctx):
    """F4 wiring lock (nil-tolerant lesson): persist_job must PASS the chapter's
    scenes into the doc build — dropping the `scenes=` kwarg keeps every other
    test green (the fetch is fail-open), so this pins the marker actually landing."""
    c, _, outline, _, jobs, _, _ = ctx
    book = _StubBook()
    _use_book(book)
    CH = uuid.uuid4()
    s1, s2 = uuid.uuid4(), uuid.uuid4()
    outline.chapter_scenes = [SimpleNamespace(id=s1, title="Cuộc Truy Sát"),
                              SimpleNamespace(id=s2, title="Bên Bờ Suối")]
    jobs.job = _job(status="completed", result={
        "text": "### Cuộc Truy Sát\n\nprose one\n\n### Bên Bờ Suối\n\nprose two",
        "chapter_id": str(CH), "assembly_mode": "per_scene_stitch", "persisted": False})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 200 and r.json()["persisted"] is True
    heads = [n for n in book.bodies[0]["content"] if n["type"] == "heading"]
    assert [h["attrs"].get("sceneId") for h in heads] == [str(s1), str(s2)]


def test_persist_job_survives_scene_fetch_failure(ctx):
    """F4 fail-open: a broken outline read must never block the accept — the draft
    persists WITHOUT markers (best-effort contract)."""
    c, _, outline, _, jobs, _, _ = ctx
    book = _StubBook()
    _use_book(book)

    async def boom(p, ch):
        raise RuntimeError("outline down")
    outline.scenes_for_chapter = boom
    jobs.job = _job(status="completed", result={
        "text": "### T\n\nprose", "chapter_id": str(uuid.uuid4()),
        "assembly_mode": "chapter", "persisted": False})
    r = c.post(f"/v1/composition/jobs/{JOB}/persist", json={})
    assert r.status_code == 200 and r.json()["persisted"] is True
    heads = [n for n in book.bodies[0]["content"] if n["type"] == "heading"]
    assert heads and "sceneId" not in heads[0]["attrs"]  # heading kept, marker skipped


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


# ── BE-M4 (3b): GET /works/{pid}/scenes/{node}/suggest-motifs — ranked motif suggest ──
def test_suggest_motifs_returns_ranked_candidates(ctx, monkeypatch):
    """The GUI twin of composition_motif_suggest_for_chapter: ranked {motif,score,match_reason}."""
    from app.db.models import Motif, MotifCandidate
    c = ctx[0]
    motif = Motif(id=uuid.uuid4(), owner_user_id=USER, code="rev.slap", name="Face-slap")

    class _StubRetriever:
        def __init__(self, pool):
            pass

        async def retrieve(self, caller_id, **kw):
            assert kw["project_id"] == PROJECT   # gated Work's project rode through
            return [MotifCandidate(motif=motif, score=0.82, match_reason={"tension": 1, "cosine": 0.8})]

    monkeypatch.setattr("app.routers.engine.get_pool", lambda: object())
    monkeypatch.setattr("app.routers.engine.MotifRetriever", _StubRetriever)
    r = c.get(f"/v1/composition/works/{PROJECT}/scenes/{NODE}/suggest-motifs?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["candidates"]) == 1
    cand = body["candidates"][0]
    assert cand["motif"]["name"] == "Face-slap"
    assert cand["score"] == 0.82
    assert "tension" in cand["match_reason"]


def test_suggest_motifs_404_for_node_in_another_work(ctx, monkeypatch):
    """Per-tool IDOR (via _load_work_node): a node whose project_id != the gated Work → 404."""
    c, _works, outline, *_ = ctx
    # the node resolves to a DIFFERENT project than the URL's PROJECT (reuse the valid _node())
    outline.node = _node().model_copy(update={"project_id": uuid.uuid4()})
    monkeypatch.setattr("app.routers.engine.get_pool", lambda: object())
    monkeypatch.setattr("app.routers.engine.MotifRetriever", lambda pool: None)  # never reached
    r = c.get(f"/v1/composition/works/{PROJECT}/scenes/{NODE}/suggest-motifs")
    assert r.status_code == 404


def test_list_job_corrections(ctx):
    """S-09 W1 — the individual corrections recorded on a generation job (VIEW-gated);
    empty for a job with none, and returns the rows newest-first as the repo yields them."""
    c, works, outline, canon, jobs, judge_stub, captured = ctx
    corrections = captured["corrections"]
    job_id = uuid.uuid4()
    # empty when the job has no corrections
    r = c.get(f"/v1/composition/works/{PROJECT}/jobs/{job_id}/corrections")
    assert r.status_code == 200 and r.json()["corrections"] == []
    # returns each correction the repo yields
    corrections.rows = [SimpleNamespace(model_dump=lambda mode=None: {"id": "c1", "action": "edit"})]
    r = c.get(f"/v1/composition/works/{PROJECT}/jobs/{job_id}/corrections")
    assert r.status_code == 200
    body = r.json()["corrections"]
    assert len(body) == 1 and body[0]["action"] == "edit"
