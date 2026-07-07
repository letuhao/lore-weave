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


# ── L7 Milestone B — advisory schema threaded into the decoupled submits ──


_ADVISORY_SCHEMA = {
    "entity_kinds": ["cultivator"],
    "edge_predicates": ["disciple_of", "pursues"],
    "event_kinds": [],
    "fact_types": ["realm"],
    "allow_free_edges": True,  # advisory — SDK hints, never pre-drops
    "label": "p1@v3",
    "schema_version": 3,
}


def test_schema_from_absent_returns_none():
    assert d._schema_from(_seed_shell_rs()) is None


def test_schema_from_present_builds_advisory_schema():
    rs = _seed_shell_rs()
    rs["_schema"] = _ADVISORY_SCHEMA
    sch = d._schema_from(rs)
    assert sch is not None
    assert sch.edge_predicates == ("disciple_of", "pursues")
    assert sch.allow_free_edges is True  # never pre-drops on the SDK path


def test_entity_submit_injects_schema_vocab_into_prompt():
    """A stashed schema reaches build_entity_system → its vocab appears in the
    submitted system prompt (the LLM gets the project's node-kinds as a hint)."""
    rs = _seed_shell_rs()
    rs["_schema"] = _ADVISORY_SCHEMA
    ek = d.assemble_entity_submit(rs)
    system = ek["input"]["messages"][0]["content"]
    assert "cultivator" in system


def test_trio_submits_inject_edge_vocab_into_relation_prompt():
    rs = _seed_shell_rs()
    rs["_schema"] = _ADVISORY_SCHEMA
    rs = d.fold_entity_job(rs, _job({"entities": [{"name": "Kai", "kind": "person", "confidence": 0.9}]}))
    ts = d.assemble_trio_submits(rs)
    rel_system = ts["relation"]["input"]["messages"][0]["content"]
    assert "disciple_of" in rel_system


def test_entity_submit_no_schema_omits_vocab():
    """Back-compat: no stashed schema → the static prompt (no injected vocab)."""
    ek = d.assemble_entity_submit(_seed_shell_rs())
    system = ek["input"]["messages"][0]["content"]
    assert "cultivator" not in system


# ── Model-context-aware chunk sizing ────────────────────────────────────────


def test_context_budget_from_absent_is_none():
    """No context_length stashed (unresolved, or a legacy resume blob) → the SDK's
    legacy flat chunk size, never a guessed window."""
    assert d._context_budget_from(_seed_shell_rs()) is None


def test_context_budget_from_builds_real_budget():
    rs = _seed_shell_rs()
    rs["context_length"] = 1_000_000
    budget = d._context_budget_from(rs)
    assert budget is not None
    assert budget.model_context == 1_000_000


def test_entity_submit_uses_stashed_context_length_not_flat_default():
    """A 1M-context model must NOT get the same chunk size a small-window model
    would — the exact bug class a hardcoded/omitted context_budget reintroduces."""
    small = _seed_shell_rs()
    small["context_length"] = 24_000
    huge = _seed_shell_rs()
    huge["context_length"] = 1_000_000

    small_chunk = d.assemble_entity_submit(small)["chunking"].size
    huge_chunk = d.assemble_entity_submit(huge)["chunking"].size
    default_chunk = d.assemble_entity_submit(_seed_shell_rs())["chunking"].size
    assert huge_chunk > small_chunk
    assert default_chunk == 15  # unresolved context_length ⇒ legacy flat default


def test_trio_submits_use_stashed_context_length():
    no_budget = d.assemble_trio_submits(
        d.fold_entity_job(_seed_shell_rs(), _job({"entities": [{"name": "Kai", "kind": "person", "confidence": 0.9}]})),
    )
    rs = _seed_shell_rs()
    rs["context_length"] = 1_000_000
    rs = d.fold_entity_job(rs, _job({"entities": [{"name": "Kai", "kind": "person", "confidence": 0.9}]}))
    ts = d.assemble_trio_submits(rs)

    assert no_budget["relation"]["chunking"].size == 15  # legacy flat default
    assert ts["relation"]["chunking"].size > no_budget["relation"]["chunking"].size


def test_shell_trio_serde_roundtrips_nonempty():
    """review-impl finding 5 — non-empty relation/event/fact serde: model_dump(mode='json')
    ↔ model_validate through the resume_state JSONB must round-trip (the prior shell test
    only covered EMPTY trio results, so a candidate-model shape issue would slip to live)."""
    rs = _seed_shell_rs()
    # two entities so the relation resolves both endpoints (survives _postprocess)
    rs = d.fold_entity_job(rs, _job({"entities": [
        {"name": "Kai", "kind": "person", "confidence": 0.9},
        {"name": "Bob", "kind": "person", "confidence": 0.9},
    ]}))
    rs = d.begin_trio(rs, {"relation": "jr", "event": "je", "fact": "jf"})
    rs = d.fold_trio_job(rs, "relation", _job({"relations": [
        {"subject": "Kai", "predicate": "knows", "object": "Bob", "confidence": 0.8},
    ]}))
    rs = d.fold_trio_job(rs, "event", _job({"events": [
        {"name": "Meeting", "summary": "Kai meets Bob", "participants": ["Kai", "Bob"],
         "kind": "action", "confidence": 0.8},
    ]}))
    rs = d.fold_trio_job(rs, "fact", _job({"facts": [
        {"content": "Kai is brave", "type": "trait", "confidence": 0.7},
    ]}))
    assert rs["stage"] == d.PERSIST
    # accumulators are JSON-safe dicts in resume_state
    assert all(isinstance(x, dict) for x in rs["relations"] + rs["events"] + rs["facts"])
    # the relation survives postprocess (both endpoints are entities) AND round-trips
    # back to a typed object for persist_pass2 — the end-to-end serde proof.
    cands = d.reconstruct_candidates(rs)
    assert any(r.subject == "Kai" and r.object == "Bob" for r in cands.relations)
    # events/facts serde must not raise on reconstruct (counts depend on postprocess)
    _ = cands.events, cands.facts


# ── WX Wave 4 shell — recovery + filter fan-out over the WX-T2c seams ───────────

def _entity(name, cid):
    return {"name": name, "kind": "person", "aliases": [], "confidence": 0.9,
            "canonical_name": name.lower(), "canonical_id": cid}


def _relation(subj, obj, rid):
    return {"subject": subj, "predicate": "saw", "object": obj, "polarity": "affirm",
            "modality": "actual", "confidence": 0.8, "subject_id": None,
            "object_id": None, "relation_id": rid}


def _recovery_rs():
    rs = d.new_extract_state(chunk_text="Kai saw a Ghost.", known_entities=[],
                             has_recovery=True, has_filter=False)
    rs.update(user_id="11111111-1111-1111-1111-111111111111", project_id=None,
              model_source="user_model", model_ref="m", stage=d.RECOVERY)
    rs["_recovery_cfg"] = {"model_ref": "rec-model", "model_source": "user_model",
                           "max_items_per_batch": 5, "transient_retry_budget": 1,
                           "known_entity_kinds": {}}
    rs["entities"] = [_entity("Kai", "e-kai")]
    rs["relations"] = [_relation("Kai", "Ghost", "r1")]  # "Ghost" unmatched → Tier-3
    return rs


def test_assemble_recovery_builds_tier3_batch_for_unmatched_name():
    submits, rs = d.assemble_recovery(_recovery_rs())
    assert list(submits) == ["r0"]
    assert submits["r0"]["operation"] == "chat"
    assert submits["r0"]["model_ref"] == "rec-model"
    assert rs["recovery_batch_names"]["r0"] == ["Ghost"]
    assert rs["recovery_base_entities"] and rs["recovery_promoted"] == []


def test_assemble_recovery_clamps_output_to_stashed_context_length():
    # A window small enough that 80% of it is BELOW the flat 1024+200*n_items
    # budget for this one-name batch (1224) — the clamp must actually bite.
    rs = _recovery_rs()
    rs["context_length"] = 1000
    submits, _ = d.assemble_recovery(rs)
    assert submits["r0"]["input"]["max_tokens"] == int(1000 * 0.8)


def test_fold_recovery_promotes_entity_verdict():
    _submits, rs = d.assemble_recovery(_recovery_rs())
    rs = d.begin_recovery(rs, {"r0": "j0"})
    job = _job({"messages": [{"content":
        '{"decisions":[{"idx":0,"verdict":"entity","kind":"person"}]}'}]})
    rs = d.fold_recovery_terminal(rs, "r0", job)
    assert d.recovery_complete(rs) and rs["stage"] == d.PERSIST  # no filter
    names = [e["name"] for e in rs["entities"]]
    assert names == ["Kai", "Ghost"]                 # Ghost promoted
    assert len(rs["relations"]) == 1                 # relation kept (not abstract)


def test_fold_recovery_drops_abstract_relations():
    _submits, rs = d.assemble_recovery(_recovery_rs())
    rs = d.begin_recovery(rs, {"r0": "j0"})
    job = _job({"messages": [{"content": '{"decisions":[{"idx":0,"verdict":"abstract"}]}'}]})
    rs = d.fold_recovery_terminal(rs, "r0", job)
    assert [e["name"] for e in rs["entities"]] == ["Kai"]   # nothing promoted
    assert rs["relations"] == []                            # abstract-Ghost relation dropped


def test_fold_recovery_idempotent_on_duplicate_batch():
    _submits, rs = d.assemble_recovery(_recovery_rs())
    rs = d.begin_recovery(rs, {"r0": "j0"})
    job = _job({"messages": [{"content":
        '{"decisions":[{"idx":0,"verdict":"entity","kind":"person"}]}'}]})
    rs = d.fold_recovery_terminal(rs, "r0", job)
    again = d.fold_recovery_terminal(rs, "r0", job)  # dup terminal
    assert [e["name"] for e in again["entities"]] == ["Kai", "Ghost"]  # not double-promoted


def test_recovery_accumulates_promoted_across_two_batches():
    """The cross-fold accumulator (recovery_promoted/name_verdict) must survive batch→
    batch: with max_items_per_batch=1 + two unmatched names, the 2nd fold reads the 1st
    fold's promoted set and APPENDS — the riskiest part of the multi-batch decouple. Each
    fold recomputes entities from the immutable base, so the final reflects BOTH."""
    rs = _recovery_rs()
    rs["_recovery_cfg"]["max_items_per_batch"] = 1
    rs["relations"] = [_relation("Kai", "Ghost", "r1"), _relation("Kai", "Wraith", "r2")]
    submits, rs = d.assemble_recovery(rs)
    assert set(submits) == {"r0", "r1"}                      # 2 single-name batches
    rs = d.begin_recovery(rs, {"r0": "j0", "r1": "j1"})

    ent = lambda name: _job({"messages": [{"content":
        f'{{"decisions":[{{"idx":0,"verdict":"entity","kind":"person"}}]}}'}]})
    rs = d.fold_recovery_terminal(rs, "r0", ent("Ghost"))
    assert not d.recovery_complete(rs) and rs["stage"] == d.RECOVERY  # 1/2, stays
    assert [e["name"] for e in rs["entities"]] == ["Kai", "Ghost"]
    rs = d.fold_recovery_terminal(rs, "r1", ent("Wraith"))
    assert d.recovery_complete(rs) and rs["stage"] == d.PERSIST
    # BOTH promoted — the 2nd fold did not clobber the 1st's accumulator
    assert [e["name"] for e in rs["entities"]] == ["Kai", "Ghost", "Wraith"]


def _filter_rs(categories=("entity",)):
    rs = d.new_extract_state(chunk_text="text", known_entities=[],
                             has_recovery=False, has_filter=True)
    rs.update(user_id="u", project_id="p", model_source="user_model", model_ref="m",
              stage=d.FILTER)
    rs["_filter_cfg"] = {"model_ref": "flt-model", "model_source": "user_model",
                         "partial_policy": "keep", "categories": list(categories),
                         "max_items_per_batch": 3, "transient_retry_budget": 1}
    rs["entities"] = [_entity("Kai", "e-kai"), _entity("Ghost", "e-ghost")]
    rs["relations"] = [_relation("Kai", "Ghost", "r1")]
    return rs


def test_assemble_filter_builds_category_batches():
    submits, rs = d.assemble_filter(_filter_rs())
    assert list(submits) == ["f:entity:0"]
    assert submits["f:entity:0"]["model_ref"] == "flt-model"
    assert rs["filter_n_input"]["entity"] == 2
    assert rs["filter_batch_meta"]["f:entity:0"]["category"] == "entity"


def test_assemble_filter_clamps_output_to_stashed_context_length():
    # A window small enough that 80% of it is BELOW the flat 1536+256*n_items
    # budget for this two-item batch (2048) — the clamp must actually bite.
    rs = _filter_rs()
    rs["context_length"] = 1000
    submits, _ = d.assemble_filter(rs)
    assert submits["f:entity:0"]["input"]["max_tokens"] == int(1000 * 0.8)


def test_fold_filter_then_finalize_keeps_supported_only():
    submits, rs = d.assemble_filter(_filter_rs())
    rs = d.begin_filter(rs, {"f:entity:0": "j0"})
    job = _job({"messages": [{"content":
        '{"verdicts":[{"idx":0,"verdict":"supported"},{"idx":1,"verdict":"unsupported"}]}'}]})
    rs = d.fold_filter_terminal(rs, "f:entity:0", job)
    assert d.filter_complete(rs) and rs["stage"] == d.PERSIST
    rs = d.finalize_filter(rs)
    assert [e["name"] for e in rs["entities"]] == ["Kai"]  # idx0 supported kept, idx1 dropped
    assert len(rs["relations"]) == 1                        # relation category not filtered


def test_fold_filter_idempotent_on_duplicate_task():
    submits, rs = d.assemble_filter(_filter_rs())
    rs = d.begin_filter(rs, {"f:entity:0": "j0"})
    job = _job({"messages": [{"content": '{"verdicts":[{"idx":0,"verdict":"supported"}]}'}]})
    rs = d.fold_filter_terminal(rs, "f:entity:0", job)
    again = d.fold_filter_terminal(rs, "f:entity:0", job)
    assert again["filter_verdicts"]["entity"] == {"0": "supported"}
    assert again["filter_folded"] == ["f:entity:0"]


def test_finalize_filter_unjudged_kept_under_keep_policy():
    submits, rs = d.assemble_filter(_filter_rs())
    rs = d.begin_filter(rs, {"f:entity:0": "j0"})
    # empty verdicts → both idx unjudged → keep policy keeps both
    job = _job({"messages": [{"content": '{"verdicts":[]}'}]})
    rs = d.fold_filter_terminal(rs, "f:entity:0", job)
    rs = d.finalize_filter(rs)
    assert [e["name"] for e in rs["entities"]] == ["Kai", "Ghost"]


# ── C12 — target-typed extraction (decoupled state machine) ────────────────────

def _rs_targets(targets, has_recovery=False, has_filter=False):
    return d.new_extract_state(
        chunk_text="text", known_entities=["A"],
        has_recovery=has_recovery, has_filter=has_filter, targets=targets,
    )


def test_c12_targets_none_runs_all_trio():
    rs = _rs_targets(None)
    assert set(rs["trio_targets"]) == set(d.TRIO_OPS)


def test_c12_targets_events_only_trio_subset():
    rs = _rs_targets(["entities", "events"])
    assert rs["trio_targets"] == ["event"]


def test_c12_entity_to_trio_completes_on_subset_only():
    """An events-only build advances past trio after ONLY the event op folds —
    it must NOT hang waiting for relation/fact (never submitted)."""
    rs = d.apply_entity_result(_rs_targets(["entities", "events"]), ["e1"])
    assert rs["stage"] == d.TRIO
    rs = d.begin_trio(rs, {"event": "je"})
    rs = d.fold_trio_op(rs, "event", ["ev"])
    assert d.trio_complete(rs)
    assert rs["stage"] == d.PERSIST
    assert rs["events"] == ["ev"]
    assert rs["relations"] == [] and rs["facts"] == []


def test_c12_entities_only_skips_trio_entirely():
    rs = d.apply_entity_result(_rs_targets(["entities"]), ["e1"])
    assert rs["trio_targets"] == []
    assert rs["stage"] == d.PERSIST


def test_c12_assemble_trio_submits_only_requested_ops():
    rs = _seed_shell_rs()
    rs["trio_targets"] = ["event"]
    rs = d.fold_entity_job(rs, _job({"entities": [
        {"name": "Kai", "kind": "person", "confidence": 0.9},
    ]}))
    assert rs["stage"] == d.TRIO
    ts = d.assemble_trio_submits(rs)
    assert set(ts) == {"event"}


def test_c12_relations_target_resolves_relation_op():
    rs = _rs_targets(["relations"])
    assert rs["trio_targets"] == ["relation"]


def test_c12_entities_only_with_recovery_advances_to_recovery_not_persist():
    """Regression (adversary MAJOR): an entities-only build (no trio target)
    with recovery enabled must advance ENTITY → RECOVERY, NOT straight to
    PERSIST (which would silently drop recovery)."""
    rs = d.apply_entity_result(
        _rs_targets(["entities"], has_recovery=True), ["e1"])
    assert rs["trio_targets"] == []
    assert rs["stage"] == d.RECOVERY


def test_c12_entities_only_with_filter_only_advances_to_filter():
    rs = d.apply_entity_result(
        _rs_targets(["entities"], has_filter=True), ["e1"])
    assert rs["stage"] == d.FILTER


def test_c12_entities_only_no_recovery_no_filter_persists():
    rs = d.apply_entity_result(_rs_targets(["entities"]), ["e1"])
    assert rs["stage"] == d.PERSIST


def test_c12_legacy_rs_without_trio_targets_defaults_all():
    """A pre-C12 resume blob (no trio_targets key) ⇒ all three (back-compat)."""
    rs = d.new_extract_state(
        chunk_text="t", known_entities=[], has_recovery=False, has_filter=False,
    )
    del rs["trio_targets"]
    rs = d.apply_entity_result(rs, ["e1"])
    rs = d.begin_trio(rs, {"relation": "jr", "event": "je", "fact": "jf"})
    rs = d.fold_trio_op(rs, "relation", ["re"])
    rs = d.fold_trio_op(rs, "event", ["ev"])
    assert not d.trio_complete(rs)  # still needs fact (legacy = all three)
    rs = d.fold_trio_op(rs, "fact", ["fa"])
    assert d.trio_complete(rs)


# ── D-KG-WORKER-GRADED-EFFORT — graded effort survives the resume_state ─────


def test_graded_effort_in_resume_state_reaches_entity_submit():
    """A reasoning_effort stashed in resume_state spreads the reasoning wire
    fields into the entity submit the consumer rebuilds on resume."""
    rs = _seed_shell_rs()
    rs["reasoning_effort"] = "high"
    ek = d.assemble_entity_submit(rs)
    assert ek["input"]["reasoning_effort"] == "high"
    assert ek["input"]["chat_template_kwargs"] == {
        "thinking": True, "enable_thinking": True,
    }


def test_graded_effort_in_resume_state_reaches_trio_submits():
    rs = _seed_shell_rs()
    rs["reasoning_effort"] = "high"
    rs = d.fold_entity_job(rs, _job({"entities": [
        {"name": "Kai", "kind": "person", "confidence": 0.9},
    ]}))
    ts = d.assemble_trio_submits(rs)
    for op in ("relation", "event", "fact"):
        assert ts[op]["input"]["reasoning_effort"] == "high"


def test_absent_effort_in_resume_state_omits_wire_fields():
    """A legacy/pre-effort resume blob (no reasoning_effort key) ⇒ no wire
    fields, byte-identical to the historical decoupled submit."""
    ek = d.assemble_entity_submit(_seed_shell_rs())
    assert "reasoning_effort" not in ek["input"]
    assert "chat_template_kwargs" not in ek["input"]


def test_recovery_submit_stays_force_off_under_graded_effort():
    """D1 carve-out drift-lock: the recovery classifier is a cheap structural
    pass that must NOT inherit graded effort — its thinking stays force-OFF and
    it carries no reasoning_effort, even when the job runs at high effort."""
    rs = _recovery_rs()
    rs["reasoning_effort"] = "high"
    submits, _ = d.assemble_recovery(rs)
    inp = submits["r0"]["input"]
    assert "reasoning_effort" not in inp
    assert inp["chat_template_kwargs"] == {"thinking": False, "enable_thinking": False}
