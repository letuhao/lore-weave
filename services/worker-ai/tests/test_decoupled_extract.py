"""Phase 2b WX-T3a — pure state-machine coverage for the decoupled extraction
orchestrator. The DB/SDK shell + consumer are covered by the live-smoke; here we
lock the stage transitions, the trio FAN-IN (advance only when all 3 folded, any
order, idempotent on a duplicate), and the filter sub-loop."""

from app import decoupled_extract as d


def _rs(has_recovery=False, has_filter=False):
    return d.new_extract_state(
        chunk_text="text", known_entities=["A"],
        has_recovery=has_recovery, has_filter=has_filter,
    )


def test_new_state_defaults():
    rs = _rs()
    assert rs["stage"] == d.ENTITY
    assert rs["entities"] == [] and rs["trio_folded"] == []
    assert rs["filter_idx"] == 0 and rs["filter_n"] == 0


def test_entity_with_results_goes_to_trio():
    rs = d.apply_entity_result(_rs(), ["e1", "e2"])
    assert rs["stage"] == d.TRIO and rs["entities"] == ["e1", "e2"]


def test_entity_empty_short_circuits_to_persist():
    rs = d.apply_entity_result(_rs(), [])
    assert rs["stage"] == d.PERSIST  # nothing to anchor


def test_op_for_job_maps_terminal_event_to_op():
    rs = d.begin_trio(_rs(), {"relation": "jr", "event": "je", "fact": "jf"})
    assert d.op_for_job(rs, "je") == "event"
    assert d.op_for_job(rs, "nope") is None


def test_trio_fanin_advances_only_when_all_three_folded_any_order():
    rs = d.apply_entity_result(_rs(), ["e1"])
    rs = d.begin_trio(rs, {"relation": "jr", "event": "je", "fact": "jf"})
    # fold out of order: event, fact, relation
    rs = d.fold_trio_op(rs, "event", ["ev"])
    assert not d.trio_complete(rs) and rs["stage"] == d.TRIO
    rs = d.fold_trio_op(rs, "fact", ["fa"])
    assert not d.trio_complete(rs) and rs["stage"] == d.TRIO
    rs = d.fold_trio_op(rs, "relation", ["re"])
    assert d.trio_complete(rs)
    assert rs["events"] == ["ev"] and rs["facts"] == ["fa"] and rs["relations"] == ["re"]
    # neither recovery nor filter → straight to persist
    assert rs["stage"] == d.PERSIST


def test_trio_fold_idempotent_on_duplicate_op():
    rs = d.begin_trio(d.apply_entity_result(_rs(), ["e1"]),
                      {"relation": "jr", "event": "je", "fact": "jf"})
    rs = d.fold_trio_op(rs, "relation", ["re"])
    again = d.fold_trio_op(rs, "relation", ["DUP"])  # duplicate terminal event
    assert again["relations"] == ["re"]  # unchanged
    assert again["trio_folded"] == ["relation"]


def test_after_trio_gates_on_recovery_then_filter():
    base = d.begin_trio(d.apply_entity_result(_rs(has_recovery=True, has_filter=True), ["e1"]),
                        {"relation": "jr", "event": "je", "fact": "jf"})
    rs = base
    for op in ("relation", "event", "fact"):
        rs = d.fold_trio_op(rs, op, [op])
    assert rs["stage"] == d.RECOVERY  # recovery wins first

    # filter-only project skips recovery
    rs2 = d.begin_trio(d.apply_entity_result(_rs(has_filter=True), ["e1"]),
                       {"relation": "jr", "event": "je", "fact": "jf"})
    for op in ("relation", "event", "fact"):
        rs2 = d.fold_trio_op(rs2, op, [op])
    assert rs2["stage"] == d.FILTER


def test_recovery_advances_to_filter_or_persist():
    rs = _rs(has_recovery=True, has_filter=True)
    rs["stage"] = d.RECOVERY
    out = d.apply_recovery_result(rs, entities=["e1", "e2"], relations=["r1"])
    assert out["stage"] == d.FILTER and out["entities"] == ["e1", "e2"]

    rs2 = _rs(has_recovery=True, has_filter=False)
    rs2["stage"] = d.RECOVERY
    out2 = d.apply_recovery_result(rs2, entities=["e1"], relations=[])
    assert out2["stage"] == d.PERSIST


def test_filter_subloop_runs_each_batch_then_persists():
    rs = _rs(has_filter=True)
    rs = d.begin_filter(rs, n_batches=2)
    assert rs["stage"] == d.FILTER and rs["filter_n"] == 2
    rs = d.apply_filter_batch(rs, {"entities": ["e1"]})
    assert rs["filter_idx"] == 1 and rs["stage"] == d.FILTER and not d.filter_done(rs)
    rs = d.apply_filter_batch(rs, {"relations": ["r1"]})
    assert rs["filter_idx"] == 2 and d.filter_done(rs) and rs["stage"] == d.PERSIST
    assert rs["entities"] == ["e1"] and rs["relations"] == ["r1"]


def test_begin_filter_zero_batches_goes_straight_to_persist():
    rs = d.begin_filter(_rs(has_filter=True), n_batches=0)
    assert rs["stage"] == d.PERSIST


def test_candidates_dict_assembles_accumulators():
    rs = _rs()
    rs["entities"] = ["e"]; rs["relations"] = ["r"]; rs["events"] = ["v"]; rs["facts"] = ["f"]
    assert d.candidates_dict(rs) == {
        "entities": ["e"], "relations": ["r"], "events": ["v"], "facts": ["f"],
    }
