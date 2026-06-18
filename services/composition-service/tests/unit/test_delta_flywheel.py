"""C27 (dị bản M4) — delta-flywheel core logic tests (pure, AI-free).

Covers the LOCKED invariants:
  • extraction targets the DERIVATIVE's own delta project_id (never source/null);
  • the project-scope GUARD fires on a null delta project (refuse dispatch);
  • forward-from-branch write-order — an out-of-order (pre-branch) chapter yields a
    THINNER delta (skip), NOT a correctness break;
  • a non-derivative (canon/greenfield) Work is a clean no-op (no flywheel).
"""

from __future__ import annotations

import uuid

import pytest

from app.engine.delta_flywheel import (
    DeltaScopeError,
    assert_delta_extraction_scoped,
    is_forward_of_branch,
    plan_flywheel_dispatch,
)

DELTA = uuid.uuid4()   # the derivative's OWN project (the extraction target)
SOURCE = uuid.uuid4()  # the source/base project


# ── PROJECT-SCOPE GUARD ──────────────────────────────────────────────


def test_guard_passes_for_a_real_derivative():
    # both present → no raise
    assert_delta_extraction_scoped(DELTA, SOURCE) is None


def test_guard_refuses_null_delta_project():
    # a null delta project would widen the extraction write to ALL projects.
    with pytest.raises(DeltaScopeError):
        assert_delta_extraction_scoped(None, SOURCE)


def test_guard_refuses_null_source_means_not_derivative():
    with pytest.raises(DeltaScopeError):
        assert_delta_extraction_scoped(DELTA, None)


# ── FORWARD-FROM-BRANCH WRITE-ORDER ──────────────────────────────────


def test_forward_of_branch_at_or_after_is_delta():
    assert is_forward_of_branch(4, 4) is True   # at the branch
    assert is_forward_of_branch(7, 4) is True   # after the branch


def test_pre_branch_chapter_is_not_delta():
    # an out-of-order (before the branch) chapter is inherited base, not delta.
    assert is_forward_of_branch(2, 4) is False


def test_null_branch_means_diverge_from_start_all_forward():
    assert is_forward_of_branch(0, None) is True
    assert is_forward_of_branch(100, None) is True


def test_unplaceable_chapter_is_conservatively_included():
    # can't prove it is pre-branch → don't silently drop it.
    assert is_forward_of_branch(None, 4) is True


# ── plan_flywheel_dispatch — the full decision ───────────────────────


def test_plan_dispatches_for_forward_derivative_chapter_into_delta():
    d = plan_flywheel_dispatch(
        delta_project_id=DELTA, source_project_id=SOURCE,
        branch_point=4, chapter_sort_order=5,
    )
    assert d.dispatch is True
    assert d.reason == "delta_dispatch"
    # CRITICAL: the extraction target is the DERIVATIVE's own project, never source.
    assert d.delta_project_id == DELTA
    assert d.delta_project_id != SOURCE


def test_plan_skips_non_derivative_clean_no_op():
    d = plan_flywheel_dispatch(
        delta_project_id=DELTA, source_project_id=None,
        branch_point=None, chapter_sort_order=1,
    )
    assert d.dispatch is False
    assert d.reason == "not_a_derivative"


def test_plan_skips_pre_branch_thinner_delta_not_an_error():
    # an out-of-order pre-branch chapter degrades to a SKIP, never raises.
    d = plan_flywheel_dispatch(
        delta_project_id=DELTA, source_project_id=SOURCE,
        branch_point=4, chapter_sort_order=2,
    )
    assert d.dispatch is False
    assert d.reason == "pre_branch_thinner_delta"


def test_plan_raises_on_null_delta_for_a_real_forward_derivative():
    # a derivative that SHOULD dispatch but has a null delta project → GUARD raises
    # (never a silent wrong-partition / all-projects write).
    with pytest.raises(DeltaScopeError):
        plan_flywheel_dispatch(
            delta_project_id=None, source_project_id=SOURCE,
            branch_point=4, chapter_sort_order=5,
        )


def test_plan_pre_branch_check_precedes_scope_guard():
    # a pre-branch chapter on a null-delta derivative should SKIP (thinner delta),
    # NOT trip the guard — the forward-from-branch check runs first so out-of-order
    # authoring degrades gracefully.
    d = plan_flywheel_dispatch(
        delta_project_id=None, source_project_id=SOURCE,
        branch_point=4, chapter_sort_order=2,
    )
    assert d.dispatch is False
    assert d.reason == "pre_branch_thinner_delta"
