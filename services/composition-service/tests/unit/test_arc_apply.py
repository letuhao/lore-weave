"""W10 — arc_apply pure placement-rescale unit tests (no DB, no LLM).

apply = decompose at arc scale (§12.5). These prove the deterministic MATH:
  - R2.5 proportional placement-rescale: span_start/span_end scale into the target
    range, endpoints preserved, monotonic, clamped to [1..target].
  - roster-bind-ONCE (§12.5): a roster role is bound once and propagated to EVERY
    placement's role_bindings; unbound roster slots are surfaced (never silently
    half-bound).
  - drop/merge NEVER silent (§12.6): when the target is smaller than the source
    span and two same-thread placements collapse onto the same chapters, the
    folded one lands in the drop_merge_report — it is never silently dropped.

The deep planner materialization (outline_node rows / LLM) is OUT of scope here —
arc_apply is a pure function over the template JSONB (see app/engine/arc_apply.py).
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import ArcApplyArgs, ArcTemplate
from app.engine.arc_apply import _rescale_span, build_apply_plan


def _arc(**kw) -> ArcTemplate:
    base = dict(
        id=kw.pop("id", uuid.uuid4()),
        owner_user_id=kw.pop("owner_user_id", uuid.uuid4()),
        code=kw.pop("code", "arc.three-year-pact"),
        name=kw.pop("name", "Three-Year Pact"),
        chapter_span=kw.pop("chapter_span", 30),
        threads=kw.pop("threads", [{"key": "combat", "label": "Combat"},
                                   {"key": "cultivation", "label": "Cultivation"}]),
        layout=kw.pop("layout", []),
        arc_roster=kw.pop("arc_roster", []),
    )
    base.update(kw)
    return ArcTemplate(**base)


def _placement(code, thread, start, end, ord=0, **kw):
    p = dict(motif_code=code, thread=thread, span_start=start, span_end=end, ord=ord)
    p.update(kw)
    return p


# ── _rescale_span: the R2.5 proportional core ────────────────────────────────────
def test_rescale_identity_when_source_equals_target():
    # source span == target → placement spans are unchanged.
    assert _rescale_span(1, 5, source_span=30, target=30) == (1, 5)
    assert _rescale_span(10, 30, source_span=30, target=30) == (10, 30)


def test_rescale_preserves_endpoints():
    # chapter 1 → 1, chapter source_span → target (the anchor endpoints never drift).
    assert _rescale_span(1, 1, source_span=60, target=10)[0] == 1
    assert _rescale_span(60, 60, source_span=60, target=10)[1] == 10


def test_rescale_compresses_proportionally():
    # 60 → 10: the midpoint (chapter 30) lands near the target midpoint (~5).
    s, e = _rescale_span(30, 30, source_span=60, target=10)
    assert 5 <= s <= 6 and 5 <= e <= 6


def test_rescale_expands_proportionally():
    # 10 → 30: a placement on chapters 5..6 spreads out across the larger target.
    s, e = _rescale_span(5, 6, source_span=10, target=30)
    assert s < e
    assert 1 <= s <= 30 and 1 <= e <= 30


def test_rescale_clamps_and_orders():
    # out-of-range / inverted inputs are clamped to [1..target] and start<=end.
    s, e = _rescale_span(0, 999, source_span=30, target=8)
    assert 1 <= s <= e <= 8


def test_rescale_single_chapter_source():
    # a degenerate source_span of 1 maps everything to chapter 1 (no div-by-zero).
    assert _rescale_span(1, 1, source_span=1, target=12) == (1, 1)


# ── build_apply_plan: rescale + interleave ───────────────────────────────────────
def test_plan_rescales_every_placement_into_target_range():
    arc = _arc(chapter_span=30, layout=[
        _placement("m.hook", "combat", 1, 3, ord=0),
        _placement("m.climax", "combat", 28, 30, ord=1),
    ])
    plan = build_apply_plan(arc, ArcApplyArgs(target_chapters=10))
    assert plan.target_chapters == 10
    assert plan.source_chapter_span == 30
    for p in plan.placements:
        assert 1 <= p.span_start <= p.span_end <= 10
        # original span retained for audit
        assert p.src_span_start >= 1
    # endpoints anchored: first placement starts at 1, last ends at 10.
    assert plan.placements[0].span_start == 1
    assert plan.placements[-1].span_end == 10


def test_plan_uses_target_as_source_when_span_missing():
    # chapter_span NULL → the source span falls back to target (identity rescale).
    arc = _arc(chapter_span=None, layout=[_placement("m.a", "combat", 1, 1)])
    plan = build_apply_plan(arc, ArcApplyArgs(target_chapters=12))
    assert plan.source_chapter_span == 12
    assert plan.placements[0].span_start == 1


def test_plan_chapter_interleave_lists_active_placements():
    arc = _arc(chapter_span=10, layout=[
        _placement("m.a", "combat", 1, 5, ord=0),
        _placement("m.b", "cultivation", 4, 8, ord=1),
    ])
    plan = build_apply_plan(arc, ArcApplyArgs(target_chapters=10))
    # chapter 4 and 5 fall in BOTH placements' spans → interleave lists both ords.
    assert set(plan.chapter_interleave["4"]) == {0, 1}
    assert set(plan.chapter_interleave["5"]) == {0, 1}
    assert plan.chapter_interleave["1"] == [0]


# ── roster-bind ONCE (§12.5) ─────────────────────────────────────────────────────
def test_roster_bound_once_and_propagated_to_every_placement():
    arc = _arc(
        arc_roster=[{"key": "protagonist", "actant": "subject"},
                    {"key": "rival", "actant": "opponent"}],
        layout=[
            _placement("m.a", "combat", 1, 5, ord=0),
            _placement("m.b", "combat", 6, 10, ord=1),
        ],
    )
    plan = build_apply_plan(arc, ArcApplyArgs(
        target_chapters=10,
        roster_bindings={"protagonist": "char-XiaoYan", "rival": "char-NaLan"},
    ))
    assert plan.roster_bindings == {"protagonist": "char-XiaoYan", "rival": "char-NaLan"}
    # bound ONCE then propagated identically to EVERY placement.
    for p in plan.placements:
        assert p.role_bindings == {"protagonist": "char-XiaoYan", "rival": "char-NaLan"}
    assert plan.unbound_roster_keys == []


def test_unbound_roster_keys_surfaced_never_silent():
    arc = _arc(arc_roster=[{"key": "protagonist"}, {"key": "mentor"}],
               layout=[_placement("m.a", "combat", 1, 5)])
    plan = build_apply_plan(arc, ArcApplyArgs(
        target_chapters=5, roster_bindings={"protagonist": "char-1"},
    ))
    # 'mentor' had no binding supplied → it is surfaced, not silently dropped.
    assert plan.unbound_roster_keys == ["mentor"]
    assert plan.roster_bindings == {"protagonist": "char-1"}


def test_roster_binding_for_unknown_key_is_ignored():
    # a binding for a key NOT in the roster is dropped (can't smuggle a stray slot).
    arc = _arc(arc_roster=[{"key": "protagonist"}], layout=[_placement("m.a", "combat", 1, 5)])
    plan = build_apply_plan(arc, ArcApplyArgs(
        target_chapters=5, roster_bindings={"protagonist": "c1", "ghost": "c2"},
    ))
    assert plan.roster_bindings == {"protagonist": "c1"}
    assert plan.placements[0].role_bindings == {"protagonist": "c1"}


# ── drop/merge NEVER silent (§12.6) ──────────────────────────────────────────────
def test_merge_reported_when_target_collapses_same_thread_placements():
    # two distinct combat placements at chapters 1..2 and 3..4 of a 4-chapter source,
    # squeezed onto a 1-chapter target → they collapse onto chapter 1. The later one
    # is MERGED into the earlier — and that merge is REPORTED (never silent).
    arc = _arc(chapter_span=4, layout=[
        _placement("m.first", "combat", 1, 2, ord=0),
        _placement("m.second", "combat", 3, 4, ord=1),
    ])
    plan = build_apply_plan(arc, ArcApplyArgs(target_chapters=1))
    codes = [p.motif_code for p in plan.placements]
    # exactly one survivor on the thread; the other is folded in + reported.
    assert "m.first" in codes
    assert "m.second" not in codes
    assert len(plan.drop_merge_report) == 1
    entry = plan.drop_merge_report[0]
    assert entry.kind == "merged"
    assert entry.motif_code == "m.second"
    assert entry.into_motif_code == "m.first"
    # the survivor records what was folded into it.
    survivor = next(p for p in plan.placements if p.motif_code == "m.first")
    assert "m.second" in survivor.merged_codes


def test_no_merge_when_placements_stay_distinct():
    arc = _arc(chapter_span=10, layout=[
        _placement("m.a", "combat", 1, 3, ord=0),
        _placement("m.b", "combat", 7, 10, ord=1),
    ])
    plan = build_apply_plan(arc, ArcApplyArgs(target_chapters=10))
    assert plan.drop_merge_report == []
    assert len(plan.placements) == 2


def test_different_threads_never_merge_even_if_same_chapters():
    # same rescaled chapters but DIFFERENT threads → parallel tracks, not a merge.
    arc = _arc(chapter_span=4, layout=[
        _placement("m.combat", "combat", 1, 4, ord=0),
        _placement("m.romance", "romance", 1, 4, ord=1),
    ])
    plan = build_apply_plan(arc, ArcApplyArgs(target_chapters=1))
    assert plan.drop_merge_report == []
    assert len(plan.placements) == 2


def test_plan_is_deterministic():
    arc = _arc(chapter_span=20, layout=[
        _placement("m.a", "combat", 1, 5, ord=0),
        _placement("m.b", "cultivation", 6, 12, ord=1),
        _placement("m.c", "combat", 13, 20, ord=2),
    ])
    args = ArcApplyArgs(target_chapters=7, roster_bindings={})
    p1 = build_apply_plan(arc, args)
    p2 = build_apply_plan(arc, args)
    assert p1.model_dump() == p2.model_dump()
