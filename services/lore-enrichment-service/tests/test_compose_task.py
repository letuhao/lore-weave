"""Compose one-shot task store + executor + poll (LLM re-arch Phase 3 M2).

The two interactive compose LLM calls (profile-suggest, intent-resolve) now run OFF
the request path via :mod:`app.compose.compose_task`: the endpoint creates a 'pending'
task + enqueues a resume-stream trigger, the resume worker runs the compute, and
GET /compose-tasks/{id} polls. These tests cover (all fakes — no live stack):

  * run_compose_task orchestration — idempotent completed-skip, dispatch, business
    failure → 'failed', not-found drop;
  * the two compute fns (compute_profile_suggest / compute_intent_resolve) — the LLM
    pipeline + best-effort KG / glossary degrade (moved off the endpoint);
  * dispatch_resume_message — the worker's task-vs-gap-fill branch;
  * the poll route — 200 + result, 404 (absent / not-the-caller's), 401, user-scoping.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jwt as pyjwt

from app.clients.book import BookProjection
from app.compose import compose_task as ct
from app.db.book_profile import NEUTRAL_PROFILE
from app.deps import get_db
from app.generation.complete import CompletionSeamError
from app.services.profile_suggest import ProfileSuggestError

OWNER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"


def _bearer(sub: str = OWNER) -> str:
    return pyjwt.encode({"sub": sub}, "x", algorithm="HS256")


# ── run_compose_task orchestration (patched store + compute) ──────────────────


def _patch_orchestration(monkeypatch, *, row, compute_result=None, compute_raises=None):
    marks: list = []

    async def _load(pool, *, task_id, user_id=None):
        return row

    async def _mark(pool, *, task_id, status, result=None, error=None):
        marks.append({"status": status, "result": result, "error": error})

    async def _compute(pool, **kw):
        if compute_raises is not None:
            raise compute_raises
        return compute_result

    monkeypatch.setattr(ct, "load_compose_task", _load)
    monkeypatch.setattr(ct, "_mark", _mark)
    monkeypatch.setattr(ct, "compute_profile_suggest", _compute)
    monkeypatch.setattr(ct, "compute_intent_resolve", _compute)
    return marks


def _pending_row(kind="profile_suggest", **req):
    base = {"user_id": OWNER, "book_id": str(uuid4()), "project_id": str(uuid4()),
            "suggest_model_ref": str(uuid4()), "sample_chapter_ids": []}
    base.update(req)
    return {"task_id": str(uuid4()), "kind": kind, "status": "pending", "request": base}


def test_run_completed_task_skips(monkeypatch):
    row = _pending_row()
    row["status"] = "completed"
    marks = _patch_orchestration(monkeypatch, row=row, compute_result={"x": 1})
    out = asyncio.run(ct.run_compose_task(object(), task_id=row["task_id"]))
    assert out == "already_completed"
    assert marks == []  # no recompute, no re-mark


def test_run_dispatches_and_completes(monkeypatch):
    row = _pending_row()
    marks = _patch_orchestration(monkeypatch, row=row, compute_result={"worldview": "w"})
    out = asyncio.run(ct.run_compose_task(object(), task_id=row["task_id"]))
    assert out == "completed"
    # marked running first, then completed with the compute result.
    assert [m["status"] for m in marks] == ["running", "completed"]
    assert marks[-1]["result"] == {"worldview": "w"}


def test_run_business_error_marks_failed(monkeypatch):
    row = _pending_row()
    marks = _patch_orchestration(
        monkeypatch, row=row, compute_raises=CompletionSeamError("llm down"))
    out = asyncio.run(ct.run_compose_task(object(), task_id=row["task_id"]))
    assert out == "failed"
    assert [m["status"] for m in marks] == ["running", "failed"]
    assert "llm down" in marks[-1]["error"]


def test_run_unusable_output_marks_failed(monkeypatch):
    row = _pending_row(kind="intent_resolve", intent_text="x", generation_model_ref=str(uuid4()))
    marks = _patch_orchestration(
        monkeypatch, row=row, compute_raises=ProfileSuggestError("no json"))
    out = asyncio.run(ct.run_compose_task(object(), task_id=row["task_id"]))
    assert out == "failed" and marks[-1]["status"] == "failed"


def test_run_not_found(monkeypatch):
    _patch_orchestration(monkeypatch, row=None)
    out = asyncio.run(ct.run_compose_task(object(), task_id=str(uuid4())))
    assert out == "not_found"


# ── store write path: create_compose_task (the INSERT params) ─────────────────


class _CreateConn:
    """Captures the fetchval INSERT params and returns a fixed task_id."""

    def __init__(self, task_id):
        self._task_id = task_id
        self.params: tuple = ()

    async def fetchval(self, _sql, *params):
        self.params = params
        return self._task_id


def test_create_compose_task_writes_columns():
    import json
    from uuid import UUID
    tid = uuid4()
    conn = _CreateConn(tid)
    proj, book = str(uuid4()), str(uuid4())
    req = {"user_id": OWNER, "book_id": book, "project_id": proj,
           "suggest_model_ref": str(uuid4()), "sample_chapter_ids": []}
    out = asyncio.run(ct.create_compose_task(
        _PollPool(conn), kind="profile_suggest", user_id=OWNER,
        project_id=proj, book_id=book, request=req,
    ))
    assert out == str(tid)
    kind, user, project, book_uuid, request_json = conn.params
    assert kind == "profile_suggest"
    assert user == UUID(OWNER) and project == UUID(proj) and book_uuid == UUID(book)
    assert json.loads(request_json) == req  # request shape persisted intact


def test_create_compose_task_null_book():
    tid = uuid4()
    conn = _CreateConn(tid)
    asyncio.run(ct.create_compose_task(
        _PollPool(conn), kind="intent_resolve", user_id=OWNER,
        project_id=str(uuid4()), book_id=None, request={"intent_text": "x"},
    ))
    assert conn.params[3] is None  # book_id NULL when absent


# ── compute: profile suggest (LLM pipeline moved off the endpoint) ────────────


def _projection(book_id):
    return BookProjection(
        book_id=book_id, title="Neon Saigon", original_language="vi",
        description="cyberpunk", summary_excerpt="",
        genre_tags=["cyberpunk"], chapter_count=5,
    )


def _patch_suggest(monkeypatch, *, llm_text, kg_raises=False, chapter_text="第一回 正文"):
    ch = uuid4()

    class _Chapter:
        chapter_id = ch

    class _FakeBook:
        def __init__(self, **_kw): ...
        async def get_projection(self, *, book_id):
            return _projection(book_id)
        async def list_chapters(self, *, book_id, limit):
            return [_Chapter()], 1
        async def get_chapter_text(self, *, book_id, chapter_id):
            return chapter_text
        async def aclose(self): ...

    class _FakeKnowledge:
        def __init__(self, **_kw): ...
        async def build_context(self, *, user_id, project_id, message):
            if kg_raises:
                from app.clients.knowledge import KnowledgeServiceError
                raise KnowledgeServiceError("kg down")
            from types import SimpleNamespace
            return SimpleNamespace(context="<passages>…</passages>")
        async def aclose(self): ...

    def _make(**_kw):
        async def _complete(prompt, ctx):
            return llm_text
        return _complete

    monkeypatch.setattr(ct, "BookClient", _FakeBook)
    monkeypatch.setattr(ct, "KnowledgeClient", _FakeKnowledge)
    monkeypatch.setattr(ct, "make_complete_fn", _make)


def test_compute_profile_suggest_returns_draft(monkeypatch):
    _patch_suggest(
        monkeypatch,
        llm_text='{"worldview": "near-future cyberpunk Saigon", "language": "vi", '
                 '"dimension_overrides": {"character": {"add": [{"id": "implants", "label": "Cyberware"}]}}}',
    )
    out = asyncio.run(ct.compute_profile_suggest(
        object(), user_id=OWNER, book_id=str(uuid4()), project_id=str(uuid4()),
        suggest_model_ref=str(uuid4()), sample_chapter_ids=[],
    ))
    assert out["worldview"] == "near-future cyberpunk Saigon"
    assert out["language"] == "vi"
    assert out["profile_source"] == "ai_suggested"
    assert out["dimension_overrides"]["character"]["add"][0]["id"] == "implants"


def test_compute_profile_suggest_degrades_when_kg_down(monkeypatch):
    _patch_suggest(monkeypatch, llm_text='{"worldview": "w", "language": "vi"}', kg_raises=True)
    out = asyncio.run(ct.compute_profile_suggest(
        object(), user_id=OWNER, book_id=str(uuid4()), project_id=str(uuid4()),
        suggest_model_ref=str(uuid4()), sample_chapter_ids=[],
    ))
    assert out["worldview"] == "w"  # KG down → book-only, still computes


def test_compute_profile_suggest_no_json_raises(monkeypatch):
    _patch_suggest(monkeypatch, llm_text="I'm sorry, I cannot help with that.")
    with pytest.raises(ProfileSuggestError):
        asyncio.run(ct.compute_profile_suggest(
            object(), user_id=OWNER, book_id=str(uuid4()), project_id=str(uuid4()),
            suggest_model_ref=str(uuid4()), sample_chapter_ids=[],
        ))


# ── compute: intent resolve ───────────────────────────────────────────────────


def _patch_intent(monkeypatch, *, llm_text=None, llm_raises=None, glossary_down=False,
                  entities=None):
    from types import SimpleNamespace

    class _FakeGlossary:
        def __init__(self, **_kw): ...
        async def list_entities(self, *, book_id, limit):
            if glossary_down:
                raise RuntimeError("glossary down")
            return entities or []
        async def aclose(self): ...

    async def _neutral(_pool, _book_id):
        return NEUTRAL_PROFILE

    def _make(**_kw):
        async def _complete(prompt, ctx):
            if llm_raises is not None:
                raise llm_raises
            return llm_text
        return _complete

    monkeypatch.setattr(ct, "GlossaryClient", _FakeGlossary)
    monkeypatch.setattr(ct, "get_book_profile", _neutral)
    monkeypatch.setattr(ct, "make_complete_fn", _make)


def test_compute_intent_resolve_returns_target(monkeypatch):
    from types import SimpleNamespace
    _patch_intent(
        monkeypatch,
        llm_text='{"target":{"mode":"existing","canonical_name":"姜子牙","entity_kind":"character"},'
                 '"dimensions":["历史"],"technique":"retrieval","rationale":"in list"}',
        entities=[SimpleNamespace(name="姜子牙", kind="character")],
    )
    out = asyncio.run(ct.compute_intent_resolve(
        object(), user_id=OWNER, project_id=str(uuid4()), book_id=str(uuid4()),
        intent_text="the king's advisor", generation_model_ref=str(uuid4()),
    ))
    assert out["target"]["canonical_name"] == "姜子牙"
    assert out["technique"] == "retrieval"


def test_compute_intent_resolve_degrades_when_glossary_down(monkeypatch):
    _patch_intent(
        monkeypatch, glossary_down=True,
        llm_text='{"target":{"mode":"new","canonical_name":"新仙","entity_kind":"character"},'
                 '"technique":"fabrication"}',
    )
    out = asyncio.run(ct.compute_intent_resolve(
        object(), user_id=OWNER, project_id=str(uuid4()), book_id=str(uuid4()),
        intent_text="a new immortal", generation_model_ref=str(uuid4()),
    ))
    assert out["target"]["canonical_name"] == "新仙"  # glossary down → [] hint, still resolves


def test_compute_intent_resolve_llm_error_propagates(monkeypatch):
    _patch_intent(monkeypatch, llm_raises=CompletionSeamError("llm down", retryable=False))
    with pytest.raises(CompletionSeamError):
        asyncio.run(ct.compute_intent_resolve(
            object(), user_id=OWNER, project_id=str(uuid4()), book_id=str(uuid4()),
            intent_text="x", generation_model_ref=str(uuid4()),
        ))


# ── worker dispatch branch ─────────────────────────────────────────────────────


def test_dispatch_routes_task_to_compose(monkeypatch):
    from app.worker import resume_consumer as rc
    seen: dict = {}

    async def _run(pool, *, task_id):
        seen["task_id"] = task_id

    async def _redrive(*, pool, job_id, project_id, user_id):
        seen["redrive"] = job_id

    monkeypatch.setattr(rc, "run_compose_task", _run)
    monkeypatch.setattr(rc, "redrive_one", _redrive)
    asyncio.run(rc.dispatch_resume_message(
        pool=object(), fields={"task_id": "t-1", "kind": "profile_suggest"}))
    assert seen == {"task_id": "t-1"}  # routed to the compose task, NOT redrive


def test_dispatch_routes_jobid_to_redrive(monkeypatch):
    from app.worker import resume_consumer as rc
    seen: dict = {}

    async def _run(pool, *, task_id):
        seen["task_id"] = task_id

    async def _redrive(*, pool, job_id, project_id, user_id):
        seen["redrive"] = job_id

    monkeypatch.setattr(rc, "run_compose_task", _run)
    monkeypatch.setattr(rc, "redrive_one", _redrive)
    asyncio.run(rc.dispatch_resume_message(
        pool=object(), fields={"job_id": "j-1", "project_id": "p", "user_id": "u"}))
    assert seen == {"redrive": "j-1"}  # legacy gap-fill shape


# ── poll endpoint ──────────────────────────────────────────────────────────────


class _PollConn:
    """Records the fetchrow params (to prove user-scoping) and returns a row/None."""

    def __init__(self, row):
        self._row = row
        self.params: tuple = ()

    async def fetchrow(self, _sql, *params):
        self.params = params
        return self._row


class _PollPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _A:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _A()


def _poll_app(pool):
    from app.api import compose_tasks
    app = FastAPI()
    app.include_router(compose_tasks.router)
    app.dependency_overrides[get_db] = lambda: pool
    return app


def _db_row(task_id, *, status="completed", result_json='{"worldview": "w"}'):
    import json
    return {
        "task_id": task_id, "kind": "profile_suggest", "status": status,
        "user_id": uuid4(), "project_id": uuid4(), "book_id": uuid4(),
        "request_json": json.dumps({"a": 1}),
        "result_json": result_json, "error_message": None,
    }


def test_poll_returns_completed_result():
    tid = uuid4()
    conn = _PollConn(_db_row(tid))
    resp = TestClient(_poll_app(_PollPool(conn))).get(
        f"/v1/lore-enrichment/compose-tasks/{tid}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["result"] == {"worldview": "w"}
    # user-scoping: the caller's id is bound into the WHERE (anti cross-user oracle).
    assert any(str(p) == OWNER for p in conn.params)


def test_poll_404_when_absent():
    conn = _PollConn(None)  # no row (absent OR not the caller's)
    resp = TestClient(_poll_app(_PollPool(conn))).get(
        f"/v1/lore-enrichment/compose-tasks/{uuid4()}",
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 404


def test_poll_requires_auth():
    conn = _PollConn(None)
    resp = TestClient(_poll_app(_PollPool(conn))).get(
        f"/v1/lore-enrichment/compose-tasks/{uuid4()}",
    )
    assert resp.status_code == 401
