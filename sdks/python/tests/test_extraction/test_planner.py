"""Tests for the two-phase extraction planner (PLAN lane / §3.1, §8.4)."""
from __future__ import annotations

import pytest

from loreweave_extraction.planner import (
    LLMCall,
    ModelCaps,
    Plan,
    PlanRequest,
    Policy,
    Unit,
    effort_output_multiplier,
    per_call_budget,
    plan,
)


def _u(uid, ei, eo, *, splittable=False, axis=None, group="ch1"):
    return Unit(id=uid, kind="character", est_input=ei, est_output=eo,
                splittable=splittable, split_axis=axis, group=group)


def test_per_call_budget_grows_output_with_effort():
    caps = ModelCaps(context_window=10_000, output_ceiling=2_000)
    none_in, none_out = per_call_budget(caps, Policy(reasoning_effort="none"))
    high_in, high_out = per_call_budget(caps, Policy(reasoning_effort="high"))
    # higher effort reserves more output (clamped to the ceiling) → less input budget.
    assert high_out >= none_out
    assert high_in <= none_in
    assert none_out <= caps.output_ceiling and high_out <= caps.output_ceiling


def test_effort_multiplier_monotonic():
    assert (effort_output_multiplier("none") <= effort_output_multiplier("low")
            <= effort_output_multiplier("medium") <= effort_output_multiplier("high"))
    assert effort_output_multiplier("bogus") == 1.0


def test_packs_small_units_up_to_max_units_per_call():
    # 4 tiny units, max 2 per call → 2 calls (the MAX_KINDS_PER_BATCH analog bounds breadth).
    caps = ModelCaps(context_window=100_000, output_ceiling=20_000)
    units = [_u(f"k{i}", 100, 100) for i in range(4)]
    p = plan(PlanRequest("extract", units, caps, Policy(max_units_per_call=2)))
    assert p.est_llm_calls == 2
    assert all(len(c.units) <= 2 for c in p.calls)
    # every unit id is present exactly once across all calls (1:1 attribution, §8.4.6).
    ids = [uid for c in p.calls for uid in c.unit_ids]
    assert sorted(ids) == sorted(u.id for u in units)


def test_packs_by_budget_not_just_count():
    # Two units that together exceed the input budget must split across two calls even
    # though max_units_per_call would allow them together.
    caps = ModelCaps(context_window=3_000, output_ceiling=500)
    # budget_ratio 0.7 → ~2100 input; out reservation 500 → input budget ~1600.
    units = [_u("a", 1_000, 100), _u("b", 1_000, 100)]
    p = plan(PlanRequest("extract", units, caps, Policy(max_units_per_call=5)))
    assert p.est_llm_calls == 2


def test_oversized_splittable_unit_is_split():
    caps = ModelCaps(context_window=10_000, output_ceiling=1_000)
    in_budget, _ = per_call_budget(caps, Policy())
    big = _u("chap", in_budget * 3 + 10, 300, splittable=True, axis="chunk")
    p = plan(PlanRequest("extract", [big], caps, Policy(max_units_per_call=1)))
    assert not p.unplannable
    # split into ≥3 sub-units, each tagged with the root id for the fan-out guard.
    assert p.est_llm_calls >= 3
    assert all(u.root == "chap" for c in p.calls for u in c.units)
    assert any("split chap" in r for r in p.rationale)


def test_oversized_not_splittable_is_unplannable():
    caps = ModelCaps(context_window=2_000, output_ceiling=500)
    in_budget, _ = per_call_budget(caps, Policy())
    big = _u("huge", in_budget + 5_000, 100, splittable=False)
    p = plan(PlanRequest("extract", [big], caps, Policy()))
    assert len(p.unplannable) == 1
    assert p.unplannable[0].unit.id == "huge"
    assert "not splittable" in p.unplannable[0].reason
    assert p.est_llm_calls == 0  # nothing schedulable


def test_output_overflow_triggers_split_even_if_input_fits():
    # Input fits comfortably but est_output blows the output budget → must split.
    caps = ModelCaps(context_window=100_000, output_ceiling=1_000)
    u = _u("dense", 500, 5_000, splittable=True, axis="kind")
    p = plan(PlanRequest("extract", [u], caps, Policy(max_units_per_call=1)))
    assert not p.unplannable
    assert p.est_llm_calls >= 5


def test_fan_out_warning_when_split_is_pathological():
    caps = ModelCaps(context_window=4_000, output_ceiling=500)
    in_budget, _ = per_call_budget(caps, Policy())
    big = _u("runaway", in_budget * 20, 100, splittable=True, axis="chunk")
    p = plan(PlanRequest("extract", [big], caps, Policy(max_units_per_call=1, fan_out_warn_threshold=8)))
    assert p.model_fit_warning is not None
    assert "runaway" in p.model_fit_warning and "larger-context" in p.model_fit_warning


def test_calls_per_chapter_uses_groups():
    caps = ModelCaps(context_window=100_000, output_ceiling=20_000)
    units = [_u("a", 100, 100, group="ch1"), _u("b", 100, 100, group="ch2")]
    p = plan(PlanRequest("extract", units, caps, Policy(max_units_per_call=1)))
    # 2 calls across 2 chapters → 1.0 calls/chapter.
    assert p.calls_per_chapter == 1.0


def test_cost_range_brackets_expected_and_is_zero_when_unpriced():
    caps = ModelCaps(context_window=100_000, output_ceiling=20_000)
    units = [_u("a", 1_000, 500)]
    # Unpriced → all zero.
    p0 = plan(PlanRequest("extract", units, caps, Policy()))
    assert p0.est_cost_range.expected == 0.0
    # Priced → low ≤ expected ≤ high, and the spread comes from the effort multiplier.
    p = plan(PlanRequest("extract", units, caps, Policy(
        reasoning_effort="high", price_per_input_token=1e-6, price_per_output_token=2e-6)))
    cr = p.est_cost_range
    assert cr.low <= cr.expected <= cr.high
    assert cr.high > cr.low  # effort multiplier widened the band


def test_empty_request_is_empty_plan():
    caps = ModelCaps(context_window=10_000, output_ceiling=1_000)
    p = plan(PlanRequest("extract", [], caps, Policy()))
    assert p.est_llm_calls == 0 and p.calls == [] and p.est_cost_range.expected == 0.0


def test_split_subunits_are_unique_and_packed_one_to_one():
    # /review-impl coverage: a split must yield distinct sub-ids, each packed exactly once.
    caps = ModelCaps(context_window=10_000, output_ceiling=1_000)
    in_budget, _ = per_call_budget(caps, Policy())
    big = _u("chap", in_budget * 4, 300, splittable=True, axis="chunk")
    p = plan(PlanRequest("extract", [big], caps, Policy(max_units_per_call=1)))
    ids = [uid for c in p.calls for uid in c.unit_ids]
    assert len(ids) == len(set(ids)), "split sub-unit ids must be unique"
    assert all(i.startswith("chap#") for i in ids)


def test_max_parts_ceiling_makes_over_split_unplannable():
    # /review-impl MED fix: a unit that needs more sub-units than its axis supports (max_parts)
    # is Unplannable — not an unrealizable plan.
    caps = ModelCaps(context_window=10_000, output_ceiling=1_000)
    in_budget, _ = per_call_budget(caps, Policy())
    # needs ~4 parts but the axis (e.g. 2 kinds) only subdivides into 2.
    u = _u("twoKinds", in_budget * 4, 300, splittable=True, axis="kind")
    u = Unit(id=u.id, kind=u.kind, est_input=u.est_input, est_output=u.est_output,
             splittable=True, split_axis="kind", max_parts=2, group="ch1")
    p = plan(PlanRequest("extract", [u], caps, Policy(max_units_per_call=1)))
    assert len(p.unplannable) == 1 and "max_parts=2" in p.unplannable[0].reason
    assert p.est_llm_calls == 0


def test_max_parts_within_ceiling_still_splits():
    caps = ModelCaps(context_window=10_000, output_ceiling=1_000)
    in_budget, _ = per_call_budget(caps, Policy())
    u = Unit(id="ok", kind="character", est_input=in_budget * 2, est_output=200,
             splittable=True, split_axis="kind", max_parts=4, group="ch1")
    p = plan(PlanRequest("extract", [u], caps, Policy(max_units_per_call=1)))
    assert not p.unplannable and p.est_llm_calls >= 2


def test_zero_input_budget_makes_everything_unplannable():
    # Tiny context + high effort → output reservation eats the whole budget → in_budget<=0.
    caps = ModelCaps(context_window=1_200, output_ceiling=1_000)
    u = _u("any", 50, 50, splittable=True, axis="chunk")
    p = plan(PlanRequest("extract", [u], caps, Policy(reasoning_effort="high")))
    # in_budget = 1200*0.7 - min(1000, 1000*2.5)=840-1000 → clamped 0 → can't fit → unplannable.
    assert per_call_budget(caps, Policy(reasoning_effort="high"))[0] == 0
    assert len(p.unplannable) == 1 and p.est_llm_calls == 0


def test_negative_estimates_rejected():
    with pytest.raises(ValueError):
        Unit(id="bad", kind="x", est_input=-1, est_output=0)
    with pytest.raises(ValueError):
        Unit(id="bad", kind="x", est_input=0, est_output=0, max_parts=0)
