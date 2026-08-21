"""S11 — flipping composition onto the allocation layer must be a MEASURED no-op.

RUN-STATE invariant 6 (sealed): *no existing `loreweave_context` consumer changes behaviour
until its own measurement says it may.* This file IS that measurement, kept as a test so the
claim stays true rather than being true on the day it was written.
"""
from __future__ import annotations

import pytest

from app.packer.budget import PACK_OUTPUT_RESERVE_TOKENS, pack_budget_for

FLAT = 6000


# ── the half that makes adoption safe ─────────────────────────────────────────────────────

@pytest.mark.parametrize("window", [16_384, 32_768, 131_072, 200_000])
def test_a_real_models_window_is_UNCHANGED_by_the_switch(window):
    """Every window at or above 16K keeps the exact budget it had before. The dev stack's
    model reports 200000, so this is the case that covers essentially all live traffic — if
    it moved, the flip would be a silent re-tuning of every book."""
    assert pack_budget_for(window, FLAT).grounding == FLAT


def test_an_UNRESOLVED_window_is_unchanged_too():
    """`resolve_context_length` returns None rather than fabricating, so this is the path a
    real request takes whenever provider-registry cannot answer."""
    a = pack_budget_for(None, FLAT)
    assert (a.grounding, a.source, a.clamped) == (FLAT, "flat", False)


def test_a_million_token_window_KEEPS_its_growth():
    """The trap in composing the two functions. `allocate_context` alone caps at the default,
    which would have silently REVOKED `scale_by_window`'s growth for big models — fixing the
    small-window bug by introducing a large-window one."""
    assert pack_budget_for(1_000_000, FLAT).grounding == 30_000


# ── the half that fixes the defect ────────────────────────────────────────────────────────

@pytest.mark.parametrize("window,share", [(4096, 1.46), (8192, 0.73)])
def test_the_old_number_did_not_fit_the_window_at_all(window, share):
    """Stated as arithmetic so it cannot be argued with: the pre-switch grounding budget was
    this fraction of the model's ENTIRE context, before the prompt and before the reply."""
    assert FLAT / window == pytest.approx(share, abs=0.01)


def test_a_small_window_is_reduced_AND_flagged():
    a = pack_budget_for(8192, FLAT)
    assert a.grounding < FLAT
    assert a.clamped is True, "the shrink happened silently"
    assert a.total <= 8192


def test_an_impossible_window_reports_fits_False_instead_of_pretending():
    a = pack_budget_for(4096, FLAT)
    assert a.clamped is True and a.fits is False


def test_the_reserve_is_a_typical_reply_not_the_runaway_ceiling():
    """`SCENE_OUTPUT_CEILING` is 32768. Reserving it would clamp every window below ~128K to
    the floor — a re-tuning of every book wearing a safety fix's clothes. Pinned because the
    number is a judgement call and the WRONG one is silently catastrophic."""
    from app.engine.cowrite import SCENE_OUTPUT_CEILING

    assert PACK_OUTPUT_RESERVE_TOKENS < SCENE_OUTPUT_CEILING / 4
    # …and with the ceiling as the reserve, a 32K model would indeed be gutted — which is the
    # counterfactual that justifies the constant above.
    assert pack_budget_for(32_768, FLAT, output_reserve=SCENE_OUTPUT_CEILING).grounding == 512
    assert pack_budget_for(32_768, FLAT).grounding == FLAT
