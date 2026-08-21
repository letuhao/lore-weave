"""S3 — one locator across five producers, and the state that used to have no shape.

The defect the union is worth building for
------------------------------------------
`self_heal.Finding.located` is `tuple[int,int] | None`, and `None` is an ANSWER: the judge
quoted text that could not be found in the chapter. It reached a human only by making the
`located` COUNT smaller — and `PolishPanel` renders `"{{edits}} edits · {{refuted}} dropped"`,
never `findings`, then falls through to *"No issues found — the prose is clean."* when there
are no proposals. So a run that finds six problems and places none reported CLEAN.

`plan_heal` has the same two-states-one-shape problem from the other side: on a not-located
finding it leaves `chapter`/`scene` populated with numbers that point at nothing, so a consumer
reading them as a position sends a human to a scene that does not exist.

These tests pin both directions, per producer, with a control for each.
"""
from __future__ import annotations

import uuid

from app.engine.canon_check import CanonViolation
from app.engine.error_block_heal import MergedFinding
from app.engine.finding import Locator, LocatorKind, SkipReason
from app.engine.plan_heal import PlanFinding
from app.engine.self_heal import Finding
from app.engine.stitch import _OverResolveFinding, _RepetitionFinding


# ── the union itself ──────────────────────────────────────────────────────────────────────

def test_a_locator_that_points_nowhere_says_so():
    loc = Locator.nowhere(quote="he smiled", why=SkipReason.NOT_LOCATED)
    assert loc.placed is False
    assert loc.as_payload()["placed"] is False
    assert loc.as_payload()["quote"] == "he smiled", "the quote is the human's only handle"


def test_CONTROL_a_placed_locator_says_placed():
    assert Locator.span(3, 9, "abc").placed is True


def test_placed_is_on_the_wire_so_an_OLD_reader_cannot_misread_a_NEW_kind():
    """`placed` is redundant with `kind` and emitted anyway.

    A consumer that has not learned a sixth `LocatorKind` must not read an unplaced finding as
    placed just because it does not recognise the tag. That is the same reasoning that keeps
    `CheckStatus` explicit rather than inferred from an empty verdict list.
    """
    for loc in (Locator.span(0, 1), Locator.scene_at(1, 1), Locator.seam(1, 2),
                Locator.blocks(["b1"]), Locator.entity("e1"), Locator.nowhere()):
        assert "placed" in loc.as_payload()
        assert loc.as_payload()["placed"] == loc.placed


def test_the_payload_drops_empties_but_never_the_two_load_bearing_keys():
    p = Locator.scene_at(2, 5).as_payload()
    assert p == {"kind": "scene", "placed": True, "chapter": 2, "scene": 5}


def test_str_of_the_kind_is_the_VALUE_not_the_member_path():
    """`StrEnum`, not `(str, Enum)` — the regression `SkipReason` shipped and a live run
    caught: `f"{kind}"` returning `"LocatorKind.SPAN"` while `== "span"` stayed True, so
    every unit test passed and every rendered string was wrong."""
    assert f"{LocatorKind.SPAN}" == "span"
    assert Locator.span(0, 1).as_payload()["kind"] == "span"


# ── every producer projects, and every producer can say NOWHERE ───────────────────────────

def test_self_heal_unlocated_finding_is_a_locator_not_an_absence():
    loc = Finding(type="repetition", span="he smiled", issue="i", fix="f").locator
    assert loc.placed is False and loc.quote == "he smiled"
    assert loc.why == SkipReason.NOT_LOCATED


def test_CONTROL_self_heal_located_finding_carries_its_offsets():
    loc = Finding(type="t", span="x", issue="i", fix="f", located=(3, 9)).locator
    assert (loc.kind, loc.start, loc.end, loc.placed) == (LocatorKind.SPAN, 3, 9, True)


def test_plan_heal_not_located_does_NOT_report_its_meaningless_position():
    """The chapter/scene numbers are still on the object; the locator must not repeat them.

    `run_plan_self_heal` sets NOT_LOCATED when the index is out of range, leaving
    `chapter`/`scene` as numbers that address nothing.
    """
    loc = PlanFinding(chapter=9, scene=9, issue="q", skip_reason=SkipReason.NOT_LOCATED).locator
    assert loc.placed is False
    assert loc.chapter is None and loc.scene is None


def test_CONTROL_plan_heal_located_finding_is_a_scene_position():
    loc = PlanFinding(chapter=2, scene=1).locator
    assert (loc.kind, loc.chapter, loc.scene) == (LocatorKind.SCENE, 2, 1)


def test_a_stitch_finding_is_a_SEAM_and_not_either_scene():
    """Attributing it to one side would name a scene that is individually fine."""
    loc = _RepetitionFinding(1, 2, "the wind").locator
    assert loc.kind is LocatorKind.SEAM
    assert (loc.scene, loc.right_scene) == (1, 2)
    assert loc.quote == "the wind"
    assert _OverResolveFinding(3, 4).locator.kind is LocatorKind.SEAM


def test_a_merged_block_finding_carries_BOTH_ids_and_offsets():
    b = uuid.UUID(int=1)
    loc = MergedFinding(block_ids=[b], start=0, end=5, notes=["n"]).locator
    assert loc.kind is LocatorKind.BLOCKS
    assert loc.block_ids == (str(b),)
    assert (loc.start, loc.end) == (0, 5), "the ids address the editor, the offsets the text"


def test_a_canon_violation_with_no_entity_is_UNLOCATED():
    """`plan_conflicts` returns `unlinked` names for exactly this reason: an assertion the
    guard could not place is a hole in coverage, not a finding about nobody."""
    loc = CanonViolation(entity_id="", name="Ghost", matched="Ghost").locator
    assert loc.placed is False and loc.quote == "Ghost"


def test_CONTROL_a_canon_violation_with_an_entity_points_at_it():
    loc = CanonViolation(entity_id="e1", name="Alice", matched="Alice",
                         span="…Alice…").locator
    assert (loc.kind, loc.entity_id, loc.matched) == (LocatorKind.ENTITY, "e1", "Alice")


# ── the denominator: every finding type projects ──────────────────────────────────────────

def test_every_finding_producer_has_a_locator():
    """The list is the five the spec names. `test_finding_locator_gate.py` derives the same
    set from the CODE, so a sixth producer cannot be added without answering this."""
    producers = [
        Finding(type="t", span="s", issue="i", fix="f"),
        PlanFinding(chapter=1, scene=1),
        _RepetitionFinding(1, 2, "p"),
        _OverResolveFinding(1, 2),
        MergedFinding(block_ids=[uuid.UUID(int=2)], start=0, end=1, notes=[]),
        CanonViolation(entity_id="e", name="n"),
    ]
    for p in producers:
        loc = p.locator
        assert isinstance(loc, Locator), f"{type(p).__name__} does not project a Locator"
        assert isinstance(loc.as_payload(), dict)
