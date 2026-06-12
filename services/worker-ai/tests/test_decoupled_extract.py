"""Phase 2b WX-T3a — pure state-machine coverage for the decoupled extraction
orchestrator. The DB/SDK shell + consumer are covered by the live-smoke; here we
lock the stage transitions, the trio FAN-IN (advance only when all 3 folded, any
order, idempotent on a duplicate), and the filter sub-loop."""

from unittest.mock import MagicMock

from app import decoupled_extract as d


def _job(result: dict):
    j = MagicMock()
    j.status = "completed"
    j.result = result
    return j


def _seed_shell_rs():
    rs = d.new_extract_state(
        chunk_text="Kai met Bob.", known_entities=[],
        has_recovery=False, has_filter=False,
    )
    rs.update(user_id="u", project_id="p", model_source="user_model", model_ref="m")
    return rs


def _rs(has_recovery=False, has_filter=False):
    return d.new_extract_state(
        chunk_text="text", known_entities=["A"],
        has_recovery=has_recovery, has_filter=has_filter,
    )


def test_new_state_defaults():
    rs = _rs()
    assert rs["stage"] == d.ENTITY
    assert rs["entities"] == [] and rs["trio_folded"] == []
    assert rs["trio_jobs"] == {}


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


def test_recovery_fanout_folds_each_batch_then_advances():
    rs = _rs(has_recovery=True, has_filter=True)
    rs["stage"] = d.RECOVERY
    rs = d.begin_recovery(rs, {"b0": "j0", "b1": "j1"})
    assert d.recovery_task_for_job(rs, "j1") == "b1"
    rs = d.fold_recovery_task(rs, "b0", entities=["e1"], relations=["r1"])
    assert not d.recovery_complete(rs) and rs["stage"] == d.RECOVERY
    rs = d.fold_recovery_task(rs, "b1", entities=["e1", "e2"], relations=[])
    assert d.recovery_complete(rs)
    assert rs["entities"] == ["e1", "e2"] and rs["relations"] == []
    assert rs["stage"] == d.FILTER  # has_filter

    # recovery-only (no filter) → persist
    rs2 = d.begin_recovery({**_rs(has_recovery=True), "stage": d.RECOVERY}, {"b0": "j0"})
    rs2 = d.fold_recovery_task(rs2, "b0", entities=["e"], relations=[])
    assert rs2["stage"] == d.PERSIST


def test_begin_recovery_empty_skips_to_filter_or_persist():
    rs = d.begin_recovery({**_rs(has_recovery=True, has_filter=True), "stage": d.RECOVERY}, {})
    assert rs["stage"] == d.FILTER
    rs2 = d.begin_recovery({**_rs(has_recovery=True), "stage": d.RECOVERY}, {})
    assert rs2["stage"] == d.PERSIST


def test_recovery_fold_idempotent_on_duplicate():
    rs = d.begin_recovery({**_rs(has_recovery=True), "stage": d.RECOVERY}, {"b0": "j0"})
    rs = d.fold_recovery_task(rs, "b0", entities=["e"], relations=[])
    again = d.fold_recovery_task(rs, "b0", entities=["DUP"], relations=[])
    assert again["entities"] == ["e"] and again["recovery_folded"] == ["b0"]


def test_filter_fanout_folds_tasks_accumulates_verdicts_then_persists():
    rs = d.begin_filter(_rs(has_filter=True),
                        {"entity:0": "je", "relation:0": "jr"})
    assert rs["stage"] == d.FILTER and d.filter_task_for_job(rs, "jr") == "relation:0"
    rs = d.fold_filter_task(rs, "entity:0", "entity", {0: "supported", 1: "unsupported"})
    assert not d.filter_complete(rs) and rs["stage"] == d.FILTER
    rs = d.fold_filter_task(rs, "relation:0", "relation", {0: "supported"})
    assert d.filter_complete(rs) and rs["stage"] == d.PERSIST
    # verdicts accumulated per category (idx keys stringified for JSON)
    assert rs["filter_verdicts"]["entity"] == {"0": "supported", "1": "unsupported"}
    assert rs["filter_verdicts"]["relation"] == {"0": "supported"}


def test_filter_fold_idempotent_on_duplicate_task():
    rs = d.begin_filter(_rs(has_filter=True), {"entity:0": "je"})
    rs = d.fold_filter_task(rs, "entity:0", "entity", {0: "supported"})
    again = d.fold_filter_task(rs, "entity:0", "entity", {0: "unsupported"})
    assert again["filter_verdicts"]["entity"] == {"0": "supported"}  # unchanged
    assert again["filter_folded"] == ["entity:0"]


def test_begin_filter_empty_goes_straight_to_persist():
    rs = d.begin_filter(_rs(has_filter=True), {})
    assert rs["stage"] == d.PERSIST


def test_candidates_dict_assembles_accumulators():
    rs = _rs()
    rs["entities"] = ["e"]; rs["relations"] = ["r"]; rs["events"] = ["v"]; rs["facts"] = ["f"]
    assert d.candidates_dict(rs) == {
        "entities": ["e"], "relations": ["r"], "events": ["v"], "facts": ["f"],
    }


# ── WX-T3b shell (submit-assembly + fold-dispatch + serde) ─────────────────────

def test_shell_entity_to_trio_to_persist_roundtrip():
    """The shell drives entity → trio fan-in → persist over the SDK seams, storing
    candidates SERIALIZED (JSON-safe) in rs and reconstructing them for persist."""
    rs = _seed_shell_rs()

    ek = d.assemble_entity_submit(rs)
    assert ek["operation"] == "entity_extraction" and ek["model_ref"] == "m"

    rs = d.fold_entity_job(rs, _job({"entities": [{"name": "Kai", "kind": "person", "confidence": 0.9}]}))
    assert rs["stage"] == d.TRIO
    assert "Kai" in rs["all_known"]
    assert isinstance(rs["entities"][0], dict)  # serialized for JSONB

    ts = d.assemble_trio_submits(rs)
    assert set(ts) == {"relation", "event", "fact"}
    assert ts["relation"]["operation"] == "relation_extraction"

    rs = d.begin_trio(rs, {"relation": "jr", "event": "je", "fact": "jf"})
    rs = d.fold_trio_job(rs, "relation", _job({"relations": []}))
    rs = d.fold_trio_job(rs, "event", _job({"events": []}))
    assert rs["stage"] == d.TRIO  # still waiting on fact
    rs = d.fold_trio_job(rs, "fact", _job({"facts": []}))
    assert rs["stage"] == d.PERSIST and d.trio_complete(rs)

    cands = d.reconstruct_candidates(rs)
    assert [e.name for e in cands.entities] == ["Kai"]


def test_shell_empty_entities_short_circuits_to_persist():
    rs = d.fold_entity_job(_seed_shell_rs(), _job({"entities": []}))
    assert rs["stage"] == d.PERSIST  # no entities → nothing to anchor
    assert d.reconstruct_candidates(rs).entities == []
