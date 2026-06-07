"""B1 chapter-assembly-mode plumbing tests.

Covers the pure resolver (precedence + defense-in-depth fallback), the WorkPatch
settings enum validator (422 on a bad stored value), and the /generate wiring
(501 on the not-yet-implemented 'chapter' mode + echo of the resolved mode).
"""

from __future__ import annotations

import pydantic
import pytest

from app.engine.assembly import ASSEMBLY_MODES, resolve_assembly_mode
from app.routers.works import WorkPatch

# Reuse the engine-router TestClient fixture + ids (pack/stream/judge stubbed).
from tests.unit.test_engine_router import PROJECT, NODE, DRAFTER, ctx  # noqa: F401


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


def test_generate_chapter_mode_override_501(ctx):
    # The request override resolves to 'chapter' → 501 (B2 not built), before any job.
    c, _, _, _, jobs, _, _ = ctx
    r = c.post(f"/v1/composition/works/{PROJECT}/generate",
               json={**_gen_body(), "assembly_mode": "chapter"})
    assert r.status_code == 501
    assert r.json()["detail"]["code"] == "ASSEMBLY_MODE_NOT_IMPLEMENTED"
    # guarded BEFORE job creation — assert jobs.create was never reached (the
    # StubJobs records its kwargs on _last_create only when create() runs). An
    # empty jobs.updates alone would NOT prove this (create precedes the first
    # update_status), so check the create sentinel directly. (/review-impl COSMETIC-1)
    assert not hasattr(jobs, "_last_create")
    assert jobs.updates == []


def test_generate_chapter_mode_from_work_setting_501(ctx):
    # No override, but the work setting selects 'chapter' → 501.
    c, works, _, _, _, _, _ = ctx
    works.work.settings = {"assembly_mode": "chapter"}
    r = c.post(f"/v1/composition/works/{PROJECT}/generate", json=_gen_body())
    assert r.status_code == 501


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
