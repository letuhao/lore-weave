"""Tests for the Context Budget kernel Planner + budget math (T3.2)."""
from loreweave_context import CompilePlan, Planner, compute_target, scale_by_window
from loreweave_context.budget import compute_target as _bt

P = Planner()


# ── scale_by_window — the shared helper for the many smaller sub-budgets
# (tool-surface hot-seed, steering, single-tool-result caps) that were each tuned
# as a flat constant against a mid-size window ────────────────────────────────
def test_scale_by_window_unknown_context_length_keeps_flat_default():
    assert scale_by_window(4000, None) == 4000
    assert scale_by_window(4000, 0) == 4000


def test_scale_by_window_negative_context_length_keeps_flat_default():
    # /review-impl LOW: a bogus/corrupt negative context_length (e.g. from a
    # user_models row that predates provider-registry's positive-value validation)
    # must degrade to the flat default, not propagate — a narrowed guard (e.g.
    # `context_length < 0` instead of `<= 0`) would let 0 through silently.
    assert scale_by_window(4000, -100) == 4000


def test_scale_by_window_never_shrinks_below_flat_default():
    # A window smaller than tuned_window must NOT reduce the budget below what's
    # already deployed — this helper only ever grows a budget, never shrinks one.
    assert scale_by_window(4000, 8_000, tuned_window=200_000) == 4000


def test_scale_by_window_scales_up_for_a_larger_window():
    # The exact bug class: a flat cap tuned for a 200K model must NOT clamp a
    # genuinely bigger window to the same number.
    assert scale_by_window(4000, 1_000_000, tuned_window=200_000) == 20_000
    assert scale_by_window(6000, 1_000_000, tuned_window=200_000) == 30_000


# ── compute_target (moved into the kernel; chat re-exports it) ────────────────
def test_compute_target_band():
    assert compute_target(200_000, task_weight=0.0) == 20_000    # 0.1×window floor
    assert compute_target(200_000, task_weight=1.0) == 150_000   # 0.75×window surface
    assert compute_target(20_000, task_weight=0.0) == 2_000      # 0.1×window floor
    assert compute_target(20_000, task_weight=1.0) == 15_000     # 0.75×window surface
    assert 2_000 < compute_target(20_000, task_weight=0.5) < 15_000


def test_compute_target_edges():
    assert compute_target(None) is None
    assert compute_target(0) is None
    assert compute_target(200_000, task_weight=5.0) == 150_000            # >1 clamps
    assert compute_target(200_000, task_weight=-1.0) == 20_000           # <0 clamps
    assert compute_target(200_000, task_weight=float("nan")) == 150_000  # NaN → roomy
    assert _bt is compute_target                                         # same object


def test_compute_target_has_no_absolute_cap_on_a_huge_window():
    # No absolute cap on either end: a 1M-context model must NOT be clamped to whatever
    # a 200K model gets — this is the exact regression a hardcoded cap reintroduces.
    assert compute_target(1_000_000, task_weight=0.0) == 100_000
    assert compute_target(1_000_000, task_weight=1.0) == 750_000


# ── Planner.plan (the compaction policy seam) ────────────────────────────────
def test_plan_disabled_is_flat():
    plan = P.plan(grounding_needed=True, context_length=200_000,
                  task_elastic_enabled=False, light_task_weight=0.5)
    assert isinstance(plan, CompilePlan)
    assert plan.compact_target is None      # flag off → flat 0.75×window trigger downstream
    assert plan.task_weight == 1.0
    assert plan.grounding is True


def test_plan_grounding_turn_is_roomy():
    plan = P.plan(grounding_needed=True, context_length=40_000,
                  task_elastic_enabled=True, light_task_weight=0.5)
    assert plan.task_weight == 1.0
    assert plan.compact_target == compute_target(40_000, task_weight=1.0)  # surface_max


def test_plan_status_turn_is_lean():
    plan = P.plan(grounding_needed=False, context_length=40_000,
                  task_elastic_enabled=True, light_task_weight=0.5)
    assert plan.task_weight == 0.5
    assert plan.compact_target == compute_target(40_000, task_weight=0.5)
    # a status turn's target is strictly leaner than a grounding turn's
    assert plan.compact_target < compute_target(40_000, task_weight=1.0)
    assert plan.grounding is False


def test_plan_swappable_subclass():
    # the seam: a policy override changes the plan without touching the consumer.
    class Aggressive(Planner):
        def plan(self, **kw):
            base = super().plan(**kw)
            return CompilePlan(grounding=base.grounding, task_weight=0.0,
                               compact_target=compute_target(kw["context_length"], task_weight=0.0))
    plan = Aggressive().plan(grounding_needed=True, context_length=40_000,
                             task_elastic_enabled=True, light_task_weight=0.5)
    assert plan.task_weight == 0.0 and plan.compact_target == 4_000
