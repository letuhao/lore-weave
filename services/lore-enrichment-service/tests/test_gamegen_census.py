"""The provenance census — five counts and two ratios, each a different fact.

`census.py` shipped with no caller and no test. These are written against what the
module's own docstring PROMISES, because that is the only specification it has, and
a test that merely re-states the implementation would certify whatever it does.

The two ratios are where a defect would hide, and they hide in opposite directions:
`completeness` must NOT be improved by refusing a field, and `groundedness` must NOT
be damaged by a magnitude. Both are asserted against a case where a wrong
implementation gives a different number, never against a case where every
implementation agrees.
"""
from __future__ import annotations

from app.gamegen.census import Census, Origin, census_of


def _cell(answer_id: str, state: str = "answered") -> dict:
    return {"state": state, "answer_id": answer_id}


GROUNDED = {"a1": {"grounded": True}, "a2": {"grounded": True},
            "a3": {"grounded": False}, "a4": {"grounded": False}}


# ── the five counts are five different facts ────────────────────────────────

def test_each_origin_is_counted_under_its_own_name():
    c = census_of(
        body={"realm": _cell("a1"),
              "sect": _cell("a3"),
              "lifespan": _cell("a9", state="not_stated"),
              "trade": _cell("a9", state="refused")},
        answers_by_id=GROUNDED,
        magnitudes={"/realm/qi_cost": 40},
        default_provenance={"/sect/rank_titles": "engine"},
    )
    assert (c.book, c.model, c.policy, c.engine, c.silent) == (1, 1, 1, 1, 2)
    assert c.total == 6 and c.chosen == 3


def test_a_refusal_is_counted_as_absent_not_as_defaulted():
    """`refused` and `not_stated` both mean *the player will not see this*, and
    neither means *the engine handled it*. Folding either into ENGINE would read as
    coverage; folding either into the chosen counts would read as a decision."""
    c = census_of(body={"x": _cell("a9", state="refused")}, answers_by_id={},
                  magnitudes={}, default_provenance={})
    assert c.silent == 1 and c.engine == 0 and c.chosen == 0
    assert c.by_field["/x"] == Origin.SILENT


def test_an_answer_with_no_verified_citation_is_MODEL_not_BOOK():
    c = census_of(body={"x": _cell("a3")}, answers_by_id=GROUNDED,
                  magnitudes={}, default_provenance={})
    assert (c.book, c.model) == (0, 1)


def test_an_answer_id_the_map_does_not_know_falls_to_MODEL():
    """Missing evidence is not evidence. An unknown answer must never be credited
    to the book — that is the direction the error has to fall."""
    c = census_of(body={"x": _cell("ghost")}, answers_by_id=GROUNDED,
                  magnitudes={}, default_provenance={})
    assert (c.book, c.model) == (0, 1)


# ── the two ratios, each asserted where a wrong one differs ─────────────────

def test_completeness_is_not_improved_by_refusing_a_field():
    """The failure this guards: counting SILENT as *handled* would make a pipeline
    that refuses everything score 1.0. Same body, one field refused — the number
    must go DOWN."""
    full = census_of(body={"a": _cell("a1"), "b": _cell("a2")},
                     answers_by_id=GROUNDED, magnitudes={}, default_provenance={})
    part = census_of(body={"a": _cell("a1"), "b": _cell("a9", state="not_stated")},
                     answers_by_id=GROUNDED, magnitudes={}, default_provenance={})
    assert full.completeness == 1.0
    assert part.completeness == 0.5, "SILENT must sit in the denominator"


def test_groundedness_is_not_damaged_by_a_magnitude():
    """`PGN-A5` — a magnitude is never in the book. Counting policy against
    groundedness would penalise the pipeline for obeying its own axiom, so adding
    magnitudes must leave the ratio untouched while completeness rises."""
    bare = census_of(body={"a": _cell("a1"), "b": _cell("a3")},
                     answers_by_id=GROUNDED, magnitudes={}, default_provenance={})
    with_mag = census_of(body={"a": _cell("a1"), "b": _cell("a3")},
                         answers_by_id=GROUNDED,
                         magnitudes={"/a/cost": 1, "/b/cost": 2},
                         default_provenance={})
    assert bare.groundedness == 0.5
    assert with_mag.groundedness == 0.5, "policy is excluded from groundedness"
    assert with_mag.completeness == 1.0 and with_mag.policy == 2


def test_a_complete_manifest_can_be_entirely_ungrounded():
    """The reason there are two numbers and not one."""
    c = census_of(body={"a": _cell("a3"), "b": _cell("a4")}, answers_by_id=GROUNDED,
                  magnitudes={}, default_provenance={})
    assert c.completeness == 1.0 and c.groundedness == 0.0


def test_empty_ratios_are_zero_rather_than_a_division_error():
    c = Census()
    assert c.total == 0 and c.completeness == 0.0 and c.groundedness == 0.0


# ── by_field is what makes a low ratio actionable ───────────────────────────

def test_by_field_names_which_fields_not_only_how_many():
    c = census_of(
        body={"realm": {"tiers": [_cell("a1"), _cell("a3")]}},
        answers_by_id=GROUNDED,
        magnitudes={"/realm/qi": 9},
        default_provenance={"/realm/titles": "engine"},
    )
    assert c.by_field == {
        "/realm/tiers/0": Origin.BOOK,
        "/realm/tiers/1": Origin.MODEL,
        "magnitude:/realm/qi": Origin.POLICY,
        "default:/realm/titles": Origin.ENGINE,
    }


def test_a_cell_is_a_leaf_even_though_it_is_a_dict():
    """The cell must carry a STRUCTURED value here, and that is the whole test.

    It took two tries to make it able to fail. A scalar-only cell passed with the
    `return` removed, because `visit` ignores strings. A cell holding a structured
    value passed too, because the walk only COUNTS at a cell, so recursing found
    nothing to count. Both were assertions with no possible violation (`NV-1`), and
    only the third fixture has one: a cell nested inside a cell's value. The outer
    cell is the field; the inner one must contribute nothing, or one decision is
    counted twice and `completeness` reports coverage that does not exist."""
    cell = {"state": "answered", "answer_id": "a1",
            "value": {"detail": {"state": "answered", "answer_id": "a3"}}}
    c = census_of(body={"a": cell}, answers_by_id=GROUNDED,
                  magnitudes={}, default_provenance={})
    assert c.total == 1, f"the cell is one field, not its contents: {c.by_field}"
    assert set(c.by_field) == {"/a"}


def test_as_dict_names_engine_and_silent_by_what_they_MEAN():
    c = census_of(body={"a": _cell("a9", state="not_stated")}, answers_by_id={},
                  magnitudes={}, default_provenance={"/b": "engine"})
    d = c.as_dict()
    assert d["engine_defaulted"] == 1 and d["not_stated"] == 1
    assert "engine" not in d and "silent" not in d, (
        "the serialised names are the report's vocabulary; `engine`/`silent` are "
        "the internal ones and must not leak as if they were the report"
    )
