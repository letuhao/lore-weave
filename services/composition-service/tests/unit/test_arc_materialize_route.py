"""W10 — the arc-materialize ROUTE (D-W10-APPLY-PLANNER-MATERIALIZE).

Covers the orchestration + guards with faked clients/repos: the happy commit (tree +
ledger), the H13 arc 404, NO_CHAPTERS, the all-unresolved 400, and AlreadyPlanned 409.
The pure beat-distribution/assembly is covered in test_arc_materialize; the commit SQL by
the outline repo tests; this asserts the WIRING (plan→resolve→spec→commit→ledger).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db.models import ArcTemplate, Motif
from app.db.repositories import AlreadyPlannedError

U, P, B = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
MID = uuid.uuid4()
CH1, CH2 = uuid.uuid4(), uuid.uuid4()


def _arc() -> ArcTemplate:
    return ArcTemplate(
        id=uuid.uuid4(), code="rev", name="Revenge", chapter_span=2,
        threads=[{"key": "combat", "label": "Combat"}],
        layout=[{"motif_code": "duel", "motif_id": str(MID), "thread": "combat",
                 "span_start": 1, "span_end": 2, "ord": 0}],
        arc_roster=[],
    )


def _motif() -> Motif:
    return Motif(id=MID, code="duel", name="Duel",
                 beats=[{"key": "b0", "label": "open", "tension_target": 3, "order": 0},
                        {"key": "b1", "label": "clash", "tension_target": 4, "order": 1}],
                 roles=[{"key": "protagonist", "actant": "subject", "label": "hero"}])


class _FakeMotifs:
    def __init__(self, motif): self._m = motif
    async def get_visible(self, u, mid): return self._m
    async def get_by_codes(self, u, codes): return {}


class _FakeArcs:
    def __init__(self, arc): self._a = arc
    async def get_visible(self, u, aid): return self._a


class _FakeBook:
    def __init__(self, chapters): self._ch = chapters
    async def list_chapters(self, book_id, bearer): return self._ch


class _FakeKal:
    async def roster(self, book_id, **kw): return []


class _FakeOutline:
    def __init__(self, *, raise_already=False):
        self.raise_already = raise_already
        self.committed = None
    async def commit_decomposed_tree(self, p, *, book_id=None, created_by=None, arc_title, chapters, replace, idempotency_key):
        if self.raise_already:
            raise AlreadyPlannedError([CH1])
        self.committed = chapters
        n = sum(len(ch["scenes"]) for ch in chapters)
        return {"arc_id": str(uuid.uuid4()),
                "chapter_ids": [str(ch["chapter_id"]) for ch in chapters],
                "scene_ids": [str(uuid.uuid4()) for _ in range(n)], "replay": False}


class _FakeAppRepo:
    last_rows: list = []
    def __init__(self, pool): pass
    async def insert_many(self, p, b, rows, *, created_by=None, conn=None):
        _FakeAppRepo.last_rows = rows
        return rows


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    monkeypatch.setattr("app.routers.plan.get_pool", lambda: object())
    # the ledger write moved into the shared engine (apply_arc_to_spec), which imports the repo
    # from its SOURCE module — patch there so the fake is picked up by the lazy import.
    monkeypatch.setattr("app.db.repositories.motif_application.MotifApplicationRepo", _FakeAppRepo)

    from app.main import app
    from app.deps import (get_arc_template_repo, get_book_client_dep,
                          get_grant_client_dep, get_kal_client_dep, get_motif_repo,
                          get_outline_repo, get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    # E0 book-grant authority stubbed at OWNER; the arc-materialize route resolves
    # the Work's book then gates EDIT (deny paths in test_grant_gate).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    state = SimpleNamespace(
        arc=_arc(), motif=_motif(), chapters=[
            {"chapter_id": str(CH1), "title": "One", "sort_order": 0},
            {"chapter_id": str(CH2), "title": "Two", "sort_order": 1},
        ], outline=_FakeOutline())

    app.dependency_overrides[get_current_user] = lambda: U
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    app.dependency_overrides[get_works_repo] = lambda: SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(project_id=P, user_id=U, book_id=B, settings={})))
    app.dependency_overrides[get_book_client_dep] = lambda: _FakeBook(state.chapters)
    app.dependency_overrides[get_kal_client_dep] = lambda: _FakeKal()
    app.dependency_overrides[get_outline_repo] = lambda: state.outline
    app.dependency_overrides[get_arc_template_repo] = lambda: _FakeArcs(state.arc)
    app.dependency_overrides[get_motif_repo] = lambda: _FakeMotifs(state.motif)
    with TestClient(app) as c:
        yield c, state
    app.dependency_overrides.clear()


def _post(c, **body):
    base = {"arc_template_id": str(uuid.uuid4())}
    base.update(body)
    return c.post(f"/v1/composition/works/{P}/arc/materialize", json=base)


def test_happy_materialize_commits_tree_and_ledger(client):
    c, state = client
    r = _post(c)
    assert r.status_code == 201, r.text
    data = r.json()
    # 2 beats over 2 chapters → 2 scenes, 2 ledger rows.
    assert data["scenes_total"] == 2 and data["beats_distributed"] == 2
    assert len(data["scene_ids"]) == 2
    assert data["motif_applications"] == 2
    assert data["unresolved_placements"] == []
    assert data["drop_merge_report"] == []   # 2 chapters ≥ arc span → no fold (§12.6)
    # the commit spec mapped onto the book's real chapter_ids (sorted by sort_order).
    committed_ids = [str(ch["chapter_id"]) for ch in state.outline.committed]
    assert committed_ids == [str(CH1), str(CH2)]
    # each ledger row got its scene node id + the arc lineage annotation.
    assert all(r_["outline_node_id"] for r_ in _FakeAppRepo.last_rows)
    assert _FakeAppRepo.last_rows[0]["annotations"]["arc_template_id"] == str(state.arc.id)


def test_arc_not_visible_is_404(client):
    c, state = client
    state.arc = None  # not overridden in the dep — patch the fake directly
    from app.main import app
    from app.deps import get_arc_template_repo
    app.dependency_overrides[get_arc_template_repo] = lambda: _FakeArcs(None)
    r = _post(c)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "ARC_TEMPLATE_NOT_FOUND"


def test_no_chapters_is_400(client):
    c, state = client
    from app.main import app
    from app.deps import get_book_client_dep
    app.dependency_overrides[get_book_client_dep] = lambda: _FakeBook([])
    r = _post(c)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "NO_CHAPTERS"


def test_all_unresolved_is_400(client):
    c, state = client
    from app.main import app
    from app.deps import get_motif_repo
    # motif resolves to None (foreign/archived) → nothing materializes.
    app.dependency_overrides[get_motif_repo] = lambda: _FakeMotifs(None)
    r = _post(c)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NO_MATERIALIZABLE_PLACEMENTS"
    assert r.json()["detail"]["unresolved_placements"][0]["motif_code"] == "duel"


def test_already_planned_is_409(client):
    c, state = client
    from app.main import app
    from app.deps import get_outline_repo
    app.dependency_overrides[get_outline_repo] = lambda: _FakeOutline(raise_already=True)
    r = _post(c)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CHAPTER_ALREADY_PLANNED"
