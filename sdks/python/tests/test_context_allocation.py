"""S11 — the allocation layer must be able to say LESS, which is what `scale_by_window` cannot.

The bug being fixed is arithmetic and it is pinned here numerically rather than described:
`scale_by_window(6000, 4096)` is 6000, i.e. 146% of the window it has to fit inside.
"""
from __future__ import annotations

import pytest

from loreweave_context import allocate_context, scale_by_window
from loreweave_context.allocation import ContextAllocation


# ── the defect, stated as arithmetic ──────────────────────────────────────────────────────

@pytest.mark.parametrize("window,share", [(4096, 1.46), (8192, 0.73)])
def test_scale_by_window_CANNOT_shrink_and_that_is_the_bug(window, share):
    """Not a criticism of `scale_by_window` — its contract says it only ever grows, and for
    the flat-constant problem it was written for that is right. It is the wrong tool for
    dividing a window, and this pins WHY so the next reader does not re-adopt it."""
    got = scale_by_window(6000, window)
    assert got == 6000
    assert got / window == pytest.approx(share, abs=0.01)


def test_the_allocator_shrinks_where_scale_by_window_could_not():
    a = allocate_context(8192, grounding_default=6000, output_reserve=2048)
    assert a.grounding < 6000, "the allocator did not reduce a block that cannot fit"
    assert a.clamped is True
    assert a.total <= 8192, "the parts still do not fit the window"
    assert a.fits is True


def test_a_roomy_window_is_UNCHANGED_which_is_what_makes_adoption_safe():
    """The control, and the more important half. If adoption altered every book's budget it
    would be a re-tuning wearing a refactor's clothes. On the windows real models actually
    have, the caller's own default must survive untouched."""
    for window in (32_768, 131_072, 200_000, 1_000_000):
        a = allocate_context(window, grounding_default=6000, output_reserve=4096)
        assert a.grounding == 6000, f"window={window} silently re-tuned the budget"
        assert a.clamped is False


# ── the unknown window: adoption must be a provable no-op ─────────────────────────────────

@pytest.mark.parametrize("window", [None, 0, -1])
def test_an_unknown_window_returns_the_callers_numbers_untouched(window):
    """`resolve_context_length` returns None rather than fabricating, so this is the path a
    real adoption hits whenever provider-registry cannot answer. It must change nothing."""
    a = allocate_context(window, grounding_default=6000, output_reserve=4096)
    assert (a.grounding, a.source, a.clamped) == (6000, "flat", False)
    assert a.window is None


def test_source_distinguishes_a_flat_answer_from_a_computed_one():
    """Two allocations can carry the same `grounding` for opposite reasons — the window was
    roomy, or the window was unknown. A caller auditing an adoption needs to tell those
    apart, which is the same 'silence and intent must not look alike' rule the budget seam
    and OutputKind.MIRROR are both built on."""
    roomy = allocate_context(200_000, grounding_default=6000, output_reserve=4096)
    unknown = allocate_context(None, grounding_default=6000, output_reserve=4096)
    assert roomy.grounding == unknown.grounding == 6000
    assert (roomy.source, unknown.source) == ("window", "flat")


# ── the floor, and the failure it exists to make visible ──────────────────────────────────

def test_a_window_too_small_gets_the_FLOOR_and_says_it_was_clamped():
    """A 4096-token model cannot hold 6000 tokens of grounding plus a reply. Returning a
    12-token block would produce an empty pack that reads as 'this book has no grounding' —
    a lie the caller cannot distinguish from the truth."""
    a = allocate_context(4096, grounding_default=6000, output_reserve=3000)
    assert a.grounding == 512
    assert a.clamped is True


def test_fits_reports_an_over_committed_model_rather_than_hiding_it():
    """When even the floor does not fit, the allocation says so instead of quietly returning
    numbers that cannot all be honoured. `fits` is the field a caller branches on."""
    a = allocate_context(2048, grounding_default=6000, output_reserve=1800)
    assert a.grounding == 512
    assert a.fits is False, "an impossible allocation reported itself as fine"


def test_a_roomy_window_reports_fits_true():
    """Control for the assertion above — otherwise `fits` could be hardcoded False."""
    assert allocate_context(200_000, grounding_default=6000, output_reserve=4096).fits is True


# ── the output reserve is subtracted, not shared ───────────────────────────────────────────

def test_a_bigger_output_reserve_takes_room_from_GROUNDING():
    """S7-4 made the output side adaptive and, on a full roster, much larger. The two halves
    now have to be decided together: grounding can be trimmed after the fact, a reply that
    stops mid-sentence cannot."""
    small = allocate_context(16_384, grounding_default=99_999, output_reserve=1_000)
    large = allocate_context(16_384, grounding_default=99_999, output_reserve=9_000)
    assert large.grounding == small.grounding - 8_000


def test_the_allocation_is_frozen():
    a = allocate_context(None, grounding_default=6000, output_reserve=4096)
    assert isinstance(a, ContextAllocation)
    with pytest.raises(Exception):
        a.grounding = 1  # type: ignore[misc]
