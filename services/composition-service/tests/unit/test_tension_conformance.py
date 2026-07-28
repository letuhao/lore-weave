"""E7 — the tension-curve conformance measure.

Pass 4 shapes a curve; pass 6 hands it to the drafter as a prompt line and never checks. Whether
the model obeyed was unobservable: `parse_scenes` clamps a scene's tension to 0..100 and is never
told the chapter's target, so a chapter that missed by 22 looked exactly like one that hit exactly.

The fixture below is not invented. It is the real curve and the real realised peaks from plan run
`019f9d2e`'s beat_plan `019f9f0f` and scene_plan `019f9f12` — measured by hand against the database
before this module existed. Pinning the module against them is what makes it a MEASURE rather than
a plausible function: if it cannot reproduce the numbers that motivated it, it is wrong.
"""

from __future__ import annotations

from app.engine import tension_conformance as tc

# ── the real arc (10 chapters), verbatim from the stored artifacts ────────────

REAL_CURVE = [
    {"chapter_index": 1, "beat_role": "hook", "tension_target": 65},
    {"chapter_index": 2, "beat_role": "establishment", "tension_target": 35},
    {"chapter_index": 3, "beat_role": "establishment", "tension_target": 58},
    {"chapter_index": 4, "beat_role": "rising_conflict", "tension_target": 55},
    {"chapter_index": 5, "beat_role": "rising_conflict", "tension_target": 68},
    {"chapter_index": 6, "beat_role": "rising_conflict", "tension_target": 82},
    {"chapter_index": 7, "beat_role": "setback", "tension_target": 66},
    {"chapter_index": 8, "beat_role": "setback", "tension_target": 90},
    {"chapter_index": 9, "beat_role": "climax", "tension_target": 100},
    {"chapter_index": 10, "beat_role": "resolution", "tension_target": 52},
]
REAL_PEAKS = [65, 35, 58, 55, 68, 60, 66, 90, 100, 48]


def _plan(peaks: list[int | None], *, start: int = 1) -> list[dict]:
    """A `scene_plan` artifact's `chapters`, each chapter's peak realised as its top scene."""
    out = []
    for i, p in enumerate(peaks, start=start):
        scenes = [] if p is None else [{"tension": max(0, p - 12)}, {"tension": p}]
        out.append({"chapter": {"sort_order": i, "title": f"ch{i}"}, "scenes": scenes})
    return out


def test_it_reproduces_the_measurement_that_MOTIVATED_it():
    """The whole point. 8 of 10 chapters landed EXACTLY on target, two undershot (−22, −4), and the
    drafter never once exceeded a target — consistent with the prompt's "do not exceed it"."""
    r = tc.measure(REAL_CURVE, _plan(REAL_PEAKS))
    assert r["measured"] is True
    assert [c["delta"] for c in r["chapters"]] == [0, 0, 0, 0, 0, -22, 0, 0, 0, -4]
    assert r["on_target"] == 9 and r["under"] == 1 and r["over"] == 0
    assert r["mean_abs_delta"] == 2.6
    # …and the one real miss is NAMED, not merely counted — a count tells an author something is
    # wrong without telling them where to look.
    assert "chapter 6 aimed at 82, peaked at 60" in r["warning"]


def test_a_clean_arc_says_NOTHING_rather_than_congratulating_itself():
    """A warning that fires on every run is one nobody reads."""
    r = tc.measure(REAL_CURVE, _plan([c["tension_target"] for c in REAL_CURVE]))
    assert r["on_target"] == 10 and r["warning"] == ""


def test_PEAK_not_mean_because_the_target_IS_a_peak():
    """`shape_tension_curve` ramps base→peak, so `tension_target` is the chapter's intended PEAK.
    Measuring the mean would compare a different quantity and read as a systematic undershoot on
    every multi-scene chapter — a whole-plan false alarm."""
    chapters = [{"chapter": {"sort_order": 1}, "scenes": [
        {"tension": 10}, {"tension": 20}, {"tension": 70},
    ]}]
    r = tc.measure([{"chapter_index": 1, "beat_role": "hook", "tension_target": 70}], chapters)
    assert r["chapters"][0]["peak"] == 70 and r["chapters"][0]["delta"] == 0


def test_OVER_is_its_own_verdict_not_a_signed_UNDER():
    """The prompt says "do not exceed"; overshooting is disobedience where undershooting is a
    shortfall. An author deciding whether to re-run wants to know which happened."""
    curve = [{"chapter_index": 1, "beat_role": "establishment", "tension_target": 40}]
    over = tc.measure(curve, _plan([95]))
    under = tc.measure(curve, _plan([5]))
    assert over["chapters"][0]["verdict"] == "over" and over["over"] == 1
    assert under["chapters"][0]["verdict"] == "under" and under["under"] == 1


def test_a_chapter_with_no_scenes_is_UNMEASURED_not_a_zero_tension_miss():
    """A degraded chapter (`scene_decompose_degraded`) has no scenes at all. Scoring it as peak-0
    would report a catastrophic pacing miss for what is really an upstream failure — and would
    drag `mean_abs_delta` into meaninglessness."""
    r = tc.measure(REAL_CURVE[:3], _plan([65, None, 58]))
    verdicts = [c["verdict"] for c in r["chapters"]]
    assert verdicts == ["on_target", "no_scenes", "on_target"]
    assert r["chapters"][1]["peak"] is None and r["chapters"][1]["delta"] is None
    assert r["no_scenes"] == 1
    assert r["mean_abs_delta"] == 0.0          # the unmeasured chapter does not pollute the mean
    assert "1 chapter(s) have no scenes" in r["warning"]


# ── absent ≠ zero ─────────────────────────────────────────────────────────────


def test_NO_curve_reports_UNMEASURED_never_a_clean_bill_of_health():
    """The bug class this repo keeps re-shipping. "We did not look" and "we looked and found
    nothing" render identically unless the report says which it was."""
    for empty in ([], None, "not a list", [{"nonsense": 1}]):
        r = tc.measure(empty, _plan([50]))
        assert r["measured"] is False
        assert "NOT measured" in r["warning"]
        assert "on_target" not in r          # no counts at all — nothing to misread as success


def test_a_curve_shaped_from_NO_BEAT_ROLES_is_flagged_as_degenerate():
    """`shape_tension_curve([None]*n)` groups every chapter into one neutral run and ramps it
    base→peak: a smooth climb indistinguishable, by its numbers, from a planned arc. It is what a
    failed L1 beat-mapping degrades to, and it is REAL — plan artifact 019f9d2f stores exactly
    this, ten chapters reading 50,52,55…72 with every `beat_role` NULL."""
    flat = [
        {"chapter_index": i, "beat_role": None, "tension_target": t}
        for i, t in enumerate([50, 52, 55, 57, 60, 62, 65, 67, 70, 72], start=1)
    ]
    r = tc.measure(flat, _plan([50, 52, 55, 57, 60, 62, 65, 67, 70, 72]))
    assert r["degenerate_curve"] is True
    assert "NO beat roles" in r["warning"]
    # …and it is flagged even though every chapter hit its target exactly, which is the point:
    # perfect conformance to a curve that was never planned is not success.
    assert r["on_target"] == 10


def test_a_REAL_single_beat_arc_is_linear_too_and_must_NOT_be_flagged():
    """Detection keys on the ROLES, not on the shape of the numbers. A legitimate arc that spends
    every chapter in one beat also ramps linearly — flagging it would make the warning noise."""
    curve = [
        {"chapter_index": i, "beat_role": "rising_conflict", "tension_target": t}
        for i, t in enumerate([50, 58, 66, 74, 82], start=1)
    ]
    assert tc.is_degenerate(curve) is False
    assert tc.measure(curve, _plan([50, 58, 66, 74, 82]))["degenerate_curve"] is False


def test_a_one_chapter_curve_is_never_degenerate():
    """One chapter cannot demonstrate a missing shape — calling it degenerate would flag every
    short arc."""
    assert tc.is_degenerate([{"chapter_index": 1, "beat_role": None, "tension_target": 50}]) is False


# ── the pass-6 → pass-7 bridge ────────────────────────────────────────────────


def test_curve_from_report_recovers_the_targets_pass_7_cannot_otherwise_reach():
    """`self_heal` depends on ("scenes", "cast") — NOT on `beats`. Widening that to reach the curve
    would change its input fingerprint and stale it for no functional gain. It does not need to:
    pass 6 stamps the targets onto the artifact that IS pass 7's input."""
    stamped = tc.measure(REAL_CURVE, _plan(REAL_PEAKS))
    recovered = tc.curve_from_report(stamped)
    assert len(recovered) == 10
    assert recovered[5] == {"chapter_index": 6, "beat_role": "rising_conflict",
                            "tension_target": 82}
    # measuring the SAME plan against the recovered curve reproduces the original verdicts —
    # otherwise a pass-6 → pass-7 comparison would be against a subtly different yardstick
    again = tc.measure(recovered, _plan(REAL_PEAKS))
    assert [c["delta"] for c in again["chapters"]] == [c["delta"] for c in stamped["chapters"]]


def test_a_HEAL_that_flattens_the_arc_is_caught_by_re_measuring():
    """The reason pass 7 is re-measured at all: `run_plan_self_heal` receives the DecomposeResult
    and nothing else — no curve, no targets — so it can rewrite scenes into a flat plan while
    reporting a successful heal."""
    before = tc.measure(REAL_CURVE, _plan(REAL_PEAKS))
    after = tc.measure(tc.curve_from_report(before), _plan([50] * 10))   # the heal flattened it
    assert before["on_target"] == 9 and after["on_target"] <= 4
    assert after["warning"] and "missed their tension target" in after["warning"]


def test_curve_from_report_on_an_UNMEASURED_report_yields_nothing_measurable():
    """Degrade must not manufacture a yardstick. An unmeasured pass 6 means pass 7 has nothing to
    compare against, and must say so rather than invent targets."""
    unmeasured = tc.measure([], _plan([50]))
    assert tc.curve_from_report(unmeasured) == []
    assert tc.measure(tc.curve_from_report(unmeasured), _plan([50]))["measured"] is False
    for junk in (None, {}, {"chapters": "nope"}, {"chapters": [{"chapter_index": 1}]}):
        assert tc.curve_from_report(junk) == []


# ── tolerant of the shapes real artifacts actually carry ──────────────────────


def test_string_and_float_tensions_are_read_not_dropped():
    """A model emitting "70" instead of 70 has answered correctly in bad packaging — the same
    tolerance `parse_world`/`parse_cast` apply."""
    chapters = [{"chapter": {"sort_order": 1}, "scenes": [{"tension": "70"}, {"tension": 65.4}]}]
    r = tc.measure([{"chapter_index": 1, "beat_role": "hook", "tension_target": 70}], chapters)
    assert r["chapters"][0]["peak"] == 70


def test_a_boolean_target_is_not_a_target():
    """`bool` is an `int` subclass, so a stray `true` would silently measure as target 1 and report
    every chapter as a massive overshoot."""
    r = tc.measure([{"chapter_index": 1, "beat_role": "hook", "tension_target": True}], _plan([70]))
    assert r["measured"] is False


def test_chapters_align_by_SORT_ORDER_not_by_position():
    """A plan whose chapters arrive out of order must not compare chapter 3 against chapter 7's
    target — a silent mis-alignment would report misses that are really a sorting artifact."""
    chapters = list(reversed(_plan([65, 35, 58])))
    r = tc.measure(REAL_CURVE[:3], chapters)
    assert [c["delta"] for c in r["chapters"]] == [0, 0, 0]


def test_malformed_input_degrades_and_never_raises():
    for chapters in (None, "nope", [None, 7], [{"scenes": "no"}], [{"chapter": "x", "scenes": []}]):
        r = tc.measure(REAL_CURVE[:1], chapters)
        assert r["measured"] is True and r["chapters"][0]["verdict"] == "no_scenes"
