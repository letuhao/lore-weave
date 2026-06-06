"""Unit tests for adaptive diverge-K (V1 A3, spec D3).

tension is the EXISTING 0..100 scale (outline_node.tension); high_threshold
defaults to 70 (matching reasoning/policy's "high dramatic tension" gate). Mid
band = [high_threshold//2, high_threshold).
"""

import pytest

from app.engine.adaptive_k import adaptive_k, HIGH_WEIGHT_BEATS


@pytest.mark.parametrize("beat_role,tension,ceiling,expected", [
    # no signals → ceiling (no-regression fallback for hand-authored nodes)
    (None, None, 3, 3),
    (None, None, 5, 5),
    # tension primary, 0..100 scale (threshold 70, mid band [35,70))
    (None, 90, 3, 3),    # high → ceiling
    (None, 70, 3, 3),    # at threshold → ceiling
    (None, 50, 3, 2),    # mid → 2
    (None, 35, 3, 2),    # at mid boundary → 2
    (None, 34, 3, 1),    # below mid → 1
    (None, 10, 3, 1),
    (None, 0, 3, 1),
    # ceiling clamps
    (None, 90, 2, 2),
    (None, 50, 1, 1),    # mid clamped to ceiling=1
    # beat_role secondary: a high-weight beat bumps the base by 1 (clamped)
    ("midpoint", 50, 3, 3),   # mid(2) + bump = 3
    ("climax", 10, 3, 2),     # low(1) + bump = 2
    ("setup", 10, 3, 1),      # non-high-weight beat → no bump
    ("midpoint", 90, 3, 3),   # already ceiling → bump clamped
    # beat_role present, tension absent → base 1, +bump if high-weight
    ("ordeal", None, 3, 2),
    ("setup", None, 3, 1),
    # case-insensitive beat key match
    ("MidPoint", 10, 3, 2),
])
def test_adaptive_k_table(beat_role, tension, ceiling, expected):
    assert adaptive_k(beat_role, tension, k_ceiling=ceiling) == expected


def test_adaptive_k_custom_threshold():
    # threshold=50 → tension 50 now earns the ceiling
    assert adaptive_k(None, 50, k_ceiling=4, high_threshold=50) == 4


def test_adaptive_k_never_below_one_or_above_ceiling():
    for br in (None, "climax", "setup"):
        for t in (None, 0, 35, 70, 100):
            k = adaptive_k(br, t, k_ceiling=3)
            assert 1 <= k <= 3


def test_high_weight_beats_are_real_template_keys():
    # guard against typos drifting from the seeded beat keys
    assert "midpoint" in HIGH_WEIGHT_BEATS and "ten" in HIGH_WEIGHT_BEATS
    assert "setup" not in HIGH_WEIGHT_BEATS
