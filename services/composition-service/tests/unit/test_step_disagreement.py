"""Reporting the SILENCE: a run that collapsed looks exactly like a book that is small.

The hole. `character_seed present n=1` is what you get from a book with one character AND from a run
that fell over. `status` answers "may I claim absence?" — it says nothing about completeness, so the
board had no way to raise its hand. Measured on the Chinese corpus: 1 run in 12 came back with a
single name where the same document yields four on the other 11, and nothing anywhere said so.

The signal, and why it needs no ground truth: the run now has **two independent counts of the same
thing**. Carrying the cast through `analyze` — the fix for the vanished nameless character — is what
made this possible; before it the cast existed at exactly one point in the pipeline and there was
nothing to compare it against.

Reported, never repaired. A shrink is not necessarily wrong (materialize legitimately merges
duplicates), so the machine says "these two steps disagreed, look" and stops.
"""

from __future__ import annotations

from app.engine.plan_forge.coverage import spec_coverage_board
from app.engine.plan_forge.propose_llm_async import _attach_step_disagreement


def _spec(**over):
    base = {
        "meta": {"open_questions": [], "ingest_unread": {}},
        "charter": {"style_constraints": [], "forbids": [], "consistency_anchors": []},
        "layers": {"characters": [], "mechanics": [], "variables": []},
        "arcs": [], "events": [], "links": [],
    }
    base.update(over)
    return base


def test_a_COLLAPSED_cast_is_reported_against_the_run_s_own_earlier_count():
    """The exact failure: analyze read four people, the plan kept one."""
    spec = _spec(layers={"characters": [{"name": "沈砚"}], "mechanics": [], "variables": []})
    _attach_step_disagreement(spec, {"characters": [{"name": n} for n in
                                                    ("沈砚", "姜芜", "裴钧", "无名者")]})
    blk = spec["meta"]["ingest_unread"]
    assert blk["step_disagreement"] == {"characters": {"analyze": 4, "spec": 1}}
    assert "4 → 1" in blk["note"] and "disagree" in blk["note"]

    board = spec_coverage_board(spec)
    cast = next(k for k in board["kinds"] if k["kind"] == "character_seed")
    assert cast["status"] == "present", "the kind IS present — this is about completeness, not absence"
    assert cast["shrank_from"] == 4, "the author cannot see the collapse without the earlier count"


def test_a_HEALTHY_run_says_nothing():
    """A signal that fires on every run is one nobody reads, and then it is not a signal."""
    spec = _spec(layers={"characters": [{"name": "a"}, {"name": "b"}], "mechanics": [],
                         "variables": []})
    _attach_step_disagreement(spec, {"characters": [{"name": "a"}, {"name": "b"}]})
    assert "step_disagreement" not in spec["meta"]["ingest_unread"]
    board = spec_coverage_board(spec)
    assert all("shrank_from" not in k for k in board["kinds"])


def test_GROWING_is_not_reported():
    """materialize may legitimately add — an arc split, a character named in prose the analyze
    summarised. Only a LOSS is worth the author's attention."""
    spec = _spec(arcs=[{"title": "a"}, {"title": "b"}, {"title": "c"}])
    _attach_step_disagreement(spec, {"arcs": [{"title": "a"}]})
    assert "step_disagreement" not in spec["meta"]["ingest_unread"]


def test_an_analyze_that_found_NOTHING_cannot_have_lost_anything():
    spec = _spec()
    _attach_step_disagreement(spec, {"characters": [], "arcs": []})
    assert "step_disagreement" not in spec["meta"]["ingest_unread"]


def test_every_cross_checked_field_maps_to_a_board_kind():
    """A disagreement the board cannot render is a disagreement nobody sees."""
    from app.engine.plan_forge.coverage import _DISAGREEMENT_KEY
    from app.engine.plan_forge.propose_llm_async import _CROSS_STEP

    rendered = set(_DISAGREEMENT_KEY.values())
    # `events` is deliberately not a board kind (it rides `arc_overview`); everything else must land.
    assert set(_CROSS_STEP) - rendered == {"events"}


def test_the_note_survives_alongside_a_degraded_read_note():
    """Two different truths about one run. Neither may overwrite the other."""
    from app.engine.plan_forge.propose_llm_async import _attach_read_provenance

    spec = _spec(layers={"characters": [{"name": "a"}], "mechanics": [], "variables": []})
    _attach_read_provenance(spec, [{"step": "analyze"}, {"step": "analyze_retry1"}])
    _attach_step_disagreement(spec, {"characters": [{"name": "a"}, {"name": "b"}]})
    note = spec["meta"]["ingest_unread"]["note"]
    assert "regenerated or repaired" in note and "disagree" in note
