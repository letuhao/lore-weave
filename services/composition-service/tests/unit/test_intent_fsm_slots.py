"""The slot registry's three load-bearing properties (spec 2026-07-28, plan §1).

These are the checks a "does the FSM work" test would pass right over: the machine can run
end-to-end, look correct in a demo, and still lose the author's work on the next re-plan or offer
them an option the column cannot hold.
"""
from __future__ import annotations

import pytest

from app.db.repositories.outline import OutlineRepo
from app.services.intent_fsm import slots


def test_every_askable_slot_is_carried_by_the_replan_merge():
    """I-1. A slot the FSM settles but the merge does not carry is DELETED by the next re-plan.

    That is the bug the merge precondition (dccf2393d) was built to prevent, re-introduced one layer
    up and far harder to see — the author would watch their answer vanish with no error anywhere.
    The registry asserts this at import; this test is what makes the assert visible in CI rather
    than only at container boot.
    """
    uncarried = [s for s in slots.SLOT_ORDER if s not in OutlineRepo.INTENT_SLOTS]
    assert uncarried == [], (
        f"{uncarried} would be silently destroyed by a re-plan — widen "
        f"OutlineRepo.INTENT_SLOTS, never narrow this check"
    )


def test_the_entity_slots_are_deliberately_NOT_asked():
    """Spec §5 names POV as an attractive closed set; the merge does not carry it yet.

    Pinned so that adding it is a conscious act with a test to update — not a drive-by that
    reintroduces the data-loss path. When the merge learns to carry them, this test changes.
    """
    for entity_slot in ("pov_entity_id", "present_entity_ids", "location_entity_id"):
        assert entity_slot not in slots.SLOT_ORDER


def test_closed_sets_come_first_and_the_reversed_arm_is_the_exact_mirror():
    """The two POC arms must differ ONLY in order, or they are two experiments, not a comparison."""
    forward = slots.plan_for()
    reverse = slots.plan_for(arm="reversed")
    assert reverse == list(reversed(forward))
    classes = [slots.SLOTS[s].constraint_class for s in forward]
    assert classes[:3] == ["closed", "closed", "closed"]
    # Closed → canon_open → blank_open, never interleaved: each answered slot narrows the next
    # (spec §5), and an open slot asked early would spend the author's attention at its cheapest.
    rank = {"closed": 0, "canon_open": 1, "blank_open": 2}
    assert [rank[c] for c in classes] == sorted(rank[c] for c in classes)


def test_a_caller_cannot_reorder_a_run():
    """`only` narrows the scope; it never sets the order. A caller-ordered run would silently break
    the arm comparison while looking like it worked."""
    assert slots.plan_for(only=["goal", "beat_role"]) == ["beat_role", "goal"]


def test_an_unknown_slot_never_reaches_sql():
    """I-2. The apply step interpolates a COLUMN name, so membership is the whole defense."""
    with pytest.raises(slots.SlotError):
        slots.spec("goal; DROP TABLE outline_node")
    with pytest.raises(slots.SlotError):
        slots.plan_for(only=["goal", "not_a_slot"])


def test_beat_role_degrades_to_open_when_the_book_has_no_structure():
    """A closed set with nothing in it is unanswerable. The class recorded must be what the slot was
    ACTUALLY asked under — a POC that logs the intended class while the run experienced another
    measures nothing."""
    assert slots.effective_class("beat_role", beats=[]) == "blank_open"
    assert slots.effective_class("beat_role", beats=[{"key": "hook"}]) == "closed"
    assert slots.choices_for("beat_role", beats=[{"key": "hook"}, {"key": ""}]) == ["hook"]


@pytest.mark.parametrize("slot,bad", [
    ("tension", 9), ("tension", "high"),
    ("value_shift", 500),
    ("target_words", 0), ("target_words", -3),
    ("exit_state", "not json"), ("exit_state", "[1,2]"),
])
def test_a_value_the_column_cannot_hold_is_REJECTED_not_coerced(slot, bad):
    """Guessing what the author (or the model) meant is how a machine starts authoring. Every one of
    these would otherwise hit a CHECK constraint at write time — a 500 instead of a 422."""
    with pytest.raises(slots.SlotError):
        slots.spec(slot).coerce(bad)


def test_the_empty_value_matches_each_columns_nullability():
    """`decline` writes `empty`. A None into a NOT NULL column 500s on exactly the slots an author
    most wants to decline, and the FSM would then look broken precisely when it is being honest."""
    not_null = {"goal", "conflict", "outcome", "stakes"}
    for name, s in slots.SLOTS.items():
        assert (s.empty == "") is (name in not_null), name


def test_an_over_long_text_slot_is_REJECTED_before_it_poisons_the_node():
    """`outline_node.goal` is plain TEXT in Postgres but `_Short` (2000) on the Pydantic model, and
    `settle_intent_slot` writes raw SQL — so an over-long value WRITES FINE and then makes every
    later `get_node` on that node raise ValidationError. The node goes unreadable to the outline
    tree, the packer and the rail, long after the write that caused it, with nothing pointing back.

    Caught in review, not by a test failing: nothing in the happy path is long enough to trip it.
    """
    from app.db.models import OutlineNode

    long_value = "x" * 2001
    with pytest.raises(slots.SlotError, match="too long"):
        slots.spec("goal").coerce(long_value)
    # The bound is not arbitrary — it is the model's own, and this is what ties them together.
    with pytest.raises(Exception):
        OutlineNode.model_validate({
            "id": "00000000-0000-0000-0000-000000000001",
            "created_by": "00000000-0000-0000-0000-000000000002",
            "project_id": "00000000-0000-0000-0000-000000000003",
            "book_id": "00000000-0000-0000-0000-000000000004",
            "kind": "chapter", "rank": "a0", "goal": long_value,
        })
    assert slots.spec("goal").coerce("x" * 2000) == "x" * 2000


def test_render_is_stable_for_the_mechanical_metric_B_comparison():
    """Metric B is `exact`/`drifted`/`dropped` by STRING comparison (spec §8). An unstable rendering
    would report drift that never happened — and letting a model judge it instead would be asking
    the thing under test to grade itself."""
    a = slots.render("exit_state", {"v": 1, "b": 2, "a": 1})
    b = slots.render("exit_state", {"a": 1, "v": 1, "b": 2})
    assert a == b
    assert slots.render("goal", None) == ""
    assert slots.render("tension", 3) == "3"
