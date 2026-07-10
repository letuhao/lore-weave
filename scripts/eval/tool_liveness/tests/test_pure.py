"""Unit tests for the PURE (no-I/O) parts of the TLE harness — safe to run without
a live stack. Covers the SSE fold, confirm-token/job-id detection, domain routing,
and the matrix status logic. These are the parsers that silently corrupt a run if
wrong, so they are pinned here.

Run: python -m pytest scripts/eval/tool_liveness/tests/test_pure.py -q
"""
from __future__ import annotations

import json

from scripts.eval.tool_liveness import matrix
from scripts.eval.tool_liveness.confirm import domain_of, find_confirm_token
from scripts.eval.tool_liveness.poller import find_job_id, status_of
from scripts.eval.tool_liveness.sse import fold_events


def _agui_tool(cid, name, argstr, result_env):
    return [
        {"type": "TOOL_CALL_START", "toolCallId": cid, "toolCallName": name},
        {"type": "TOOL_CALL_ARGS", "toolCallId": cid, "delta": argstr},
        {"type": "TOOL_CALL_RESULT", "toolCallId": cid, "content": json.dumps(result_env)},
    ]


def test_fold_events_captures_args_ok_result():
    events = [{"type": "TEXT_MESSAGE_CONTENT", "delta": "Sure, "},
              {"type": "TEXT_MESSAGE_CONTENT", "delta": "done."}]
    events += _agui_tool("c1", "book_create", '{"title":"X"}',
                         {"ok": True, "result": {"book_id": "b-1"}})
    folded = fold_events(events)
    assert folded["assistant"] == "Sure, done."
    assert len(folded["tools"]) == 1
    tc = folded["tools"][0]
    assert tc["tool"] == "book_create"
    assert tc["args"] == {"title": "X"}
    assert tc["ok"] is True
    assert tc["result"] == {"book_id": "b-1"}


def test_fold_events_split_arg_deltas():
    events = [{"type": "TOOL_CALL_START", "toolCallId": "c", "toolCallName": "t"},
              {"type": "TOOL_CALL_ARGS", "toolCallId": "c", "delta": '{"a":'},
              {"type": "TOOL_CALL_ARGS", "toolCallId": "c", "delta": '1}'},
              {"type": "TOOL_CALL_RESULT", "toolCallId": "c",
               "content": json.dumps({"ok": False, "error": "boom"})}]
    tc = fold_events(events)["tools"][0]
    assert tc["args"] == {"a": 1}
    assert tc["ok"] is False
    assert tc["error"] == "boom"


def test_find_confirm_token_nested():
    assert find_confirm_token({"result": {"confirm_token": "TOK"}}) == "TOK"
    assert find_confirm_token({"a": [{"b": {"confirmToken": "T2"}}]}) == "T2"
    assert find_confirm_token({"ok": True, "result": {"book_id": "x"}}) is None


def test_find_job_id_and_status():
    assert find_job_id({"result": {"job_id": "J1"}}) == "J1"
    assert find_job_id({"x": [{"generation_job_id": "G"}]}) == "G"
    assert status_of({"status": "COMPLETED"}) == "completed"
    assert status_of({"state": "Running"}) == "running"
    assert status_of({"nope": 1}) is None


def test_domain_of():
    assert domain_of("glossary_propose_new_kind") == "glossary"
    assert domain_of("book_chapter_publish") == "book"
    assert domain_of("kg_build_graph") == "knowledge"
    assert domain_of("plan_compile") == "composition"


def test_matrix_status():
    assert matrix.status_for({"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS"}) == "PASS"
    assert matrix.status_for({"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "RED"}) == "RED"
    assert matrix.status_for({"G1": "RED"}) == "RED"
    assert matrix.status_for({"status": "UNTESTED-PAID"}) == "UNTESTED-PAID"


def test_matrix_render_smoke():
    rows = [{"id": "A1", "tool": "book_create", "service": "book", "tier": "A",
             "async": False, "paid": False, "probe": "make a book",
             "G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS",
             "status": "PASS", "evidence": {"readback": {"created_book_id": "b"}}}]
    md = matrix.render_md(rows, {"date": "2026-07-10", "gateway": "x", "model_ref": "m"})
    assert "book_create" in md and "G4 effect" in md and "1/1 PASS" in md


# ── RED-SELECT vs RED-CAPABILITY (the F6 lesson) ────────────────────────────────
#
# A G1 miss used to short-circuit the probe, so the tool was never exercised and a
# *selection* failure was indistinguishable from a *capability* failure. kg_build_graph
# was scored "RED — model did not call it" while it ALSO could not have succeeded: the
# embedding-model setup step existed only as a REST route behind a GUI dialog. One label
# hid a product bug behind a model excuse.

def test_g1_miss_with_working_tool_is_red_select_not_bare_red():
    row = {"G1": "RED", "G2": None, "G3": None, "G4": None, "capability": "PASS"}
    assert matrix.status_for(row) == "RED-SELECT"


def test_g1_miss_with_broken_tool_is_red_capability():
    """This is the cell the CD4 ship gate must BLOCK on."""
    row = {"G1": "RED", "G2": None, "G3": None, "G4": None, "capability": "RED"}
    assert matrix.status_for(row) == "RED-CAPABILITY"


def test_g1_miss_with_unknown_capability_stays_bare_red():
    """A paid tool (never re-probed) or one with no authored args must NOT be laundered
    into RED-SELECT — 'we didn't check' is not 'the tool works'."""
    for cap in ("SKIP-PAID", "SKIP-NO-ARGS", None):
        row = {"G1": "RED", "G2": None, "G3": None, "G4": None, "capability": cap}
        assert matrix.status_for(row) == "RED", cap


def test_capability_never_masks_a_downstream_gate_failure():
    """If the model DID select the tool and a later gate failed, capability is irrelevant —
    the row is a plain RED. A passing capability re-probe must not turn a real G3/G4
    failure into RED-SELECT."""
    row = {"G1": "PASS", "G2": "PASS", "G3": "RED", "G4": None, "capability": "PASS"}
    assert matrix.status_for(row) == "RED"


def test_all_pass_is_unaffected_by_capability_field():
    row = {"G1": "PASS", "G2": "PASS", "G3": "PASS", "G4": "PASS"}
    assert matrix.status_for(row) == "PASS"


def test_is_red_covers_every_red_flavor():
    for s in ("RED", "RED-SELECT", "RED-CAPABILITY"):
        assert matrix.is_red(s)
    for s in ("PASS", "PARTIAL", "UNTESTED-PAID", "WAIVED"):
        assert not matrix.is_red(s)


def test_every_probe_has_a_direct_arg_builder_or_is_paid():
    """A probe with no `direct` builder can never be capability-scored, so its G1 miss is
    permanently ambiguous. Adding a probe without one is a silent coverage hole."""
    from tool_liveness import probes as probes_mod

    missing = [p["id"] for p in probes_mod.build_probes() if "direct" not in p]
    assert not missing, f"probes with no deterministic `direct` args: {missing}"


def test_direct_builders_are_uniform_arity_and_fixture_scoped():
    """All builders take (fx, harness). A mismatched signature only explodes at runtime,
    after a live model turn has already been spent."""
    import inspect

    from tool_liveness import probes as probes_mod

    for p in probes_mod.build_probes():
        sig = inspect.signature(p["direct"])
        assert len(sig.parameters) == 2, f"{p['id']}: direct{sig} must take (fx, harness)"
        if "setup" in p:
            assert len(inspect.signature(p["setup"]).parameters) == 2, p["id"]


# ── the capability sweep's classifier (sweep.py) ────────────────────────────────
#
# An `executes: false` BLOCKS the tool from every workflow and hides it from tool_list.
# So the classifier must be conservative — but widening it must not swallow the real bug
# it was built to find. Both directions are pinned here with the ACTUAL messages observed
# in the 2026-07-10 sweep.

def test_sweep_classifier_scores_our_own_bad_args_as_inconclusive():
    """The first sweep scored 10 healthy tools 'broken' because it handed them a
    placeholder where they wanted a UUID or an existing kind-code. Those are our bugs."""
    from tool_liveness.sweep import classify

    caller_fault = [
        "Error executing tool composition_motif_get: badly formed hexadecimal UUID string",
        "Error executing tool composition_get_work: pass project_id or book_id",
        "no live genre with that code in this book",
        "unknown kind: tle-sweep",
        'Error executing tool kg_world_query: {"message": "world_id is not a valid id: \'tle-sweep\'"}',
        "Error executing tool plan_validate: badly formed hexadecimal UUID string",
        "book_id is required",
        "only the project's owner can set its embedding model",
        # observed in the Tier-A write sweep: we called with ONLY the required args, so
        # there was nothing to change. The tool is right to refuse. Scoring this broken
        # would have blocked book_chapter_update_meta from every workflow.
        "no fields to update",
    ]
    for msg in caller_fault:
        executes, why = classify(False, msg)
        assert executes is None, f"must be INCONCLUSIVE, not broken: {msg!r} -> {why}"


def test_sweep_classifier_still_catches_the_real_bug_it_was_built_to_find():
    """settings_get_profile declared its `profile` field as null|array (json.RawMessage is
    []byte) while returning an object, so the SDK rejected the tool's OWN output — 100% of
    calls, for every user. The classifier must NOT launder this into 'inconclusive'."""
    from tool_liveness.sweep import classify

    real = (
        "tool 'settings_get_profile' failed: rejected by the owning service: validating "
        'tool output: validating root: validating /properties/profile: type: map[...] '
        'has type "object", want one of "null, array"'
    )
    executes, why = classify(False, real)
    assert executes is False, f"a genuine tool failure must score BROKEN, got {executes} ({why})"


def test_sweep_classifier_success_is_executes_true():
    from tool_liveness.sweep import classify

    assert classify(True, "")[0] is True


def test_sweep_refuses_to_call_a_tool_whose_ids_it_cannot_supply():
    """Refusing to call is the safe move: a placeholder id produces a lookup failure that
    says nothing about the tool. `None` means SKIP, not broken."""
    from tool_liveness.sweep import fill_args

    fx = {"book_id": "b-1"}
    # a uuid arg with no fixture value -> cannot build
    assert fill_args({"required": ["motif_id"], "properties": {"motif_id": {"type": "string"}}}, fx) is None
    # a reference code -> cannot build
    assert fill_args({"required": ["kind"], "properties": {"kind": {"type": "string"}}}, fx) is None
    # a fixture-backed id -> fine
    assert fill_args({"required": ["book_id"], "properties": {"book_id": {"type": "string"}}}, fx) == {"book_id": "b-1"}
    # an enum -> take the first
    assert fill_args({"required": ["mode"], "properties": {"mode": {"enum": ["a", "b"]}}}, fx) == {"mode": "a"}
    # free text -> a placeholder is harmless
    assert fill_args({"required": ["query"], "properties": {"query": {"type": "string"}}}, fx) == {"query": "tle-sweep"}


# ── the sweep's SAFETY filter (a bug here mutates real user data) ───────────────
#
# `_meta.scope` is the safety predicate. A Tier-A tool scoped book/project can only touch
# the throwaway fixture we hand it; one scoped user/none rewrites the real account
# (settings_update_profile) or deletes real rows (memory_forget). Paid tools must never be
# called to score a matrix cell.

def _t(name, tier, scope, paid=False):
    return {"name": name, "schema": {}, "meta": {"tier": tier, "scope": scope, **({"paid": True} if paid else {})}}


def test_sweep_never_calls_a_user_scoped_write():
    from tool_liveness.sweep import plan

    catalog = [
        _t("settings_update_profile", "A", "user"),   # would rewrite the real profile
        _t("memory_forget", "A", "user"),             # would delete real rows
        _t("glossary_propose_entities", "A", "book"), # fixture-scoped: safe
    ]
    for include_writes in (False, True):
        targets, _ = plan(catalog, include_writes=include_writes)
        names = {t["name"] for t in targets}
        assert "settings_update_profile" not in names, "a user-scoped write must NEVER be swept"
        assert "memory_forget" not in names, "a user-scoped write must NEVER be swept"


def test_sweep_calls_fixture_scoped_writes_only_when_asked():
    from tool_liveness.sweep import plan

    catalog = [_t("glossary_propose_entities", "A", "book"), _t("kg_propose_edge", "A", "project")]
    assert plan(catalog, include_writes=False)[0] == [], "writes are opt-in"
    assert len(plan(catalog, include_writes=True)[0]) == 2


def test_sweep_never_calls_a_paid_tool_even_if_it_is_a_read():
    from tool_liveness.sweep import plan

    catalog = [_t("web_search", "R", "user", paid=True), _t("glossary_deep_research", "W", "book", paid=True)]
    for include_writes in (False, True):
        assert plan(catalog, include_writes=include_writes)[0] == [], \
            "a capability probe must never spend the user's money"


def test_sweep_always_calls_reads_and_token_minting_writes():
    from tool_liveness.sweep import plan

    # Tier-W mints a confirm_token and writes nothing at call time; we never redeem it.
    catalog = [_t("book_list", "R", "user"), _t("glossary_entity_delete", "W", "book")]
    assert len(plan(catalog, include_writes=False)[0]) == 2


# ── the classifier's ORDERING, which is the whole design ────────────────────────
#
# `_CALLER_FAULT` is deliberately permissive — every false positive it kills widens it,
# and a wide regex eventually swallows a true positive. These two real bugs were laundered
# into `null` for exactly that reason: the first matched on `missing`/`required`, the
# second on `does not exist`. An explicit "the tool leaked its own internals" signal must
# be checked FIRST and must win.

def test_a_python_typeerror_is_the_tools_fault_not_ours():
    """kg_entity_edge_timeline: run_read() missing 1 required positional argument: 'user_id'.
    Reproduces unconditionally — the tool can never work. It must NOT be laundered by the
    `missing`/`required` alternatives in the caller-fault regex."""
    from tool_liveness.sweep import classify

    msg = ("Error executing tool kg_entity_edge_timeline: run_read() missing 1 required "
           "positional argument: 'user_id'")
    executes, why = classify(False, msg)
    assert executes is False, f"a Python TypeError is a product bug, got {executes} ({why})"
    assert "internal" in why


def test_a_sql_schema_error_is_the_tools_fault_not_ours():
    """translation_list_versions: column ct.model_source does not exist. Must not be
    laundered by the `does not exist` alternative (which exists to absorb 'entity does not
    exist')."""
    from tool_liveness.sweep import classify

    msg = "Error executing tool translation_list_versions: column ct.model_source does not exist"
    executes, why = classify(False, msg)
    assert executes is False, f"a SQL schema error is a product bug, got {executes} ({why})"


def test_broken_requires_positive_evidence_never_exclusion():
    """The design, in one test. An unrecognised failure is `null`, never `false`.

    The old design scored broken-by-exclusion (anything not matching a caller-fault regex).
    That regex needed widening four times and twice swallowed a real bug. `executes: false`
    blocks a tool from every workflow; a missed detection blocks nothing. So: enumerate the
    bounded vocabulary of TOOL failure, attribute everything else to ourselves."""
    from tool_liveness.sweep import classify

    # an error we have never seen before, in nobody's vocabulary
    assert classify(False, "the flux capacitor declined")[0] is None
    # and the settings_get_profile break must STILL be caught, or the inversion cost us it
    assert classify(False, 'validating tool output: want one of "null, array"')[0] is False


def test_a_missing_row_is_still_inconclusive_not_broken():
    """`does not exist` must keep absorbing genuine not-found errors — the internal regex
    is anchored on `column`/`relation`, not the bare phrase."""
    from tool_liveness.sweep import classify

    for msg in ("entity does not exist", "that book does not exist", "no such chapter"):
        assert classify(False, msg)[0] is None, msg


def test_go_panics_and_nil_derefs_are_the_tools_fault():
    from tool_liveness.sweep import classify

    for msg in ("panic: runtime error: invalid memory address",
                "runtime error: nil pointer dereference",
                "index out of range [3] with length 2"):
        assert classify(False, msg)[0] is False, msg


def test_fill_args_supplies_optional_scope_keys_the_fixture_holds():
    """13 kg_* tools declare `project_id` OPTIONAL (it normally rides the X-Project-Id
    envelope) and then refuse with "no project in scope". A required-args-only call never
    exercised them. Supplying an optional scope key we hold is the same value the envelope
    would have carried."""
    from tool_liveness.sweep import fill_args

    schema = {"required": ["entity_id"],
              "properties": {"entity_id": {"type": "string"},
                             "project_id": {"type": "string"},
                             "limit": {"type": "integer"}}}
    fx = {"entity_id": "e-1", "project_id": "p-1"}
    args = fill_args(schema, fx)
    assert args == {"entity_id": "e-1", "project_id": "p-1"}, args
    assert "limit" not in args, "only SCOPE keys are auto-supplied, not every optional"


def test_fill_args_does_not_invent_a_scope_key_the_fixture_lacks():
    from tool_liveness.sweep import fill_args

    schema = {"required": [], "properties": {"project_id": {"type": "string"}}}
    assert fill_args(schema, {"book_id": "b-1"}) == {}
