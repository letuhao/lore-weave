"""Unit tests for planning Stage 2 — shape_tension_curve (engine/arc_plan.py).

Pins the review-defect FIX: the opening is capped (no ch1=100), 100 appears ONLY at
the climax, the resolution drops, and a multi-chapter beat ramps within itself.
"""

from app.engine.arc_plan import ChapterTension, band_for, shape_tension_curve


def test_curve_caps_opening_peaks_at_climax_drops_at_resolution():
    # the POC's 12-chapter beat sequence (the one that telescoped to 100 in ch1)
    beats = (["hook"] * 2 + ["establishment"] * 2 + ["rising_conflict"] * 3
             + ["setback"] * 2 + ["climax"] * 2 + ["resolution"])
    curve = shape_tension_curve(beats)
    targets = [c.tension_target for c in curve]
    assert len(curve) == 12
    assert [c.chapter_index for c in curve] == list(range(1, 13))
    # ch1 (hook base) is well below max — the defect was ch1 == 100
    assert targets[0] <= 65
    # 100 appears ONLY in the climax beat (ch10-11), nowhere earlier
    assert max(targets[:9]) < 100
    assert 100 in targets[9:11]
    # resolution drops below the climax
    assert targets[11] < targets[10]


def test_multichapter_beat_ramps_within_itself():
    curve = shape_tension_curve(["rising_conflict"] * 3)
    t = [c.tension_target for c in curve]
    assert t[0] < t[1] < t[2]                 # 55 → 68/69 → 82 (monotonic ramp)
    assert t[0] == 55 and t[2] == 82          # base → peak of the band


def test_single_chapter_beat_sits_at_peak():
    [c] = shape_tension_curve(["climax"])
    assert c.tension_target == 100            # length-1 run → the band peak


def test_unknown_or_none_role_uses_default_band():
    assert band_for(None) == (50, 72)
    assert band_for("nonsense_beat") == (50, 72)
    [a, b] = shape_tension_curve([None, "MADE_UP"])
    assert a.tension_target == 72 and b.tension_target == 72  # each a length-1 default run → peak


def test_case_insensitive_role_lookup():
    [c] = shape_tension_curve(["CLIMAX"])
    assert c.tension_target == 100
