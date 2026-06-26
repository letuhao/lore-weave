"""W2 — motif planner select + bind/swap/undo (unit; FakeRetriever mock).

RED-first guards (W2 doc §7). The real MotifRetriever raises NotImplementedError
in F0, so every test here mocks it with a `FakeRetriever` returning a scripted
list[MotifCandidate] (or [], or raising MotifRetrieverError) — the four behaviors
the W3 contract (F0 §3.3) guarantees. W2 ships + is gated entirely against this
fake; the real W3 impl is swapped in at R-NODE-P1 on a live stack-up.

Covered:
  §7.1 core select/bind/scenes
  §7.2 the F1 fallback matrix (one test per cell)
  §7.3 tension reconcile (R3)
  §7.5 reproducibility tie-break + status guard
  §7.6 B1 coverage telemetry + anti-repetition
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.db.models import Motif, MotifCandidate
from app.engine.adaptive_k import motif_tension_to_scale
from app.engine.motif_select import (
    HIGH_WEIGHT_BEATS,
    MotifRetrieverError,
    SelectedMotif,
    bind_motif,
    build_application_rows,
    estimate_diverge_budget,
    scenes_from_motif,
    select_motif_for_chapter,
    _pick_top1,
)
from app.engine.plan import ChapterPlan, ChapterScenes, ScenePlan


# ── fixtures ────────────────────────────────────────────────────────────

def _motif(
    *, code="m.bait_and_switch", name="Bait and switch", language="en",
    roles=None, beats=None, effects=None, tension_target=4,
    status="active", mining_support=None, judge_score=None,
    info_asymmetry=None, annotations=None,
) -> Motif:
    return Motif.model_validate({
        "id": uuid.uuid4(),
        "owner_user_id": None,
        "code": code,
        "language": language,
        "visibility": "unlisted",
        "kind": "scheme",
        "name": name,
        "summary": "a schemer baits a mark with a false promise then reverses",
        "genre_tags": ["xianxia", "cultivation"],
        "roles": roles if roles is not None else [
            {"key": "schemer", "actant": "subject", "label": "Schemer",
             "constraints": ["antagonist"]},
            {"key": "mark", "actant": "object", "label": "Mark", "constraints": []},
        ],
        "beats": beats if beats is not None else [
            {"key": "bait", "label": "The bait", "intent": "{schemer} offers {mark} a tempting deal",
             "tension_target": 2, "order": 1},
            {"key": "switch", "label": "The switch", "intent": "{schemer} betrays {mark}",
             "tension_target": 5, "order": 2},
        ],
        "preconditions": [],
        "effects": effects if effects is not None else [{"text": "trust_broken"}],
        "info_asymmetry": info_asymmetry,
        "annotations": annotations or {},
        "tension_target": tension_target,
        "status": status,
        "mining_support": mining_support,
        "judge_score": judge_score,
        "version": 3,
    })


def _candidate(motif: Motif, score: float, match_reason: dict | None = None) -> MotifCandidate:
    return MotifCandidate(
        motif=motif, score=score,
        match_reason=match_reason or {"tension": 0.9, "genre": 1.0, "precond": 1.0, "cosine": score},
    )


class FakeRetriever:
    """Scripts retrieve(): returns a fixed list, or [], or raises. Records the
    kwargs of the LAST call so the contract test can assert the frozen call shape
    and the gate tests can assert it was (not) called."""

    def __init__(self, result: list[MotifCandidate] | None = None, *, raises: bool = False):
        self._result = result if result is not None else []
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    async def retrieve(self, caller_id, **kwargs) -> list[MotifCandidate]:
        self.calls.append({"caller_id": caller_id, **kwargs})
        if self._raises:
            raise MotifRetrieverError("boom")
        return list(self._result)


def _chapter(beat_role="switch", intent="the betrayal lands") -> ChapterPlan:
    return ChapterPlan(chapter_id=str(uuid.uuid4()), title="Ch", sort_order=0,
                       beat_role=beat_role, intent=intent)


_CAST = {"lin": "ent-lin", "the sect elder": "ent-elder", "mark": "ent-mark"}


def _sel(motif: Motif, score=0.9) -> SelectedMotif:
    return SelectedMotif(motif=motif, score=score,
                         match_reason={"tension": 0.9, "genre": 1.0, "precond": 1.0, "cosine": score})


_COMMON = dict(
    book_id=uuid.uuid4(), project_id=uuid.uuid4(), caller_id=uuid.uuid4(),
    genre_tags=["xianxia"], language="en", prev_effects=[],
    min_score=0.30, high_threshold=70,
)


# ── §7.3 tension reconcile ──────────────────────────────────────────────

@pytest.mark.parametrize("tens5,expected", [(5, 90), (4, 75), (3, 50), (2, 30), (1, 10)])
def test_motif_tension_map(tens5, expected):
    assert motif_tension_to_scale(tens5) == expected


def test_motif_tension_fallback_and_none():
    assert motif_tension_to_scale(None, fallback=4) == 75
    assert motif_tension_to_scale(None, fallback=None) is None
    assert motif_tension_to_scale(None) is None
    # bool must NOT read as 1/0
    assert motif_tension_to_scale(True) is None
    assert motif_tension_to_scale(False) is None
    # out of range clamps
    assert motif_tension_to_scale(9) == 90
    assert motif_tension_to_scale(0) == 10


# ── §7.1 core select / bind / scenes ────────────────────────────────────

async def test_select_returns_top1_match():
    m = _motif()
    r = FakeRetriever([_candidate(m, 0.8)])
    sel = await select_motif_for_chapter(_chapter(), r, **_COMMON)
    assert sel is not None
    assert sel.motif.id == m.id
    assert sel.match_reason["cosine"] == 0.8


async def test_select_picks_highest_score():
    lo, hi = _motif(code="lo"), _motif(code="hi")
    r = FakeRetriever([_candidate(hi, 0.91), _candidate(lo, 0.5)])
    sel = await select_motif_for_chapter(_chapter(), r, **_COMMON)
    assert sel.motif.code == "hi"


async def test_select_calls_retrieve_with_frozen_kwargs():
    """Contract: the call site matches the F0-frozen retrieve() signature exactly."""
    r = FakeRetriever([_candidate(_motif(), 0.8)])
    await select_motif_for_chapter(_chapter(beat_role="switch"), r, **_COMMON)
    call = r.calls[-1]
    assert call["caller_id"] == _COMMON["caller_id"]
    for k in ("book_id", "project_id", "genre_tags", "language", "beat_role",
              "tension", "prev_effects"):
        assert k in call, f"missing frozen kwarg {k}"
    assert call["beat_role"] == "switch"


def test_bind_resolves_roles_via_cast():
    m = _motif()
    binding = bind_motif(_sel(m), _CAST, _chapter())
    # schemer label "Schemer" → no cast match; mark label "Mark" → ent-mark
    assert binding.role_bindings.get("mark") == "ent-mark"
    assert "schemer" in binding.unresolved_roles
    assert binding.warning == "partial_role_bind"


def test_bind_full_when_all_roles_resolve():
    m = _motif(roles=[
        {"key": "hero", "actant": "subject", "label": "Lin", "constraints": []},
        {"key": "foe", "actant": "opponent", "label": "The Sect Elder", "constraints": []},
    ])
    binding = bind_motif(_sel(m), _CAST, _chapter())
    assert binding.role_bindings == {"hero": "ent-lin", "foe": "ent-elder"}
    assert binding.unresolved_roles == []
    assert binding.warning is None


def test_scenes_from_motif_one_per_beat_ordered():
    m = _motif()
    binding = bind_motif(_sel(m), _CAST, _chapter())
    scenes = scenes_from_motif(_sel(m), binding, _chapter(), k_ceiling=3,
                               high_threshold=70, min_scenes=1, max_scenes=6)
    assert [s.title for s in scenes] == ["The bait", "The switch"]
    # ordered by beat order; tension reconciled 1..5 → 0..100
    assert scenes[0].tension == 30   # bait tension_target=2 → 30
    assert scenes[1].tension == 90   # switch tension_target=5 → 90


def test_scenes_from_motif_clamps_to_max():
    beats = [{"key": f"b{i}", "label": f"B{i}", "intent": "x", "tension_target": 3, "order": i}
             for i in range(10)]
    m = _motif(beats=beats)
    binding = bind_motif(_sel(m), _CAST, _chapter())
    scenes = scenes_from_motif(_sel(m), binding, _chapter(), k_ceiling=3,
                               high_threshold=70, min_scenes=1, max_scenes=4)
    assert len(scenes) == 4


def test_scenes_from_motif_underfill_not_padded():
    m = _motif(beats=[{"key": "only", "label": "Only", "intent": "x", "tension_target": 3, "order": 1}])
    binding = bind_motif(_sel(m), _CAST, _chapter())
    scenes = scenes_from_motif(_sel(m), binding, _chapter(), k_ceiling=3,
                               high_threshold=70, min_scenes=3, max_scenes=6)
    assert len(scenes) == 1  # NOT padded to min_scenes


def test_render_beat_synopsis_substitutes_bound_names():
    m = _motif(
        roles=[{"key": "hero", "actant": "subject", "label": "Lin", "constraints": []},
               {"key": "foe", "actant": "opponent", "label": "The Sect Elder", "constraints": []}],
        beats=[{"key": "x", "label": "Clash", "intent": "{hero} confronts {foe}",
                "tension_target": 4, "order": 1}],
    )
    binding = bind_motif(_sel(m), _CAST, _chapter())
    scenes = scenes_from_motif(_sel(m), binding, _chapter(), k_ceiling=3,
                               high_threshold=70, min_scenes=1, max_scenes=6)
    # role keys replaced with the bound cast member's LABEL
    assert "Lin" in scenes[0].synopsis
    assert "The Sect Elder" in scenes[0].synopsis
    assert "{hero}" not in scenes[0].synopsis


def test_render_beat_synopsis_leaves_unbound_keys_abstract():
    m = _motif(beats=[{"key": "x", "label": "Bait", "intent": "{schemer} fools {mark}",
                       "tension_target": 2, "order": 1}])
    binding = bind_motif(_sel(m), _CAST, _chapter())  # schemer unbound, mark bound
    scenes = scenes_from_motif(_sel(m), binding, _chapter(), k_ceiling=3,
                               high_threshold=70, min_scenes=1, max_scenes=6)
    # unbound 'schemer' falls back to the role label; 'mark' → bound name
    assert "Schemer" in scenes[0].synopsis or "schemer" in scenes[0].synopsis


def test_build_application_rows_pins_version_and_beat_key():
    m = _motif()
    sel = _sel(m)
    binding = bind_motif(sel, _CAST, _chapter())
    scenes = scenes_from_motif(sel, binding, _chapter(), k_ceiling=3,
                               high_threshold=70, min_scenes=1, max_scenes=6)
    rows = build_application_rows(sel, binding, scenes)
    assert len(rows) == len(scenes)
    for row, beat in zip(rows, m.beats):
        assert row["motif_id"] == str(m.id)
        assert row["motif_version"] == m.version
        assert row["role_bindings"] == binding.role_bindings
        # W5 trace: beat_key folded into annotations (no F0 schema column needed)
        assert row["annotations"]["beat_key"] == beat["key"]


# ── §7.2 the F1 fallback matrix ─────────────────────────────────────────

async def test_fallback_empty_retrieve():
    r = FakeRetriever([])
    assert await select_motif_for_chapter(_chapter(), r, **_COMMON) is None


async def test_fallback_retrieve_errored():
    r = FakeRetriever(raises=True)
    assert await select_motif_for_chapter(_chapter(), r, **_COMMON) is None


async def test_fallback_below_floor():
    r = FakeRetriever([_candidate(_motif(), 0.10)])  # below min_score 0.30
    assert await select_motif_for_chapter(_chapter(), r, **_COMMON) is None


async def test_partial_bind_is_not_fallback():
    """A partial bind still binds (not a fallback); unresolved roles surfaced."""
    r = FakeRetriever([_candidate(_motif(), 0.8)])  # schemer unbound by _CAST
    sel = await select_motif_for_chapter(_chapter(), r, **_COMMON)
    assert sel is not None
    binding = bind_motif(sel, _CAST, _chapter())
    assert binding.warning == "partial_role_bind"
    assert "schemer" in binding.unresolved_roles


async def test_connective_beat_high_floor_drops_weak_candidate():
    # a connective (non-high-weight) beat demands a higher bar than min_score
    r = FakeRetriever([_candidate(_motif(), 0.33)])  # just over min_score, under connective floor
    common = {**_COMMON, "connective_floor_margin": 0.08}
    sel = await select_motif_for_chapter(_chapter(beat_role="setup"), r, **common)
    assert sel is None


async def test_connective_beat_binds_strong_candidate():
    r = FakeRetriever([_candidate(_motif(), 0.9)])
    common = {**_COMMON, "connective_floor_margin": 0.08}
    sel = await select_motif_for_chapter(_chapter(beat_role="setup"), r, **common)
    assert sel is not None


async def test_high_weight_beat_uses_min_score_floor():
    # a high-weight beat ('switch' ∈ HIGH_WEIGHT_BEATS? no — use 'climax') binds at min_score
    assert "climax" in HIGH_WEIGHT_BEATS
    r = FakeRetriever([_candidate(_motif(), 0.31)])  # just over min_score
    common = {**_COMMON, "connective_floor_margin": 0.50}  # high margin would block a connective beat
    sel = await select_motif_for_chapter(_chapter(beat_role="climax"), r, **common)
    assert sel is not None  # high-weight beat ignores the connective margin


# ── §7.5 reproducibility tie-break + status guard ───────────────────────

def test_pick_top1_total_order_by_code():
    m1 = _motif(code="zzz")
    m2 = _motif(code="aaa")
    cands = [_candidate(m1, 0.9), _candidate(m2, 0.9)]  # tied score
    # tie broken by code asc → aaa wins, deterministically across repeated calls
    assert _pick_top1(cands).motif.code == "aaa"
    assert _pick_top1(list(reversed(cands))).motif.code == "aaa"


def test_pick_top1_prefers_mining_support_then_judge():
    base = _motif(code="aaa", mining_support=1, judge_score=0.5)
    more_support = _motif(code="bbb", mining_support=10, judge_score=0.5)
    cands = [_candidate(base, 0.9), _candidate(more_support, 0.9)]
    assert _pick_top1(cands).motif.code == "bbb"  # higher mining_support wins


async def test_draft_status_never_bound():
    """Defense-in-depth over W3's SQL status filter: a draft candidate is dropped."""
    active = _motif(code="active", status="active")
    draft = _motif(code="draft", status="draft")
    r = FakeRetriever([_candidate(draft, 0.99), _candidate(active, 0.4)])
    sel = await select_motif_for_chapter(_chapter(), r, **_COMMON)
    assert sel is not None
    assert sel.motif.code == "active"   # the higher-scored draft is skipped


# ── §7.6 coverage telemetry + anti-repetition ───────────────────────────

async def test_anti_repetition_deprioritizes_over_cap():
    """A motif already applied >= max_reapply times in the book drops below floor."""
    m = _motif()
    r = FakeRetriever([_candidate(m, 0.9)])
    common = {**_COMMON, "applied_counts": {str(m.id): 3}, "max_reapply": 3}
    sel = await select_motif_for_chapter(_chapter(), r, **common)
    assert sel is None  # over the cap → not bound


async def test_anti_repetition_allows_under_cap():
    m = _motif()
    r = FakeRetriever([_candidate(m, 0.9)])
    common = {**_COMMON, "applied_counts": {str(m.id): 2}, "max_reapply": 3}
    sel = await select_motif_for_chapter(_chapter(), r, **common)
    assert sel is not None


def test_estimate_diverge_budget_splits_bound_invent():
    bound = ChapterScenes(
        chapter=_chapter(), scenes=[ScenePlan("t", "s", 90, [], [], 3)],
        motif=_sel(_motif()),
    )
    invent = ChapterScenes(
        chapter=_chapter(beat_role=None), scenes=[ScenePlan("t", "s", 50, [], [], 2),
                                                  ScenePlan("t2", "s2", 10, [], [], 1)],
    )
    agg = estimate_diverge_budget([bound, invent])
    assert agg["bound_k"] == 3
    assert agg["invent_k"] == 3
    assert agg["total_k"] == 6
    assert agg["scene_count"] == 3


# ── T4: the L2 splice in decompose() — the full F1 matrix + coverage ────

import json as _json
from types import SimpleNamespace

from app.engine import plan as _plan


class _FakeLLM:
    """L1 maps every chapter to its beat_role hint via the chapter title; L2 emits a
    fixed 2-scene invent payload. (Mirrors test_plan.FakeLLM routing.)"""

    def __init__(self, *, l1: str | None, l2: str | None):
        self._l1, self._l2 = l1, l2
        self.l2_calls = 0

    async def submit_and_wait(self, **kw):
        user = kw["input"]["messages"][1]["content"]
        if "STRUCTURE BEATS" in user:
            res = {"messages": [{"content": self._l1}]} if self._l1 is not None else {}
            return SimpleNamespace(status="completed", result=res)
        self.l2_calls += 1
        res = {"messages": [{"content": self._l2}]} if self._l2 is not None else {}
        return SimpleNamespace(status="completed", result=res)


_BEATS = [{"key": "climax", "purpose": "payoff"}]
_L1 = _json.dumps({"chapters": [{"index": 1, "beat": "climax", "intent": "the end"}],
                   "unmapped_beats": []})
_L2 = _json.dumps({"scenes": [{"title": "A", "intent": "stuff happens", "tension": 60, "present": []}]})

_DECOMPOSE_KW = dict(
    user_id=str(uuid.uuid4()), model_source="local", model_ref="m",
    premise="p", arc_title="Arc", beats=_BEATS,
    cast=[{"entity_id": "ent-mark", "name": "Mark"}],
    k_ceiling=3, high_threshold=70, min_scenes=1, max_scenes=6,
    source_language="en",
)


def _one_chapter():
    return [ChapterPlan(chapter_id=str(uuid.uuid4()), title="Ch1", sort_order=0,
                        beat_role=None, intent="")]


async def test_decompose_motifs_off_is_verbatim_invent():
    """Back-compat: motifs disabled ⇒ the invent path runs, no motif fields set."""
    llm = _FakeLLM(l1=_L1, l2=_L2)
    res = await _plan.decompose(llm, chapters=_one_chapter(), **_DECOMPOSE_KW)
    assert res.motif_coverage == {}
    assert all(cs.motif is None for cs in res.chapters)
    assert llm.l2_calls == 1  # invented


async def test_decompose_mapped_match_binds_no_llm():
    """A mapped beat with a matching candidate binds from beats — NO L2 LLM call."""
    llm = _FakeLLM(l1=_L1, l2=_L2)
    r = FakeRetriever([_candidate(_motif(), 0.9)])
    res = await _plan.decompose(
        llm, chapters=_one_chapter(), motifs_enabled=True, retriever=r,
        book_id=uuid.uuid4(), project_id=uuid.uuid4(), genre_tags=["xianxia"],
        motif_min_score=0.30, **_DECOMPOSE_KW,
    )
    assert llm.l2_calls == 0  # bound path is LLM-free
    cs = res.chapters[0]
    assert cs.motif is not None
    assert cs.application_rows  # motif_application payloads built
    assert res.motif_coverage["bound_chapters"] == 1
    assert res.motif_coverage["mapped_chapters"] == 1


async def test_decompose_mapped_empty_falls_back_to_invent():
    llm = _FakeLLM(l1=_L1, l2=_L2)
    r = FakeRetriever([])  # empty
    res = await _plan.decompose(
        llm, chapters=_one_chapter(), motifs_enabled=True, retriever=r,
        book_id=uuid.uuid4(), project_id=uuid.uuid4(), genre_tags=["xianxia"],
        **_DECOMPOSE_KW,
    )
    assert llm.l2_calls == 1  # invented
    cs = res.chapters[0]
    assert cs.motif is None
    assert cs.warning == "no_motif_match"
    assert res.motif_coverage["fallbacks"].get("no_motif_match") == 1


async def test_decompose_mapped_errored_falls_back():
    llm = _FakeLLM(l1=_L1, l2=_L2)
    r = FakeRetriever(raises=True)
    res = await _plan.decompose(
        llm, chapters=_one_chapter(), motifs_enabled=True, retriever=r,
        book_id=uuid.uuid4(), project_id=uuid.uuid4(), genre_tags=["xianxia"],
        **_DECOMPOSE_KW,
    )
    assert llm.l2_calls == 1
    assert res.chapters[0].motif is None
    assert res.chapters[0].warning == "no_motif_match"  # retrieve None → fallback


async def test_decompose_intra_run_anti_repetition():
    """The same top motif can't carpet a single decompose: with max_reapply=1 and the
    same motif as top candidate for 3 mapped chapters, at most 1 chapter binds it; the
    rest fall back to invent (the DB count alone is stale mid-run)."""
    chapters = [ChapterPlan(chapter_id=str(uuid.uuid4()), title=f"C{i}", sort_order=i,
                            beat_role=None, intent="") for i in range(3)]
    l1 = _json.dumps({"chapters": [
        {"index": 1, "beat": "climax", "intent": "x"},
        {"index": 2, "beat": "climax", "intent": "y"},
        {"index": 3, "beat": "climax", "intent": "z"},
    ], "unmapped_beats": []})
    llm = _FakeLLM(l1=l1, l2=_L2)
    m = _motif()
    r = FakeRetriever([_candidate(m, 0.95)])  # always the same top motif
    res = await _plan.decompose(
        llm, chapters=chapters, motifs_enabled=True, retriever=r,
        book_id=uuid.uuid4(), project_id=uuid.uuid4(), genre_tags=["xianxia"],
        motif_min_score=0.30, motif_max_reapply=1, **{k: v for k, v in _DECOMPOSE_KW.items() if k != "beats"},
        beats=[{"key": "climax", "purpose": "payoff"}],
    )
    bound = sum(1 for cs in res.chapters if cs.motif is not None)
    assert bound == 1  # capped at max_reapply within the run
    assert res.motif_coverage["fallbacks"].get("no_motif_match") == 2


async def test_decompose_degraded_l1_never_retrieves():
    """L1 degraded (beat_role=None for all) ⇒ selection is GATED off → retrieve never
    called → straight to invent (the structurally-impossible degraded×candidates
    cell, W2 §2.4)."""
    llm = _FakeLLM(l1=None, l2=_L2)  # L1 returns nothing → beat_role stays None
    r = FakeRetriever([_candidate(_motif(), 0.99)])
    res = await _plan.decompose(
        llm, chapters=_one_chapter(), motifs_enabled=True, retriever=r,
        book_id=uuid.uuid4(), project_id=uuid.uuid4(), genre_tags=["xianxia"],
        **_DECOMPOSE_KW,
    )
    assert r.calls == []  # retrieve never called without a beat_role
    assert res.chapters[0].motif is None
    assert llm.l2_calls == 1
