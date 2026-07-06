"""Tests for the Context Budget kernel Planner + budget math (T3.2)."""
from loreweave_context import CompilePlan, Planner, compute_target
from loreweave_context.budget import compute_target as _bt

P = Planner()


# ── compute_target (moved into the kernel; chat re-exports it) ────────────────
def test_compute_target_band():
    assert compute_target(200_000, task_weight=0.0) == 6_000    # floor cap
    assert compute_target(200_000, task_weight=1.0) == 32_000   # surface_max cap
    assert compute_target(20_000, task_weight=0.0) == 2_000     # 0.1×window floor
    assert compute_target(20_000, task_weight=1.0) == 7_000     # 0.35×window surface
    assert 2_000 < compute_target(20_000, task_weight=0.5) < 7_000


def test_compute_target_edges():
    assert compute_target(None) is None
    assert compute_target(0) is None
    assert compute_target(200_000, task_weight=5.0) == 32_000            # >1 clamps
    assert compute_target(200_000, task_weight=-1.0) == 6_000           # <0 clamps
    assert compute_target(200_000, task_weight=float("nan")) == 32_000  # NaN → roomy
    assert _bt is compute_target                                        # same object


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
