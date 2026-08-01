"""S1 — the canon guard adopts the per-check primitive, and the false-green closes.

The measured bug, 2026-08-01: a 4-scene, 8,116-word chapter where every scene's canon guard
returned ``status="skipped_no_cast"``, ``resolved=True``, ``violations=[]``. Three of the four
scenes contained an invented character. `chapter_scene_gate`'s SQL listed the "unchecked"
states as ``('skipped_no_position','degraded')`` — so the ONE state in which the guard verified
nothing at all was the state the publish gate read as fine.

These tests pin the two halves: the guard now says what it did per check, and the derived
headline is what the gate keys on.
"""
from __future__ import annotations

import pytest
from loreweave_guard import CheckStatus

from app.engine.canon_check import ReflectResult


def _R(**kw) -> ReflectResult:
    return ReflectResult(text="prose", **kw)


# ── the guard's own honesty ───────────────────────────────────────────────────────────────

def test_a_scene_with_no_cast_no_longer_reports_a_checked_guard():
    r = _R(status="skipped_no_cast", resolved=True,
           checks={"canon_cast": CheckStatus.NO_SUBJECT, "name_grounding": CheckStatus.CHECKED})
    assert r.guard_status == "no_subject"
    assert r.guard_status != "checked", "this is the exact false-green the chapter shipped with"
    # …and the legacy scalar is UNCHANGED, because SQL and stored rows depend on it.
    assert r.status == "skipped_no_cast"


def test_CONTROL_a_fully_checked_scene_still_reads_checked():
    """Without this, "never checked" would satisfy the test above and break the publish gate
    in the other direction — every chapter permanently unpublishable."""
    r = _R(status="checked", resolved=True,
           checks={"canon_cast": CheckStatus.CHECKED, "name_grounding": CheckStatus.CHECKED})
    assert r.guard_status == "checked"


def test_a_partly_degraded_composite_does_not_round_up():
    r = _R(status="checked",
           checks={"canon_cast": CheckStatus.DEGRADED, "name_grounding": CheckStatus.CHECKED})
    assert r.guard_status == "degraded", "one dead check must not be hidden by a live one"


def test_a_caseless_script_is_NOT_a_coverage_gap():
    """The name detector is capitalisation-based, so on Chinese/Japanese there is nothing for
    it to see and never will be. Counting that as a gap paints permanent amber on every CJK
    book — the failure mode S1 exists to prevent, arriving from the other direction."""
    r = _R(status="checked",
           checks={"canon_cast": CheckStatus.CHECKED,
                   "name_grounding": CheckStatus.NOT_APPLICABLE})
    assert r.guard_status == "checked"


def test_a_guard_that_declared_no_checks_is_not_a_pass():
    """The shape a NEW generation path takes before anyone wires its checks in."""
    assert _R(status="checked", resolved=True).guard_status == "not_applicable"


def test_the_derived_headline_SERIALISES():
    """A `@property` would be invisible to `model_dump`, and `guard_status` is read back OUT of
    `generation_job.result` by the publish-gate SQL. A derived field that exists only in Python
    is a field the gate cannot see."""
    d = _R(status="skipped_no_cast", checks={"canon_cast": CheckStatus.NO_SUBJECT}).model_dump()
    assert d["guard_status"] == "no_subject"
    assert d["checks"] == {"canon_cast": "no_subject"}


# ── the guard populates it on every path, including the early returns ─────────────────────

@pytest.mark.asyncio
async def test_the_no_cast_early_return_carries_per_check_statuses():
    from app.engine.canon_reflect import run_canon_reflect

    _text, result, _tok = await run_canon_reflect(
        knowledge=None, llm=None, user_id=__import__("uuid").uuid4(),
        project_id=__import__("uuid").uuid4(), cast_glossary_ids=[],
        scene_sort_order=1, draft="Cassius walked away.", packed_prompt="",
        profile=type("P", (), {"source_language": "en"})(),
        drafter_source="s", drafter_ref="m", judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100,
    )
    assert result.checks["canon_cast"] == CheckStatus.NO_SUBJECT
    assert result.guard_status != "checked"


@pytest.mark.asyncio
async def test_the_no_position_early_return_says_no_position_not_no_subject():
    """Two different reasons a guard could not run. Collapsing them loses the only signal that
    distinguishes 'this book has no cast bound' from 'this scene's chapter ref is dangling'."""
    from app.engine.canon_reflect import run_canon_reflect

    _text, result, _tok = await run_canon_reflect(
        knowledge=None, llm=None, user_id=__import__("uuid").uuid4(),
        project_id=__import__("uuid").uuid4(), cast_glossary_ids=["e1"],
        scene_sort_order=None, draft="Cassius walked away.", packed_prompt="",
        profile=type("P", (), {"source_language": "en"})(),
        drafter_source="s", drafter_ref="m", judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100,
    )
    assert result.checks["canon_cast"] == CheckStatus.NO_POSITION
    assert result.guard_status == "no_position"
