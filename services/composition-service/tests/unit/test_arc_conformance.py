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

from app.engine.arc_conformance import build_arc_conformance, build_deep_report

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
    from app.deps import (get_arc_template_repo, get_knowledge_client_dep,
                          get_outline_repo, get_works_repo)
    from app.middleware.jwt_auth import get_current_user
    from app.routers.conformance import get_conformance_trace_reader

    state = SimpleNamespace(arc=None, rows=[], sequences=[], tag_calls=[],
                            motif_tag_calls=[], placement_motifs={}, succ_map={})

    class _Works:
        async def get(self, u, p):
            return SimpleNamespace(project_id=P, user_id=U, book_id=uuid.uuid4())
    class _ArcRepo:
        async def get_visible(self, caller_id, arc_id):
            return state.arc
    class _Reader:
        async def arc_bindings(self, u, p, arc_id):
            return state.rows
    class _Knowledge:
        async def get_motif_beat_sequences(self, user_id, *, book_id=None, corpus=False, language=None):
            return state.sequences
        async def tag_threads(self, user_id, *, book_id, threads, model_source, model_ref):
            state.tag_calls.append({"threads": threads, "model_ref": model_ref})
            return {"tagged": 1, "events_seen": 1, "threads_assigned": {}}
        async def tag_motifs(self, user_id, *, book_id, motifs, model_source, model_ref):
            state.motif_tag_calls.append({"motifs": motifs, "model_ref": model_ref})
            return {"tagged": 1, "events_seen": 1, "motifs_assigned": {}}

    class _MotifRepo:
        def __init__(self, pool):
            pass
        async def successors_by_ids(self, ids):
            return state.succ_map
        async def get_by_codes(self, caller_id, codes):
            return state.placement_motifs
    monkeypatch.setattr("app.routers.conformance.MotifRepo", _MotifRepo)

    app.dependency_overrides[get_current_user] = lambda: U
    app.dependency_overrides[get_works_repo] = lambda: _Works()
    app.dependency_overrides[get_arc_template_repo] = lambda: _ArcRepo()
    app.dependency_overrides[get_conformance_trace_reader] = lambda: _Reader()
    app.dependency_overrides[get_knowledge_client_dep] = lambda: _Knowledge()
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
    # no deep overlay unless deep=true (it's the expensive cross-service path).
    assert "deep" not in body


def test_route_deep_overlay_adds_prose_pacing(client):
    c, state = client
    aid = uuid.uuid4()
    state.arc = _arc(layout=[_placement("humiliation")])
    state.arc.id = aid
    ch1 = uuid.uuid4()
    # planned outline tension 50 on chapter 1 (index 1).
    state.rows = [{"motif_id": M_HUMIL, "motif_code": "humiliation",
                   "annotations": {"thread": "revenge", "arc_template_id": str(aid)},
                   "chapter_id": ch1, "tension": 50, "story_order": 1}]
    # realized prose: two :Event steps on chapter ch1, tension band 5 → 100/100.
    state.sequences = [[{"beat": "the slap", "thread": str(ch1), "tension": 5},
                        {"beat": "the vow", "thread": str(ch1), "tension": 5}]]
    r = c.get(f"/v1/composition/works/{P}/conformance?scope=arc&arc_template_id={aid}&deep=true")
    assert r.status_code == 200
    deep = r.json()["deep"]
    assert deep["available"] is True
    assert deep["pacing"]["realized"][0] == {"chapter_index": 1, "avg_tension": 100.0, "events": 2}
    # drift = |100 (prose) − 50 (planned outline)|.
    assert deep["pacing"]["max_drift"] == 50.0
    # the two honestly-blocked dims.
    assert deep["thread_progression"]["available"] is False
    assert deep["succession"]["available"] is False


# ── build_deep_report (pure prose-pacing) ────────────────────────────────────────────

def test_deep_groups_prose_tension_by_chapter_and_normalizes():
    # ch 'a' index 1 (bands 3,5 → avg 4 → 80), ch 'b' index 2 (band 2 → 40).
    seqs = [[{"beat": "x", "thread": "a", "tension": 3}, {"beat": "y", "thread": "a", "tension": 5},
             {"beat": "z", "thread": "b", "tension": 2}]]
    out = build_deep_report(sequences=seqs, chapter_index_by_id={"a": 1, "b": 2},
                            planned_by_index={1: 80.0, 2: 90.0})
    assert out["available"] is True
    assert out["pacing"]["realized"] == [
        {"chapter_index": 1, "avg_tension": 80.0, "events": 2},
        {"chapter_index": 2, "avg_tension": 40.0, "events": 1}]
    # drift: ch1 |80−80|=0, ch2 |40−90|=50 → max 50.
    assert out["pacing"]["max_drift"] == 50.0


def test_deep_empty_corpus_is_unavailable():
    out = build_deep_report(sequences=[], chapter_index_by_id={"a": 1}, planned_by_index={1: 50.0})
    assert out["available"] is False and out["pacing"]["realized"] == []
    assert out["pacing"]["max_drift"] is None


def test_deep_ignores_events_in_unknown_chapters():
    # an event whose chapter isn't in the arc's materialized set is dropped (no index).
    seqs = [[{"beat": "x", "thread": "ghost", "tension": 4}]]
    out = build_deep_report(sequences=seqs, chapter_index_by_id={"a": 1}, planned_by_index={})
    assert out["available"] is False


def test_deep_thread_progression_from_tagged_beats():
    # tagged beats carry narrative_thread → realized thread-presence vs the arc's threads.
    seqs = [[{"beat": "duel", "thread": "a", "narrative_thread": "combat", "tension": 4},
             {"beat": "tryst", "thread": "b", "narrative_thread": "romance", "tension": 2},
             {"beat": "ambush", "thread": "c", "narrative_thread": "combat", "tension": 5}]]
    out = build_deep_report(
        sequences=seqs, chapter_index_by_id={"a": 1, "b": 2, "c": 3},
        planned_by_index={}, arc_threads=[{"key": "combat", "label": "Combat"},
                                          {"key": "intrigue", "label": "Intrigue"}])
    tp = out["thread_progression"]
    assert tp["available"] is True
    rows = {r["thread"]: r for r in tp["threads"]}
    assert rows["combat"]["realized"] is True and rows["combat"]["realized_chapters"] == 2
    assert rows["intrigue"]["realized"] is False  # planned but never in the prose (drift)
    assert tp["unplanned"] == ["romance"]          # prose introduced a thread the arc didn't plan


def test_deep_thread_progression_ignores_threads_outside_the_arc_chapters():
    # /review-impl #1 — a thread tagged ONLY in a chapter outside the arc's materialized set
    # is NOT counted (no "realized=True with 0 chapters"); realized ⟺ realized_chapters≥1.
    seqs = [[{"beat": "skirmish", "thread": "out", "narrative_thread": "combat", "tension": 4},
             {"beat": "tryst", "thread": "a", "narrative_thread": "romance", "tension": 2}]]
    out = build_deep_report(
        sequences=seqs, chapter_index_by_id={"a": 1},  # only chapter 'a' is in the arc
        planned_by_index={}, arc_threads=[{"key": "combat", "label": "Combat"},
                                          {"key": "romance", "label": "Romance"}])
    rows = {r["thread"]: r for r in out["thread_progression"]["threads"]}
    # combat appeared only in the out-of-arc chapter → not realized here.
    assert rows["combat"]["realized"] is False and rows["combat"]["realized_chapters"] == 0
    assert rows["romance"]["realized"] is True and rows["romance"]["realized_chapters"] == 1
    # no realized row has the contradictory True/0 shape.
    assert all((not r["realized"]) or r["realized_chapters"] >= 1
               for r in out["thread_progression"]["threads"])
    assert out["thread_progression"]["unplanned"] == []  # combat-out-of-arc isn't "unplanned in-arc"


def test_deep_succession_legal_reversed_unrelated():
    # realized motif order from prose (realized_motif_code per step) vs the precedes graph.
    seqs = [[{"realized_motif_code": "humiliation", "thread": "a"},
             {"realized_motif_code": "face_slap", "thread": "b"},   # humiliation→face_slap is legal
             {"realized_motif_code": "tryst", "thread": "c"}]]      # face_slap→tryst: no edge
    out = build_deep_report(sequences=seqs, chapter_index_by_id={}, planned_by_index={},
                            precedes_code_pairs={("humiliation", "face_slap")})
    s = out["succession"]
    assert s["available"] is True and s["causal_verified"] is False
    assert s["transitions"] == 2 and s["legal"] == 1 and s["unrelated"] == 1
    assert s["violations"] == []


def test_deep_succession_flags_reversed_order_as_violation():
    seqs = [[{"realized_motif_code": "face_slap"}, {"realized_motif_code": "humiliation"}]]
    out = build_deep_report(sequences=seqs, chapter_index_by_id={}, planned_by_index={},
                            precedes_code_pairs={("humiliation", "face_slap")})
    s = out["succession"]
    assert s["legal"] == 0
    assert s["violations"] == [{"from_motif_code": "face_slap", "to_motif_code": "humiliation"}]


def test_deep_succession_collapses_consecutive_duplicates():
    seqs = [[{"realized_motif_code": "a"}, {"realized_motif_code": "a"},
             {"realized_motif_code": "b"}]]
    out = build_deep_report(sequences=seqs, chapter_index_by_id={}, planned_by_index={},
                            precedes_code_pairs={("a", "b")})
    assert out["succession"]["transitions"] == 1 and out["succession"]["legal"] == 1


def test_deep_succession_unavailable_without_motif_tags():
    seqs = [[{"thread": "a", "tension": 3}]]  # no realized_motif_code
    out = build_deep_report(sequences=seqs, chapter_index_by_id={"a": 1}, planned_by_index={})
    assert out["succession"]["available"] is False
    assert "tag-motifs" in out["succession"]["reason"]


def test_route_deep_with_model_ref_also_tags_motifs_and_reports_succession(client):
    c, state = client
    aid = uuid.uuid4()
    state.arc = _arc(layout=[_placement("humiliation"), _placement("face_slap")],
                     threads=[{"key": "revenge", "label": "Revenge"}])
    state.arc.id = aid
    ch1 = uuid.uuid4()
    state.rows = [{"motif_id": M_HUMIL, "motif_code": "humiliation",
                   "annotations": {"thread": "revenge", "arc_template_id": str(aid)},
                   "chapter_id": ch1, "tension": 50, "story_order": 1}]
    # placement motifs resolve (code→Motif) + the precedes graph over their ids.
    mh = SimpleNamespace(id=M_HUMIL, code="humiliation", name="Humiliation", summary="A public shaming.")
    mf = SimpleNamespace(id=M_SLAP, code="face_slap", name="Face Slap", summary="The retort.")
    state.placement_motifs = {"humiliation": mh, "face_slap": mf}
    state.succ_map = {M_HUMIL: [{"id": M_SLAP, "code": "face_slap", "name": "Face Slap", "ord": 0}]}
    state.sequences = [[{"realized_motif_code": "humiliation", "thread": str(ch1)},
                        {"realized_motif_code": "face_slap", "thread": str(ch1)}]]
    r = c.get(f"/v1/composition/works/{P}/conformance?scope=arc&arc_template_id={aid}"
              f"&deep=true&model_ref=m1&model_source=user_model")
    assert r.status_code == 200
    # the motif vocab (code+name+summary) was sent to tag-motifs.
    assert state.motif_tag_calls and {m["code"] for m in state.motif_tag_calls[0]["motifs"]} == {"humiliation", "face_slap"}
    s = r.json()["deep"]["succession"]
    assert s["available"] is True and s["legal"] == 1 and s["violations"] == []


def test_deep_thread_progression_unavailable_without_tags():
    seqs = [[{"beat": "x", "thread": "a", "tension": 3}]]  # no narrative_thread
    out = build_deep_report(sequences=seqs, chapter_index_by_id={"a": 1}, planned_by_index={},
                            arc_threads=[{"key": "combat", "label": "Combat"}])
    assert out["thread_progression"]["available"] is False
    assert "tag-threads" in out["thread_progression"]["reason"]


def test_route_deep_with_model_ref_tags_threads_then_reports_progression(client):
    c, state = client
    aid = uuid.uuid4()
    state.arc = _arc(layout=[_placement("humiliation")],
                     threads=[{"key": "revenge", "label": "Revenge"}])
    state.arc.id = aid
    ch1 = uuid.uuid4()
    state.rows = [{"motif_id": M_HUMIL, "motif_code": "humiliation",
                   "annotations": {"thread": "revenge", "arc_template_id": str(aid)},
                   "chapter_id": ch1, "tension": 50, "story_order": 1}]
    state.sequences = [[{"beat": "slap", "thread": str(ch1),
                         "narrative_thread": "revenge", "tension": 5}]]
    r = c.get(f"/v1/composition/works/{P}/conformance?scope=arc&arc_template_id={aid}"
              f"&deep=true&model_ref=m1&model_source=user_model")
    assert r.status_code == 200
    # the model_ref opt-in triggered a tag-threads call with the arc's vocabulary.
    assert state.tag_calls and state.tag_calls[0]["threads"] == [{"key": "revenge", "label": "Revenge"}]
    tp = r.json()["deep"]["thread_progression"]
    assert tp["available"] is True
    assert {r["thread"]: r["realized"] for r in tp["threads"]} == {"revenge": True}
