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


# ══ S2 · one cast-liveness SSOT, both directions ══════════════════════════════════════════

class _Knowledge:
    """A knowledge client that returns a FIXED snapshot. The shape under test is a POPULATED
    graph that has no row for the subject — not an outage, not an empty graph."""

    def __init__(self, snapshot):
        self._snap = snapshot

    async def fact_for_check(self, **kw):
        return self._snap


async def _reflect(cast, snapshot):
    from app.engine.canon_reflect import run_canon_reflect
    import uuid as _u
    return await run_canon_reflect(
        knowledge=_Knowledge(snapshot), llm=None, user_id=_u.uuid4(), project_id=_u.uuid4(),
        cast_glossary_ids=list(cast), scene_sort_order=1,
        draft="They met at the gate.", packed_prompt="",
        profile=type("P", (), {"source_language": "en"})(),
        drafter_source="s", drafter_ref="m", judge_source=None, judge_ref=None,
        prompt_estimate=0, max_output_tokens=100, max_iters=0,
    )


@pytest.mark.asyncio
async def test_a_POPULATED_graph_with_no_row_for_the_subject_is_NO_RULES_not_checked():
    """THE S2 fixture. The graph is healthy and has statuses for other entities — it simply
    has never heard of this scene's cast. There was nothing to check AGAINST, and reporting
    `checked` there is the per-entity version of the whole S1 false-green."""
    _t, r, _ = await _reflect(
        ["ghost"], {"entities": [{"entity_id": "someone_else", "status": "alive"}]})
    assert r.cast_liveness["ghost"] == {"status": "unknown", "source": "none"}
    assert r.unresolved_refs == 1
    assert r.checks["canon_cast"] == CheckStatus.NO_RULES
    assert r.guard_status != "checked"


@pytest.mark.asyncio
async def test_CONTROL_a_cast_the_graph_KNOWS_reads_checked_with_zero_unresolved():
    """Without this, "always NO_RULES" would satisfy the test above and make the canon guard
    report a gap on every book forever."""
    _t, r, _ = await _reflect(
        ["elara"], {"entities": [{"entity_id": "elara", "status": "alive"}]})
    assert r.cast_liveness["elara"] == {"status": "alive", "source": "kg"}
    assert r.unresolved_refs == 0
    assert r.checks["canon_cast"] == CheckStatus.CHECKED


@pytest.mark.asyncio
async def test_a_PARTLY_known_cast_still_checks_and_still_counts_the_gap():
    """One resolvable entity means the check had a corpus. The unresolved one is REPORTED
    rather than deciding the whole check's status — otherwise a single new character would
    blank the guard for the entire scene."""
    _t, r, _ = await _reflect(
        ["elara", "ghost"], {"entities": [{"entity_id": "elara", "status": "gone"}]})
    assert r.checks["canon_cast"] == CheckStatus.CHECKED
    assert r.unresolved_refs == 1


@pytest.mark.asyncio
async def test_an_OUTAGE_is_degraded_and_outranks_the_no_rules_reading():
    """`snapshot=None` is knowledge being down. Everything resolves unknown/none, but the
    honest headline is DEGRADED — the guard is fine, its input is missing — and calling that
    NO_RULES would blame an empty corpus for an outage."""
    _t, r, _ = await _reflect(["elara"], None)
    assert r.checks["canon_cast"] == CheckStatus.DEGRADED
    assert r.unresolved_refs == 1, "and the count is still honest about what it could not resolve"
