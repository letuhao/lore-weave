"""diff_class derivation — design §3, op-first order (F6)."""

from app.events.diff_class import derive_diff_class


def _entity(kind, name_hash):
    return {"kind": kind}, name_hash


def test_missing_add_when_before_absent():
    assert derive_diff_class(
        target_type="entity", op="create",
        before_structural=None, after_structural={"kind": "person"},
        before_content_hash=None, after_content_hash="h1",
    ) == "missing-add"


def test_spurious_drop_when_after_absent():
    assert derive_diff_class(
        target_type="entity", op="delete",
        before_structural={"kind": "person"}, after_structural=None,
        before_content_hash="h1", after_content_hash=None,
    ) == "spurious-drop"


def test_kind_change_wins_over_rename_on_compound_edit():
    # rename AND rekind → kind-change (higher signal), not boundary.
    assert derive_diff_class(
        target_type="entity", op="update",
        before_structural={"kind": "person"}, after_structural={"kind": "location"},
        before_content_hash="hA", after_content_hash="hB",
    ) == "kind-change"


def test_boundary_when_only_name_changed():
    assert derive_diff_class(
        target_type="entity", op="update",
        before_structural={"kind": "person"}, after_structural={"kind": "person"},
        before_content_hash="hA", after_content_hash="hB",
    ) == "boundary"


def test_merge_op_wins_first_even_with_null_after():
    # F6: a merge whose merged-away side has after=null must NOT be spurious-drop.
    assert derive_diff_class(
        target_type="entity", op="merge",
        before_structural={"kind": "person"}, after_structural=None,
        before_content_hash="hA", after_content_hash=None,
    ) == "merge"


def test_predicate_fix_by_op():
    assert derive_diff_class(
        target_type="relation", op="predicate_fix",
        before_structural={"predicate": "ally_of"}, after_structural={"predicate": "enemy_of"},
        before_content_hash=None, after_content_hash=None,
    ) == "predicate-fix"


def test_predicate_fix_detected_by_structural_change():
    assert derive_diff_class(
        target_type="relation", op="update",
        before_structural={"predicate": "ally_of"}, after_structural={"predicate": "enemy_of"},
        before_content_hash=None, after_content_hash=None,
    ) == "predicate-fix"


def test_relation_invalidate_is_spurious_drop():
    # op=invalidate, after absent → spurious-drop (walked in r3 review).
    assert derive_diff_class(
        target_type="relation", op="invalidate",
        before_structural={"predicate": "ally_of"}, after_structural=None,
        before_content_hash=None, after_content_hash=None,
    ) == "spurious-drop"


def test_relation_non_predicate_update_is_other_not_boundary():
    # R3-W3: a relation update with predicate unchanged is `other`, never boundary.
    assert derive_diff_class(
        target_type="relation", op="update",
        before_structural={"predicate": "ally_of", "confidence": 0.8},
        after_structural={"predicate": "ally_of", "confidence": 1.0},
        before_content_hash=None, after_content_hash=None,
    ) == "other"
