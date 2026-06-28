"""D-W10-ARC-CONFORMANCE — coarse arc-conformance: realized bindings vs the arc template.

The pure engine `build_arc_conformance` is the join-correctness surface (thread-progress
by code, the realized pacing curve + drift, the structural precedes-succession check, and
the §12.6 unmaterialized honesty). The route section covers the scope=arc dispatch +
tenancy (422 missing id, H13 404 foreign arc, the happy-path report).

NO LLM / NO prose extraction — `coarse=true`, `causal_verified=false` always.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.engine.arc_conformance import build_arc_conformance

U, P = uuid.uuid4(), uuid.uuid4()
# stable motif ids for the precedes graph.
M_HUMIL, M_EXILE, M_SLAP, M_TRYST = (str(uuid.uuid4()) for _ in range(4))


def _arc(*, layout, threads=None, pacing=None, name="Revenge Arc"):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name,
        threads=threads or [{"key": "revenge", "label": "Revenge"}],
        layout=layout, pacing=pacing or [])


def _placement(code, thread="revenge", ord=0):
    return {"motif_code": code, "thread": thread, "ord": ord}


def _r(code, thread="revenge", ch=1, tension=50, mid=None):
    return {"motif_id": mid, "motif_code": code, "thread": thread,
            "chapter_index": ch, "tension": tension}


# ── thread_progress ──────────────────────────────────────────────────────────────

def test_thread_progress_covered_and_missing_by_code():
    arc = _arc(layout=[_placement("humiliation", ord=0),
                       _placement("exile", ord=1),
                       _placement("face_slap", ord=2)])
    realized = [_r("humiliation", ch=1), _r("face_slap", ch=3)]  # exile never bound
    out = build_arc_conformance(arc=arc, realized=realized, precedes_pairs=set())
    tp = {t["thread"]: t for t in out["thread_progress"]}["revenge"]
    assert tp["planned"] == 3 and tp["covered"] == 2
    assert [m["motif_code"] for m in tp["missing"]] == ["exile"]


def test_thread_progress_lists_declared_thread_with_no_placement():
    arc = _arc(layout=[_placement("humiliation", thread="revenge")],
               threads=[{"key": "revenge", "label": "Revenge"},
                        {"key": "romance", "label": "Romance"}])
    out = build_arc_conformance(arc=arc, realized=[_r("humiliation")], precedes_pairs=set())
    threads = {t["thread"]: t for t in out["thread_progress"]}
    assert threads["romance"]["planned"] == 0 and threads["romance"]["covered"] == 0


# ── pacing ─────────────────────────────────────────────────────────────────────────

def test_pacing_realized_curve_averages_per_chapter():
    arc = _arc(layout=[_placement("a")])
    realized = [_r("a", ch=1, tension=40), _r("a", ch=1, tension=60), _r("a", ch=2, tension=80)]
    out = build_arc_conformance(arc=arc, realized=realized, precedes_pairs=set())
    pac = out["pacing"]
    assert pac["realized"] == [
        {"chapter_index": 1, "avg_tension": 50.0, "scenes": 2},
        {"chapter_index": 2, "avg_tension": 80.0, "scenes": 1}]
    assert pac["comparable"] is False  # no template pacing curve given


def test_pacing_compares_against_template_curve_and_reports_max_drift():
    arc = _arc(layout=[_placement("a")], pacing=[{"tension": 30}, {"tension": 90}])
    realized = [_r("a", ch=1, tension=40), _r("a", ch=2, tension=70)]
    out = build_arc_conformance(arc=arc, realized=realized, precedes_pairs=set())
    pac = out["pacing"]
    assert pac["comparable"] is True and pac["planned"] == [30.0, 90.0]
    assert pac["max_drift"] == 20.0  # max(|40-30|, |70-90|)


def test_pacing_non_numeric_template_curve_is_not_comparable():
    arc = _arc(layout=[_placement("a")], pacing=[{"label": "rising"}])  # no tension number
    out = build_arc_conformance(arc=arc, realized=[_r("a", tension=50)], precedes_pairs=set())
    assert out["pacing"]["comparable"] is False and out["pacing"]["planned"] == []


# ── succession (structural precedes) ────────────────────────────────────────────────

def test_succession_counts_legal_transitions():
    arc = _arc(layout=[_placement("humiliation"), _placement("face_slap")])
    realized = [_r("humiliation", ch=1, mid=M_HUMIL), _r("face_slap", ch=2, mid=M_SLAP)]
    out = build_arc_conformance(arc=arc, realized=realized,
                                precedes_pairs={(M_HUMIL, M_SLAP)})
    s = {t["thread"]: t for t in out["succession"]["threads"]}["revenge"]
    assert s["transitions"] == 1 and s["legal"] == 1 and s["violations"] == []


def test_succession_flags_a_reversed_precedes_edge_as_violation():
    arc = _arc(layout=[_placement("face_slap"), _placement("humiliation")])
    # realized order is slap→humiliation, but the graph says humiliation precedes slap.
    realized = [_r("face_slap", ch=1, mid=M_SLAP), _r("humiliation", ch=2, mid=M_HUMIL)]
    out = build_arc_conformance(arc=arc, realized=realized,
                                precedes_pairs={(M_HUMIL, M_SLAP)})
    s = {t["thread"]: t for t in out["succession"]["threads"]}["revenge"]
    assert s["legal"] == 0 and s["violations"] == [{"from_motif_id": M_SLAP, "to_motif_id": M_HUMIL}]


def test_succession_unrelated_pair_is_neither_legal_nor_a_violation():
    arc = _arc(layout=[_placement("humiliation"), _placement("tryst")])
    realized = [_r("humiliation", ch=1, mid=M_HUMIL), _r("tryst", ch=2, mid=M_TRYST)]
    out = build_arc_conformance(arc=arc, realized=realized, precedes_pairs=set())
    s = {t["thread"]: t for t in out["succession"]["threads"]}["revenge"]
    assert s["legal"] == 0 and s["unrelated"] == 1 and s["violations"] == []


# ── unmaterialized + honesty flags ───────────────────────────────────────────────────

def test_unmaterialized_surfaces_dropped_placements():
    arc = _arc(layout=[_placement("humiliation"), _placement("exile"), _placement("face_slap")])
    realized = [_r("humiliation"), _r("face_slap")]  # exile folded away (drop/merge)
    out = build_arc_conformance(arc=arc, realized=realized, precedes_pairs=set())
    assert [p["motif_code"] for p in out["unmaterialized"]] == ["exile"]


def test_report_carries_honest_coarse_flags():
    arc = _arc(layout=[_placement("a")])
    out = build_arc_conformance(arc=arc, realized=[_r("a", ch=1)], precedes_pairs=set())
    assert out["scope"] == "arc" and out["available"] is True
    assert out["coarse"] is True and out["causal_verified"] is False
    assert out["chapter_count"] == 1 and out["arc_name"] == "Revenge Arc"


# ── route dispatch + tenancy ─────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    monkeypatch.setattr("app.routers.conformance.get_pool", lambda: object())

    from app.main import app
    from app.deps import get_arc_template_repo, get_outline_repo, get_works_repo
    from app.middleware.jwt_auth import get_current_user
    from app.routers.conformance import get_conformance_trace_reader

    state = SimpleNamespace(arc=None, rows=[])

    class _Works:
        async def get(self, u, p):
            return SimpleNamespace(project_id=P, user_id=U, book_id=uuid.uuid4())
    class _ArcRepo:
        async def get_visible(self, caller_id, arc_id):
            return state.arc
    class _Reader:
        async def arc_bindings(self, u, p, arc_id):
            return state.rows

    class _MotifRepo:
        def __init__(self, pool):
            pass
        async def successors_by_ids(self, ids):
            return {}
    monkeypatch.setattr("app.routers.conformance.MotifRepo", _MotifRepo)

    app.dependency_overrides[get_current_user] = lambda: U
    app.dependency_overrides[get_works_repo] = lambda: _Works()
    app.dependency_overrides[get_arc_template_repo] = lambda: _ArcRepo()
    app.dependency_overrides[get_conformance_trace_reader] = lambda: _Reader()
    app.dependency_overrides[get_outline_repo] = lambda: object()  # arc branch never uses it
    with TestClient(app) as c:
        yield c, state
    app.dependency_overrides.clear()


def test_route_arc_scope_requires_arc_template_id(client):
    c, _ = client
    r = c.get(f"/v1/composition/works/{P}/conformance?scope=arc")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "ARC_TEMPLATE_ID_REQUIRED"


def test_route_foreign_or_missing_arc_is_404(client):
    c, state = client
    state.arc = None  # get_visible → None
    r = c.get(f"/v1/composition/works/{P}/conformance?scope=arc&arc_template_id={uuid.uuid4()}")
    assert r.status_code == 404


def test_route_arc_scope_returns_the_coarse_report(client):
    c, state = client
    aid = uuid.uuid4()
    state.arc = _arc(layout=[_placement("humiliation"), _placement("exile")])
    state.arc.id = aid
    ch1 = uuid.uuid4()
    state.rows = [{"motif_id": M_HUMIL, "motif_code": "humiliation",
                   "annotations": {"thread": "revenge", "arc_template_id": str(aid)},
                   "chapter_id": ch1, "tension": 55, "story_order": 1}]
    r = c.get(f"/v1/composition/works/{P}/conformance?scope=arc&arc_template_id={aid}")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "arc" and body["available"] is True and body["coarse"] is True
    assert body["chapter_count"] == 1
    # 'exile' was planned but never bound → surfaced as unmaterialized.
    assert [p["motif_code"] for p in body["unmaterialized"]] == ["exile"]
