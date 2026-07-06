"""D-ML-A5-RECANON-BACKFILL — unit tests for the pure re-canon planner.

`plan_recanon` decides how pre-A5 entities (whose stored canonical kept a native
honorific) reconcile to their post-A5 canonical id. These pin the reconciliation
logic; the apply path (real Neo4j) is operator-run and not unit-tested (mirrors
the C17 backfill split).
"""

from __future__ import annotations

from app.db.migrations.recanon_honorifics import EntityRow, plan_recanon
from loreweave_extraction.canonical import entity_canonical_id

_U = "user-1"
_P = "proj-1"
_K = "character"


def _new_id(name: str) -> str:
    return entity_canonical_id(_U, _P, name, _K)


def _row(id_: str, name: str, canonical_name: str) -> EntityRow:
    return EntityRow(id=id_, user_id=_U, project_id=_P, kind=_K, name=name, canonical_name=canonical_name)


def test_clean_entity_untouched():
    # canonical_name already equals the A5 re-canon → no drift, no action.
    rows = [_row(_new_id("田中"), "田中", "田中")]
    plan = plan_recanon(rows)
    assert plan.actions == []
    assert plan.clean == 1 and plan.rekeyed == 0 and plan.merged == 0


def test_stranded_no_sibling_rekeys_to_new_id():
    # A pre-A5 "田中様" node (stored canonical kept the honorific) with no clean
    # sibling → re-key it to the canonical id of "田中".
    rows = [_row("OLD_tanaka_sama", "田中様", "田中様")]
    plan = plan_recanon(rows)
    assert plan.rekeyed == 1 and plan.merged == 0
    (action,) = plan.actions
    assert action.op == "rekey"
    assert action.from_id == "OLD_tanaka_sama"
    assert action.into_id == _new_id("田中")


def test_stranded_merges_into_existing_clean_sibling():
    # A clean post-A5 "田中" node already exists at the new id → the stranded
    # "田中様" node MERGEs into it; the sibling survives (no rekey).
    sibling_id = _new_id("田中")
    rows = [
        _row(sibling_id, "田中", "田中"),
        _row("OLD_tanaka_sama", "田中様", "田中様"),
    ]
    plan = plan_recanon(rows)
    assert plan.merged == 1 and plan.rekeyed == 0
    (action,) = plan.actions
    assert action.op == "merge"
    assert action.from_id == "OLD_tanaka_sama"
    assert action.into_id == sibling_id


def test_multiple_stranded_variants_one_survivor():
    # "田中様" and "田中さん" both re-canon to "田中"; no clean sibling → one is
    # re-keyed as survivor, the other merges into it. Deterministic survivor
    # (lowest stored id).
    rows = [
        _row("id_b_sama", "田中様", "田中様"),
        _row("id_a_san", "田中さん", "田中さん"),
    ]
    plan = plan_recanon(rows)
    assert plan.rekeyed == 1 and plan.merged == 1
    rekey = next(a for a in plan.actions if a.op == "rekey")
    merge = next(a for a in plan.actions if a.op == "merge")
    assert rekey.from_id == "id_a_san"      # lowest id wins survivor
    assert rekey.into_id == _new_id("田中")
    assert merge.from_id == "id_b_sama"
    assert merge.into_id == _new_id("田中")


def test_vietnamese_and_korean_stranded():
    rows = [
        _row("OLD_ong_nam", "ông Nam", "ông nam"),
        _row("OLD_kim_nim", "김선생님", "김선생님"),
    ]
    plan = plan_recanon(rows)
    assert plan.rekeyed == 2 and plan.merged == 0
    into = {a.into_id for a in plan.actions}
    assert _new_id("Nam") in into and _new_id("김") in into


def test_empty_canonical_skipped():
    # A degenerate entity whose name is ONLY a honorific canonicalizes to "" →
    # left untouched (can't derive an id), counted as skipped_empty.
    rows = [_row("OLD_bare", "様", "様")]
    plan = plan_recanon(rows)
    assert plan.skipped_empty == 1 and plan.actions == []


def test_plan_is_deterministic():
    rows = [
        _row("id_b_sama", "田中様", "田中様"),
        _row("id_a_san", "田中さん", "田中さん"),
        _row(_new_id("李"), "李", "李"),
    ]
    p1 = plan_recanon(rows)
    p2 = plan_recanon(rows)
    assert [(a.op, a.from_id, a.into_id) for a in p1.actions] == \
           [(a.op, a.from_id, a.into_id) for a in p2.actions]
