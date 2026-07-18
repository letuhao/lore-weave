"""B1 chapter-assembly-mode plumbing tests.

Covers the pure resolver (precedence + defense-in-depth fallback), the WorkPatch
settings enum validator (422 on a bad stored value), and the /generate wiring
(501 on the not-yet-implemented 'chapter' mode + echo of the resolved mode).
"""

from __future__ import annotations

import uuid

import pydantic
import pytest

from app.engine.assembly import ASSEMBLY_MODES, resolve_assembly_mode
from app.routers.works import WorkPatch

# Reuse the engine-router TestClient fixture + ids (pack/stream/judge stubbed).
from tests.unit.test_engine_router import (  # noqa: F401
    BOOK, DRAFTER, JOB, NODE, PROJECT, USER, ctx,
)


# ── resolver (pure) ──

def test_resolve_override_wins_over_setting_and_default():
    assert resolve_assembly_mode("chapter", {"assembly_mode": "per_scene"}, "per_scene") == "chapter"


def test_resolve_setting_used_when_no_override():
    assert resolve_assembly_mode(None, {"assembly_mode": "chapter"}, "per_scene") == "chapter"


def test_resolve_default_when_no_override_or_setting():
    assert resolve_assembly_mode(None, {}, "chapter") == "chapter"
    assert resolve_assembly_mode(None, None, "per_scene") == "per_scene"


def test_resolve_skips_invalid_candidates_and_falls_back():
    # A legacy/hand-edited row with a bad stored value must not crash generation:
    # skip it, fall through to the (valid) default.
    assert resolve_assembly_mode(None, {"assembly_mode": "bogus"}, "chapter") == "chapter"
    # Everything invalid → the per_scene safety net.
    assert resolve_assembly_mode(None, {"assembly_mode": "bogus"}, "also_bad") == "per_scene"


def test_assembly_modes_is_the_closed_set():
    assert ASSEMBLY_MODES == ("per_scene", "chapter")


# ── WorkPatch settings enum validation (pure model; FastAPI maps to 422) ──

def test_workpatch_rejects_bad_assembly_mode():
    with pytest.raises(pydantic.ValidationError):
        WorkPatch(settings={"assembly_mode": "bogus"})


def test_workpatch_accepts_valid_assembly_mode():
    assert WorkPatch(settings={"assembly_mode": "chapter"}).settings == {"assembly_mode": "chapter"}


def test_workpatch_settings_without_assembly_mode_unaffected():
    assert WorkPatch(settings={"voice": "wry"}).settings == {"voice": "wry"}


# ── /generate wiring ──

def _gen_body():
    return {"outline_node_id": str(NODE), "model_source": "user_model", "model_ref": str(DRAFTER)}


def test_generate_explicit_chapter_override_409_redirects(ctx):
    # B2: the per-scene endpoint 409-redirects an EXPLICIT assembly_mode='chapter'
    # override to the chapter endpoint, BEFORE any job.
    c, _, _, _, jobs, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate",
               json={**_gen_body(), "assembly_mode": "chapter"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "USE_CHAPTER_ENDPOINT"
    # guarded BEFORE job creation — the StubJobs records kwargs on _last_create
    # only when create() runs; an empty jobs.updates alone wouldn't prove this.
    assert not hasattr(jobs, "_last_create")
    assert jobs.updates == []


def test_generate_work_default_chapter_still_allows_per_scene(ctx):
    # B2: a work whose DEFAULT is 'chapter' does NOT block per-scene co-write via
    # /generate (the mode selects the autonomous entrypoint, not whether co-write
    # is allowed). No explicit override → runs per-scene, echoes per_scene.
    c, works, _, _, _, _, _ = ctx
    works.work.settings = {"assembly_mode": "chapter"}
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 200
    assert '"assembly_mode": "per_scene"' in r.text


def test_generate_per_scene_default_streams_and_echoes_mode(ctx):
    # Default (no override, no setting) → per_scene path runs + echoes the mode.
    c, _, _, _, _, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 200
    assert '"assembly_mode": "per_scene"' in r.text


def test_generate_rejects_bad_assembly_mode_override_422(ctx):
    # Literal field → a bad value 422s at request validation, before any job.
    c, _, _, _, jobs, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate",
               json={**_gen_body(), "assembly_mode": "bogus"})
    assert r.status_code == 422
    assert jobs.updates == []


def test_generate_auto_echoes_assembly_mode(ctx, monkeypatch):
    # The auto (diverge→converge) JSON response echoes the resolved mode too,
    # not just the cowrite SSE job event. (/review-impl LOW-3)
    c, _, _, _, _, _, _ = ctx
    from app.engine.select import Candidate, Selection
    from app.engine.cowrite import DraftMetering

    async def fake_select(llm, judge, **kw):
        cand = Candidate("only", DraftMetering(10, 5, False))
        return Selection(winner=cand, winner_index=0, candidates=[cand],
                         rerank_reason="", rerank_measured=False)

    monkeypatch.setattr("app.routers.engine.select_draft", fake_select)
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json={**_gen_body(), "mode": "auto"})
    assert r.status_code == 200
    assert r.json()["assembly_mode"] == "per_scene"


def test_generate_body_literal_matches_assembly_modes():
    # Drift-lock: the GenerateBody request Literal is hardcoded (Python can't
    # derive a Literal from a runtime tuple), so a 3rd mode added to ASSEMBLY_MODES
    # without updating the request field would silently 422 valid requests. Lock
    # the two sets together. (/review-impl LOW-2)
    from typing import get_args
    from app.routers.engine import GenerateBody

    ann = GenerateBody.model_fields["assembly_mode"].annotation
    literal_values: set = set()
    for member in get_args(ann):  # union members: Literal[...] and NoneType
        literal_values |= set(get_args(member))  # Literal members; non-literal → ()
    assert literal_values == set(ASSEMBLY_MODES)


# ── chapter single-pass endpoint (B2) ──

CHAPTER = uuid.uuid4()
ENT1, ENT2 = uuid.uuid4(), uuid.uuid4()


@pytest.fixture
def chap_ctx(monkeypatch):
    """TestClient wired for the chapter endpoint: scenes_for_chapter + chapter
    parent node + book sort + pack/diverge/run_canon_reflect monkeypatched. The
    outline stub asserts create_node is NEVER called (the synthetic pack node must
    not be persisted — MED-1)."""
    from unittest.mock import AsyncMock

    from fastapi.testclient import TestClient

    from app.db.models import CompositionWork, GenerationJob, OutlineNode
    from app.engine.canon_check import ReflectResult
    from app.engine.cowrite import DraftMetering
    from app.engine.select import Candidate
    from app.packer.pack import PackedContext
    from app.packer.profile import NEUTRAL

    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    chapter_node = OutlineNode(id=uuid.uuid4(), created_by=USER, project_id=PROJECT,
                               book_id=BOOK,
                               kind="chapter", rank="a0", chapter_id=CHAPTER,
                               title="Ch1", goal="the arrival")
    scenes = [
        OutlineNode(id=uuid.uuid4(), created_by=USER, project_id=PROJECT, book_id=BOOK,
                    kind="scene",
                    rank="a0", parent_id=chapter_node.id, chapter_id=CHAPTER, title="S1",
                    synopsis="they enter", tension=30, present_entity_ids=[ENT1],
                    story_order=3000),
        OutlineNode(id=uuid.uuid4(), created_by=USER, project_id=PROJECT, book_id=BOOK,
                    kind="scene",
                    rank="a1", parent_id=chapter_node.id, chapter_id=CHAPTER, title="S2",
                    synopsis="the duel", tension=85, present_entity_ids=[ENT2],
                    pov_entity_id=ENT1, story_order=3001),
    ]

    class W:
        def __init__(self):
            self.work = CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK, settings={})
        async def get(self, p):
            return self.work

    class O:
        def __init__(self):
            self.nodes = {chapter_node.id: chapter_node}
            self.scenes = scenes
            self.gate = {"scenes_total": 2, "scenes_done": 2, "can_publish": True}
        async def scenes_for_chapter(self, p, ch):
            return self.scenes
        async def get_node(self, nid, *, conn=None):
            return self.nodes.get(nid)
        async def chapter_scene_gate(self, p, ch):
            return self.gate
        async def create_node(self, *a, **k):
            raise AssertionError("chapter pack node must NOT be persisted")
        async def create_decomposed_tree(self, *a, **k):
            raise AssertionError("chapter generate must NOT persist a tree")

    class Bk:
        def __init__(self):
            self.patched = None
            self.get_draft_raises = None
            self.patch_raises = None
        async def get_chapter_sort_orders(self, ids):
            return {str(CHAPTER): 3}
        async def get_draft(self, book_id, chapter_id, bearer):
            if self.get_draft_raises:
                raise self.get_draft_raises
            return {"draft_version": 7}
        async def patch_draft(self, book_id, chapter_id, bearer, **kw):
            if self.patch_raises:
                raise self.patch_raises
            self.patched = kw
            return {"draft_version": 8}

    class Cn:
        async def list_active(self, p):
            return []

    class J:
        def __init__(self):
            self.created = True
            self.updates = []
            self.scene_drafts = [{"title": "S1", "text": "scene one prose"},
                                 {"title": "S2", "text": "scene two prose"}]
            self.inflight = None  # set to an active_job_id to simulate the guard firing
            self.job = GenerationJob(id=JOB, created_by=USER, project_id=PROJECT,
                                     book_id=BOOK,
                                     operation="draft_chapter", status="running", input={})
        async def create(self, p, **kw):
            self._last_create = kw
            return self.job, self.created
        async def create_chapter_job_guarded(self, p, ch, **kw):
            # Mirrors the real method: raises the in-flight error when a concurrent
            # active chapter job exists, else creates a node-less chapter job. The
            # real method hardcodes outline_node_id=None, so reflect that here so
            # the happy-path assertions on _last_create still hold.
            if self.inflight is not None:
                from app.db.repositories import ChapterJobInFlightError
                raise ChapterJobInFlightError(self.inflight)
            self._last_create = {"outline_node_id": None, **kw}
            return self.job, self.created
        async def update_status(self, jid, status, **kw):
            self.updates.append((str(jid), status, kw))
            return self.job
        async def get(self, jid):
            return self.job
        async def chapter_scene_drafts(self, p, ch):
            return self.scene_drafts

    state = {"diverge": {}}

    async def fake_pack(req, **kw):
        state["pack_req"] = req  # capture so tests can assert the chapter_sort_hint wiring
        # T3.4 — record the grounding-pins repo so a test can LOCK that generate_chapter
        # threads it into pack (even though a synthetic chapter node id no-ops it).
        state["pack_grounding_pins_repo"] = kw.get("grounding_pins_repo", "__missing__")
        return PackedContext(blocks={}, prompt="GROUNDING", profile=NEUTRAL, token_count=5,
                             dropped_count=0, l4_dropped_no_position=0, grounding_available=True,
                             over_budget=False, warnings=[], scene_sort_order=3)

    async def fake_diverge(llm, **kw):
        state["diverge"] = kw
        return [Candidate("CHAPTER DRAFT", DraftMetering(40, 10, True))]

    async def fake_reflect(**kw):
        state["reflect"] = kw
        return (kw["draft"], ReflectResult(text=kw["draft"], status="checked",
                                           violations=[], iterations=0, resolved=True), 0)

    async def fake_stitch(llm, **kw):
        state["stitch"] = kw
        return "STITCHED CHAPTER", "stop"  # (text, finish_reason)

    monkeypatch.setattr("app.routers.engine.pack", fake_pack)
    monkeypatch.setattr("app.routers.engine.diverge", fake_diverge)
    monkeypatch.setattr("app.routers.engine.run_canon_reflect", fake_reflect)
    monkeypatch.setattr("app.routers.engine.stitch_chapter", fake_stitch)

    from app.deps import (get_book_client_dep, get_canon_rules_repo,
                          get_derivatives_repo, get_generation_jobs_repo,
                          get_glossary_client_dep, get_grant_client_dep,
                          get_grounding_pins_repo,
                          get_embedding_client_dep, get_knowledge_client_dep,
                          get_llm_client_dep, get_narrative_thread_repo, get_outline_repo,
                          get_references_repo, get_scene_links_repo, get_style_profile_repo,
                          get_voice_profile_repo, get_works_repo)
    from app.grant_client import GrantLevel
    from app.main import app
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    # E0 book-grant authority stubbed at OWNER; the chapter/stitch endpoints
    # _gate_work (resolve the Work's book, then gate) before acting.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    from types import SimpleNamespace
    works, outline, jobs, book = W(), O(), J(), Bk()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_outline_repo] = lambda: outline
    app.dependency_overrides[get_canon_rules_repo] = lambda: Cn()
    app.dependency_overrides[get_generation_jobs_repo] = lambda: jobs
    app.dependency_overrides[get_scene_links_repo] = lambda: object()
    app.dependency_overrides[get_narrative_thread_repo] = lambda: object()  # FD-1 (off in tests)
    app.dependency_overrides[get_grounding_pins_repo] = lambda: object()  # T3.4 (pack stubbed)
    app.dependency_overrides[get_style_profile_repo] = lambda: object()  # T3.5 (pack stubbed)
    app.dependency_overrides[get_voice_profile_repo] = lambda: object()  # T3.5 (pack stubbed)
    app.dependency_overrides[get_references_repo] = lambda: object()  # T3.6 (pack stubbed)
    app.dependency_overrides[get_embedding_client_dep] = lambda: object()  # T3.6 (pack stubbed)
    # C25 — derivatives repo (non-derivative works in these tests → never read).
    app.dependency_overrides[get_derivatives_repo] = lambda: SimpleNamespace(
        list_overrides_for_work=lambda *a, **k: [])
    app.dependency_overrides[get_book_client_dep] = lambda: book
    app.dependency_overrides[get_glossary_client_dep] = lambda: object()
    app.dependency_overrides[get_knowledge_client_dep] = lambda: object()
    async def _resolve_context_length(model_source, model_ref):
        return None  # unresolved in tests — the flat default budget applies
    app.dependency_overrides[get_llm_client_dep] = lambda: SimpleNamespace(
        sdk=object(), resolve_context_length=_resolve_context_length)
    with TestClient(app) as c:
        yield c, works, outline, jobs, book, state
    app.dependency_overrides.clear()


def _chap_body():
    return {"model_source": "user_model", "model_ref": str(DRAFTER)}


def _chap_url():
    return f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/generate"


def test_chapter_generate_worker_enabled_enqueues_202(chap_ctx, monkeypatch):
    # M4: COMPOSITION_WORKER_ENABLED → the chapter endpoint resolves pack/sort/critic
    # into job.input behind the in-flight guard + enqueues + 202; the worker runs
    # diverge+reflect. No inline diverge; persistence becomes the accept-step.
    c, _, _, jobs, _, _ = chap_ctx
    monkeypatch.setattr("app.routers.engine.settings.composition_worker_enabled", True)
    enq = {"n": 0}

    async def fake_enqueue(redis_url, *, job_id, user_id, project_id):
        enq["n"] += 1
        return True

    async def must_not_run(llm, **kw):
        raise AssertionError("worker path must not run diverge inline")

    monkeypatch.setattr("app.routers.engine.enqueue_job", fake_enqueue)
    monkeypatch.setattr("app.routers.engine.diverge", must_not_run)
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending" and body["assembly_mode"] == "chapter"
    assert body["enqueued"] == "ok" and enq["n"] == 1
    inp = jobs._last_create["input"]
    assert inp["worker_op"] == "chapter_generate" and inp["packed_prompt"] == "GROUNDING"
    assert inp["chapter_id"] == str(CHAPTER)
    assert inp["present_entity_ids"] == [str(ENT1), str(ENT2)]  # union cast (pov first)
    assert inp["max_out"] == 1400  # plan-sized, carried for the worker
    assert jobs._last_create["status"] == "pending"
    assert not [s for _, s, _ in jobs.updates if s == "completed"]


def test_chapter_generate_in_flight_409_when_worker_enabled(chap_ctx, monkeypatch):
    # The worker path keeps the chapter in-flight guard (409) — a concurrent
    # chapter-level job still blocks (generate + stitch both write the draft).
    c, _, _, jobs, _, _ = chap_ctx
    monkeypatch.setattr("app.routers.engine.settings.composition_worker_enabled", True)
    jobs.inflight = "active-123"

    async def fake_enqueue(redis_url, **kw):
        raise AssertionError("must not enqueue on in-flight conflict")

    monkeypatch.setattr("app.routers.engine.enqueue_job", fake_enqueue)
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CHAPTER_JOB_IN_FLIGHT"


def test_chapter_generate_happy_path(chap_ctx):
    c, _, _, jobs, book, state = chap_ctx
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "CHAPTER DRAFT" and body["assembly_mode"] == "chapter"
    assert body["canon"]["status"] == "checked"
    assert body["truncated"] is False  # clean stop (fake_diverge finish_reason None)
    # single pass — diverge called with k=1, and the union cast reached canon reflect
    assert state["diverge"]["k"] == 1
    # max_out sized from the plan: 2 scenes × 700 = 1400 (< 8192 ceiling).
    assert state["diverge"]["max_tokens"] == 1400
    assert body["max_output_tokens"] == 1400
    # chapter_sort double-fetch fix: the endpoint passes the sort it already
    # fetched as chapter_sort_hint (Bk stub returns 3) so pack() doesn't re-fetch.
    assert state["pack_req"].chapter_sort_hint == 3
    assert state["reflect"]["cast_glossary_ids"] == [str(ENT1), str(ENT2)]
    assert state["reflect"]["scene_sort_order"] == 3
    # job completed, op draft_chapter, no outline_node_id
    assert jobs._last_create["operation"] == "draft_chapter"
    assert jobs._last_create["outline_node_id"] is None
    assert any(s == "completed" for _, s, _ in jobs.updates)
    # MED-2: persisted to the book draft as a Tiptap doc (default persist=True)
    assert body["persisted"] is True and body["draft_version"] == 8
    assert book.patched["body"]["type"] == "doc"
    assert book.patched["expected_draft_version"] == 7  # read-then-write handshake


def test_chapter_persist_uses_post_canon_revised_text(chap_ctx, monkeypatch):
    # /review-impl LOW-1: the text written to the book draft must be the
    # POST-canon-revise text (persist runs AFTER run_canon_reflect), not the
    # pre-revise draft. Regression-lock against a future reorder.
    from app.engine.canon_check import ReflectResult
    c, _, _, _, book, _ = chap_ctx

    async def revising_reflect(**kw):
        return ("REVISED PROSE", ReflectResult(text="REVISED PROSE", status="checked",
                                               violations=[], iterations=1, resolved=True), 5)

    monkeypatch.setattr("app.routers.engine.run_canon_reflect", revising_reflect)
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 200
    assert r.json()["text"] == "REVISED PROSE"
    assert book.patched["body"]["content"][0]["_text"] == "REVISED PROSE"


def test_chapter_generate_persist_false_skips_book_write(chap_ctx):
    c, _, _, _, book, _ = chap_ctx
    r = c.post(_chap_url(), json={**_chap_body(), "persist": False})
    assert r.status_code == 200
    assert r.json()["persisted"] is False
    assert book.patched is None  # no book write


def test_chapter_generate_persist_failure_best_effort_keeps_text(chap_ctx):
    # A book 409 must NOT discard the generated text (cross-store best-effort).
    from app.clients.book_client import BookClientError
    c, _, _, _, book, _ = chap_ctx
    book.patch_raises = BookClientError(status=409, code="CHAPTER_DRAFT_CONFLICT", detail="stale")
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "CHAPTER DRAFT"  # text preserved
    assert body["persisted"] is False and body["persist_error"] == "CHAPTER_DRAFT_CONFLICT"


def test_chapter_generate_no_plan_400(chap_ctx):
    c, _, outline, jobs, _, _ = chap_ctx
    outline.scenes = []  # no decompose plan for this chapter
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NO_CHAPTER_PLAN"
    assert not hasattr(jobs, "_last_create")  # guarded before job creation


def test_chapter_generate_draft_failure_502_fails_job(chap_ctx, monkeypatch):
    c, _, _, jobs, _, _ = chap_ctx

    async def boom(llm, **kw):
        raise RuntimeError("no candidates")

    monkeypatch.setattr("app.routers.engine.diverge", boom)
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 502
    assert any(s == "failed" for _, s, _ in jobs.updates)


def test_chapter_generate_idempotent_replay(chap_ctx):
    c, _, _, jobs, _, state = chap_ctx
    jobs.created = False
    jobs.job.result = {"text": "PRIOR", "canon": {"status": "checked", "resolved": True}}
    r = c.post(_chap_url(), json={**_chap_body(), "idempotency_key": "k1"})
    assert r.status_code == 200
    body = r.json()
    assert body["replay"] is True and body["text"] == "PRIOR"
    assert state["diverge"] == {}  # short-circuited before drafting


def test_chapter_generate_work_404(chap_ctx):
    c, works, _, _, _, _ = chap_ctx
    works.work = None
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 404


def test_chapter_generate_in_flight_409(chap_ctx):
    # Cycle-2 in-flight guard: a concurrent chapter-level job for this chapter
    # rejects with 409 (no LLM spend, no draft race). The guard fires inside the
    # advisory-locked guarded-create, BEFORE drafting.
    c, _, _, jobs, _, state = chap_ctx
    prior = str(uuid.uuid4())
    jobs.inflight = prior
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "CHAPTER_JOB_IN_FLIGHT"
    assert detail["active_job_id"] == prior
    assert state["diverge"] == {}  # never drafted
    assert not hasattr(jobs, "_last_create")  # guard fired before create


def test_chapter_generate_surfaces_truncated(chap_ctx, monkeypatch):
    # D-COMP-TRUNCATION-SURFACING: a winner draft that stopped on "length" → the
    # response surfaces truncated=True + raw finish_reason (non-default: the happy
    # path's None finish_reason yields truncated=False).
    from app.engine.cowrite import DraftMetering
    from app.engine.select import Candidate
    c, _, _, _, _, state = chap_ctx

    async def truncated_diverge(llm, **kw):
        return [Candidate("CHAPTER DRAFT", DraftMetering(40, 10, True, finish_reason="length"))]

    monkeypatch.setattr("app.routers.engine.diverge", truncated_diverge)
    r = c.post(_chap_url(), json=_chap_body())
    assert r.status_code == 200
    body = r.json()
    assert body["truncated"] is True and body["finish_reason"] == "length"
    # T3.4 lock — generate_chapter must thread grounding_pins_repo into pack (the
    # synthetic chapter node id no-ops it inside pack, but the wiring stays guarded).
    assert state["pack_grounding_pins_repo"] not in (None, "__missing__")


# ── stitch endpoint (B3) ──

def _stitch_url():
    return f"/v1/composition/works/{PROJECT}/chapters/{CHAPTER}/stitch"


def test_stitch_happy_path_persists(chap_ctx):
    c, _, _, jobs, book, state = chap_ctx
    r = c.post(_stitch_url(), json=_chap_body())
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "STITCHED CHAPTER" and body["assembly_mode"] == "per_scene_stitch"
    assert body["stitched"] is True and body["degraded"] is False
    assert body["truncated"] is False  # fake_stitch finish_reason "stop"
    # max_out sized from the 2 scene drafts: 2 × 700 = 1400
    assert state["stitch"]["max_tokens"] == 1400 and body["max_output_tokens"] == 1400
    # the chapter's scene drafts reached the stitcher, each opening with its
    # `### <scene title>` line (F4 D-SCENEMARKER-EMIT)
    assert state["stitch"]["scene_drafts"] == [
        "### S1\n\nscene one prose", "### S2\n\nscene two prose"]
    # post-stitch canon re-check ran on the stitched text
    assert state["reflect"]["draft"] == "STITCHED CHAPTER"
    assert jobs._last_create["operation"] == "stitch_chapter"
    # persisted as a Tiptap doc
    assert body["persisted"] is True and book.patched["body"]["type"] == "doc"


def test_stitch_degrades_to_raw_concat(chap_ctx, monkeypatch):
    c, _, outline, _, book, _ = chap_ctx

    async def empty_stitch(llm, **kw):
        return "", None  # LLM failure → degrade

    monkeypatch.setattr("app.routers.engine.stitch_chapter", empty_stitch)
    r = c.post(_stitch_url(), json=_chap_body())
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True and body["stitched"] is False
    # raw concatenation of the (heading-prefixed) scene drafts is the fallback
    # artifact — the degraded path carries scene markers deterministically (F4)
    assert body["text"] == "### S1\n\nscene one prose\n\n### S2\n\nscene two prose"
    # a degraded raw-concat has no model stop reason → never truncated
    assert body["truncated"] is False
    # F4 wiring proof — the PERSISTED doc carries sceneId-anchored heading nodes
    # (the whole point of the emit: the chapter lands pre-anchored in the editor).
    heads = [n for n in book.patched["body"]["content"] if n["type"] == "heading"]
    assert [h["attrs"].get("sceneId") for h in heads] == [
        str(outline.scenes[0].id), str(outline.scenes[1].id)]


def test_stitch_surfaces_truncated(chap_ctx, monkeypatch):
    # D-COMP-TRUNCATION-SURFACING: a non-degraded stitch that stopped on "length"
    # → truncated=True (non-default vs the happy path's "stop").
    c, _, _, _, _, _ = chap_ctx

    async def truncated_stitch(llm, **kw):
        return "STITCHED CHAPTER", "length"

    monkeypatch.setattr("app.routers.engine.stitch_chapter", truncated_stitch)
    r = c.post(_stitch_url(), json=_chap_body())
    assert r.status_code == 200
    body = r.json()
    assert body["truncated"] is True and body["finish_reason"] == "length"


def test_stitch_requires_all_scenes_done_409(chap_ctx):
    c, _, outline, jobs, _, _ = chap_ctx
    outline.gate = {"scenes_total": 2, "scenes_done": 1, "can_publish": False}
    r = c.post(_stitch_url(), json=_chap_body())
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SCENES_NOT_DONE"
    assert not hasattr(jobs, "_last_create")


def test_stitch_no_scene_drafts_400(chap_ctx):
    c, _, _, jobs, _, _ = chap_ctx
    jobs.scene_drafts = []
    r = c.post(_stitch_url(), json=_chap_body())
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NO_SCENE_DRAFTS"
    assert not hasattr(jobs, "_last_create")


def test_stitch_persist_false_skips_book_write(chap_ctx):
    c, _, _, _, book, _ = chap_ctx
    r = c.post(_stitch_url(), json={**_chap_body(), "persist": False})
    assert r.status_code == 200
    assert r.json()["persisted"] is False
    assert book.patched is None


def test_stitch_in_flight_409(chap_ctx):
    # Cycle-2: a stitch is blocked by ANY active chapter-level job for the chapter
    # (a running generate or stitch) — both write the same chapter draft. 409, no
    # stitch work performed.
    c, _, _, jobs, _, state = chap_ctx
    prior = str(uuid.uuid4())
    jobs.inflight = prior
    r = c.post(_stitch_url(), json=_chap_body())
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "CHAPTER_JOB_IN_FLIGHT"
    assert detail["active_job_id"] == prior
    assert "stitch" not in state  # stitcher never ran
    assert not hasattr(jobs, "_last_create")
