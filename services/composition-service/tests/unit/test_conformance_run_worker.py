"""D-W10-ARC-CONFORMANCE-DEEP-JOB — the Tier-W arc-conformance worker handler.

``run_conformance_run`` is the production home of the deep arc overlay (the synchronous
GET deep+model_ref tagging storm times out on a real book). These drive it with fakes for
the repos/reader/knowledge so the REAL ``compute_arc_report`` runs end-to-end:

  - scope='arc' + model_ref → tags (threads+motifs+causal) then builds coarse + deep overlay
  - scope='arc' without model_ref → pacing-only deep (no tagging storm)
  - the terminal-business-error guards (chapter scope, missing arc id, foreign arc)

Plus the envelope threading: the confirm effect carries arc_template_id/model_ref/model_source.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.engine import motif_conformance_run as mcr

U, P, BOOK, AID = str(uuid.uuid4()), str(uuid.uuid4()), uuid.uuid4(), uuid.uuid4()
MH, MS = str(uuid.uuid4()), str(uuid.uuid4())


def _arc():
    return SimpleNamespace(
        id=AID, name="Revenge", threads=[{"key": "revenge", "label": "Revenge"}],
        layout=[{"motif_code": "humiliation", "thread": "revenge", "ord": 0},
                {"motif_code": "face_slap", "thread": "revenge", "ord": 1}], pacing=[])


@pytest.fixture
def patched(monkeypatch):
    state = SimpleNamespace(
        arc=_arc(), rows=[], sequences=[], placement_motifs={}, succ_map={},
        causal_pairs=[], tag_calls=[], motif_tag_calls=[], causal_calls=[])

    class _Works:
        def __init__(self, pool): pass
        async def get(self, u, p):
            return SimpleNamespace(book_id=BOOK, project_id=p, user_id=u)

    class _ArcRepo:
        def __init__(self, pool): pass
        async def get_visible(self, caller, aid):
            return state.arc

    class _Reader:
        def __init__(self, pool): pass
        async def arc_bindings(self, u, p, aid):
            return state.rows

    class _MotifRepo:
        def __init__(self, pool): pass
        async def successors_by_ids(self, ids):
            return state.succ_map
        async def get_by_codes(self, caller, codes):
            return state.placement_motifs

    class _Knowledge:
        async def get_motif_beat_sequences(self, u, *, book_id=None, corpus=False, language=None):
            return state.sequences
        async def tag_threads(self, u, *, book_id, threads, model_source, model_ref):
            state.tag_calls.append(model_ref); return {}
        async def tag_motifs(self, u, *, book_id, motifs, model_source, model_ref):
            state.motif_tag_calls.append([m["code"] for m in motifs]); return {}
        async def infer_causal_edges(self, u, *, book_id, model_source, model_ref):
            state.causal_calls.append(model_ref); return {}
        async def causal_motif_pairs(self, u, *, book_id):
            return state.causal_pairs

    monkeypatch.setattr("app.db.repositories.works.WorksRepo", _Works)
    monkeypatch.setattr("app.db.repositories.arc_template_repo.ArcTemplateRepo", _ArcRepo)
    monkeypatch.setattr("app.db.repositories.motif_repo.MotifRepo", _MotifRepo)
    monkeypatch.setattr("app.routers.conformance.ConformanceTraceReader", _Reader)
    state.knowledge = _Knowledge()
    return state


def _arc_input(**over):
    base = {"worker_op": "conformance_run", "book_id": str(BOOK), "scope": "arc",
            "arc_template_id": str(AID), "model_ref": "m1", "model_source": "user_model"}
    base.update(over)
    return base


async def _run(state, inp):
    return await mcr.run_conformance_run(
        object(), object(), state.knowledge, user_id=U, project_id=P, input=inp)


# ── happy path: deep overlay with tagging ─────────────────────────────────────────

async def test_arc_deep_job_tags_then_builds_coarse_and_deep(patched):
    state = patched
    ch1 = uuid.uuid4()
    state.rows = [{"motif_id": MH, "motif_code": "humiliation",
                   "annotations": {"thread": "revenge", "arc_template_id": str(AID)},
                   "chapter_id": ch1, "tension": 50, "story_order": 1}]
    state.placement_motifs = {
        "humiliation": SimpleNamespace(id=MH, code="humiliation", name="Humiliation", summary="x"),
        "face_slap": SimpleNamespace(id=MS, code="face_slap", name="Face Slap", summary="y")}
    state.succ_map = {MH: [{"id": MS, "code": "face_slap", "name": "Face Slap", "ord": 0}]}
    state.sequences = [[{"realized_motif_code": "humiliation", "thread": str(ch1)},
                        {"realized_motif_code": "face_slap", "thread": str(ch1)}]]
    state.causal_pairs = [("humiliation", "face_slap")]

    out = await _run(state, _arc_input())
    # coarse report shape (job result the poll returns)
    assert out["scope"] == "arc" and out["coarse"] is True and out["chapter_count"] == 1
    # the model_ref drove all three tagging passes (the storm — now off the GET).
    assert state.tag_calls == ["m1"] and state.causal_calls == ["m1"]
    assert {c for codes in state.motif_tag_calls for c in codes} == {"humiliation", "face_slap"}
    # deep overlay: a legal, causally-verified succession.
    s = out["deep"]["succession"]
    assert s["legal"] == 1 and s["caused"] == 1 and s["causal_verified"] is True


async def test_arc_job_without_model_ref_is_pacing_only_no_tagging(patched):
    state = patched
    ch1 = uuid.uuid4()
    state.rows = [{"motif_id": MH, "motif_code": "humiliation",
                   "annotations": {"thread": "revenge", "arc_template_id": str(AID)},
                   "chapter_id": ch1, "tension": 40, "story_order": 1}]
    state.sequences = [[{"beat": "x", "thread": str(ch1), "tension": 5}]]
    out = await _run(state, _arc_input(model_ref=None, model_source=None))
    assert state.tag_calls == [] and state.motif_tag_calls == [] and state.causal_calls == []
    assert out["deep"]["available"] is True              # pacing still computed from pre-existing beats
    assert out["deep"]["pacing"]["realized"][0]["avg_tension"] == 100.0


# ── terminal business-error guards (clean job-failed, no redeliver) ───────────────

async def test_chapter_scope_is_terminal_valueerror(patched):
    with pytest.raises(ValueError, match="scope='arc' only"):
        await _run(patched, {"scope": "chapter", "chapter_id": str(uuid.uuid4())})


async def test_missing_arc_template_id_is_terminal_valueerror(patched):
    with pytest.raises(ValueError, match="arc_template_id"):
        await _run(patched, _arc_input(arc_template_id=None))


async def test_foreign_or_missing_arc_is_terminal_valueerror(patched):
    patched.arc = None  # get_visible → None
    with pytest.raises(ValueError, match="not visible"):
        await _run(patched, _arc_input())


# ── envelope threading: the confirm effect carries the deep inputs ────────────────

async def test_confirm_effect_spec_carries_deep_inputs(monkeypatch):
    from app.routers import actions

    seen = {}

    async def _fake_enqueue(*, envelope_user, project_id, operation, spec):
        seen["spec"] = spec
        seen["operation"] = operation
        return uuid.uuid4()

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(actions, "_enqueue_motif_job", _fake_enqueue)
    monkeypatch.setattr(actions, "_claim_or_replay", _noop)
    monkeypatch.setattr(actions, "_precheck_or_402", _noop)

    work = SimpleNamespace(book_id=BOOK)
    payload = {"scope": "arc", "chapter_id": None, "arc_template_id": str(AID),
               "model_ref": "m1", "model_source": "user_model", "estimate_usd": 0.0}
    out = await actions._execute_conformance_run(
        payload, uuid.UUID(P), work, uuid.uuid4(), token="t.t.t", claims=None)

    assert out["outcome"] == "action_accepted" and seen["operation"] == "conformance_run"
    assert seen["spec"]["arc_template_id"] == str(AID)
    assert seen["spec"]["model_ref"] == "m1" and seen["spec"]["model_source"] == "user_model"


# ── MCP arg model accepts the deep fields (ForbidExtra still rejects unknowns) ────

def test_conformance_run_args_accept_deep_fields():
    from app.mcp.server import _ConformanceRunArgs

    a = _ConformanceRunArgs(project_id=P, scope="arc", arc_template_id=str(AID),
                            model_ref="m1", model_source="user_model")
    assert a.arc_template_id == str(AID) and a.model_ref == "m1"
    with pytest.raises(Exception):  # ForbidExtra
        _ConformanceRunArgs(project_id=P, scope="arc", bogus="x")
