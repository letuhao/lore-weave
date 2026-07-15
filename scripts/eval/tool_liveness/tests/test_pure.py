"""Unit tests for the PURE (no-I/O) parts of the TLE harness — safe to run without
a live stack. Covers the SSE fold, confirm-token/job-id detection, domain routing,
and the matrix status logic. These are the parsers that silently corrupt a run if
wrong, so they are pinned here.

Run: python -m pytest scripts/eval/tool_liveness/tests/test_pure.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.eval.tool_liveness import matrix
from scripts.eval.tool_liveness.confirm import domain_of, find_confirm_token
from scripts.eval.tool_liveness.manifest import build
from scripts.eval.tool_liveness.poller import find_job_id, status_of
from scripts.eval.tool_liveness.sse import fold_events
from scripts.eval.tool_liveness.waivers import GATES, WAIVERS


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


def test_input_arg_validation_is_our_fault_not_the_tools():
    """A "validating arguments / validating root" error is OUR bad payload (e.g. a wrong
    array-item shape we authored), NOT the tool's output violating its schema. It must score
    null, not false — else a bad authored arg would BLOCK a healthy tool from every workflow.
    Only "validating tool OUTPUT" is the tool's fault."""
    from tool_liveness.sweep import classify

    ours = ('validating "arguments": validating root: validating /properties/chapters: '
            'validating /properties/chapters/items: unknown field')
    assert classify(False, ours)[0] is None, "input-arg validation is caller-fault → null"
    # the real OUTPUT bug (settings_get_profile) still scores false — it says "tool output"
    real = 'validating tool output: validating root: want one of "null, array"'
    assert classify(False, real)[0] is False


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


# ── $ref / $defs resolution (28 composition tools wrap their args in a $ref) ─────
#
# The composition tools declare `{"properties": {"args": {"$ref": "#/$defs/_XArgs"}},
# "$defs": {...}}`. The $defs FULLY describe the object, so it is buildable — the old
# fill_args saw `type: None` on the $ref node and refused, leaving 28 tools `null`.

def test_fill_args_resolves_a_ref_wrapped_args_object():
    from tool_liveness.sweep import fill_args

    schema = {
        "required": ["args"],
        "properties": {"args": {"$ref": "#/$defs/_MotifSearchArgs"}},
        "$defs": {"_MotifSearchArgs": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        }},
    }
    assert fill_args(schema, {}) == {"args": {"query": "tle-sweep"}}


def test_fill_args_refuses_when_the_nested_ref_needs_an_unguessable_id():
    """A model resolving the schema would find `motif_id` inside `args` and, lacking one,
    could not construct it either. The nested refusal must bubble up to a whole-call None."""
    from tool_liveness.sweep import fill_args

    schema = {
        "required": ["args"],
        "properties": {"args": {"$ref": "#/$defs/_MotifGetArgs"}},
        "$defs": {"_MotifGetArgs": {
            "type": "object", "required": ["motif_id"],
            "properties": {"motif_id": {"type": "string", "format": "uuid"}},
        }},
    }
    assert fill_args(schema, {"book_id": "b-1"}) is None


def test_fill_args_supplies_a_scope_key_inside_a_nested_args_object():
    """The composition `args` wrapper carries the scope key INSIDE the nested object, so the
    optional-scope-key injection must apply at every level, not just the top."""
    from tool_liveness.sweep import fill_args

    schema = {
        "required": ["args"],
        "properties": {"args": {"$ref": "#/$defs/_A"}},
        "$defs": {"_A": {
            "type": "object", "required": ["name"],
            "properties": {"name": {"type": "string"}, "project_id": {"type": "string"}},
        }},
    }
    args = fill_args(schema, {"project_id": "p-1"})
    assert args == {"args": {"project_id": "p-1", "name": "tle-sweep"}}, args


def test_fill_args_ref_resolution_is_cycle_safe():
    """A self-referential $ref must not hang the sweep — bail to None, never loop."""
    from tool_liveness.sweep import fill_args

    schema = {
        "required": ["args"],
        "properties": {"args": {"$ref": "#/$defs/_Loop"}},
        "$defs": {"_Loop": {"$ref": "#/$defs/_Loop"}},
    }
    assert fill_args(schema, {}) is None


# ── phase 2: the throwaway-USER sweep ───────────────────────────────────────────
#
# The 25 user/none-scoped Tier-A writes mutate THE CALLER — there is no book to hand them.
# `settings_update_profile` rewrites the profile; `glossary_user_create` adds a user-tier
# kind. Against the real test account that is vandalism, so nothing ever called them, and
# that is exactly where settings_update_profile hid its output-schema break.

def test_user_fixture_headers_never_carry_the_real_account():
    """The one invariant that must never break: phase 2 talks as the throwaway user."""
    from tool_liveness import config
    from tool_liveness.user_fixture import UserFixture

    fx = UserFixture()
    fx.user_id = "00000000-0000-0000-0000-000000000001"
    h = fx.headers()
    assert h["X-User-Id"] == fx.user_id
    assert h["X-User-Id"] != config.USER_ID, "must NOT be the real test account"


def test_user_fixture_refuses_headers_before_build():
    from tool_liveness.user_fixture import UserFixture

    with pytest.raises(AssertionError):
        UserFixture().headers()


def test_authored_user_args_supplies_the_field_settings_update_profile_needs():
    """`settings_update_profile` has required=[], so a required-args-only call returns
    "no fields to update" and proves nothing. It is THE tool whose twin was broken; it
    must be reached with an optional field supplied on purpose."""
    from tool_liveness.user_fixture import UserFixture, authored_user_args

    args = authored_user_args("settings_update_profile", UserFixture(), {})
    assert args and "display_name" in args, "must supply an optional field, or learn nothing"


def test_authored_user_args_returns_none_for_tools_needing_state_we_lack():
    """A motif id, a 2nd motif, a credential — the throwaway user has none until built, and we
    do not chain a creator for them. Returning None keeps the tool at `executes: null`."""
    from tool_liveness.user_fixture import UserFixture, authored_user_args

    fx = UserFixture()  # unbuilt: no seeded credential / model
    for tool in ("composition_motif_archive", "composition_motif_link_create", "settings_model_register"):
        assert authored_user_args(tool, fx, {}) is None, tool


def test_jobs_tools_reach_via_a_synthetic_not_found_id():
    """jobs_get/cancel/pause resolve a missing/foreign job to a structured NOT-FOUND dict
    (executes:True), never touching real data — so a synthetic job_id reaches them at $0
    without seeding a real job. They must NOT depend on any fixture state."""
    from tool_liveness.user_fixture import UserFixture, authored_user_args

    fx = UserFixture()  # unbuilt on purpose
    for tool in ("jobs_get", "jobs_cancel", "jobs_pause"):
        args = authored_user_args(tool, fx, {})
        assert args and args.get("job_id") and args.get("service"), tool


def test_credential_gated_tools_use_the_seeded_credential_and_model():
    """The 6 credential-gated tools are reachable ONLY because the fixture seeds a keyless
    provider credential + a model. With those ids present, each authors args that reference
    them; without the seed (unbuilt fixture) each returns None."""
    from tool_liveness.user_fixture import UserFixture, authored_user_args

    unbuilt = UserFixture()
    seeded = UserFixture()
    seeded.credential_id = "cred-1"
    seeded.user_model_id = "model-1"

    cred_tools = ("settings_provider_inventory", "settings_model_register")
    model_tools = ("settings_model_update", "settings_model_set_favorite",
                   "settings_model_set_active", "settings_model_delete")
    for tool in cred_tools + model_tools:
        assert authored_user_args(tool, unbuilt, {}) is None, f"{tool} must skip without seed"
    for tool in cred_tools:
        assert authored_user_args(tool, seeded, {})["provider_credential_id"] == "cred-1", tool
    for tool in model_tools:
        assert authored_user_args(tool, seeded, {})["user_model_id"] == "model-1", tool


def test_registry_slug_tools_use_the_seeded_skill_and_workflow():
    """registry_get/update/set_skill_enabled + get_workflow operate on an APPROVED row by
    slug — a proposal is not retrievable that way. With the seeded slugs present each authors
    args; without the seed (unbuilt fixture) each returns None."""
    from tool_liveness.user_fixture import UserFixture, authored_user_args

    unbuilt = UserFixture()
    seeded = UserFixture()
    seeded.skill_slug = "sk-1"
    seeded.workflow_slug = "wf-1"

    for tool in ("registry_get_skill", "registry_update_skill",
                 "registry_set_skill_enabled", "registry_get_workflow"):
        assert authored_user_args(tool, unbuilt, {}) is None, f"{tool} must skip without seed"
    assert authored_user_args("registry_get_skill", seeded, {})["slug"] == "sk-1"
    assert authored_user_args("registry_update_skill", seeded, {})["body_md"]
    assert authored_user_args("registry_set_skill_enabled", seeded, {})["enabled"] is True
    assert authored_user_args("registry_get_workflow", seeded, {})["slug"] == "wf-1"


def test_credential_gated_tools_are_all_in_the_sweep_order():
    """A seeded tool absent from USER_SWEEP_ORDER would never be swept (it keeps catalog
    order, which is fine) — but pinning them here documents the reachable set."""
    from tool_liveness.user_fixture import USER_SWEEP_ORDER as O

    for tool in ("settings_provider_inventory", "settings_model_register",
                 "settings_model_update", "settings_model_set_favorite",
                 "settings_model_set_active", "settings_model_delete"):
        assert tool in O, tool


def test_chained_tools_are_unreachable_without_the_creator_result():
    """glossary_user_patch/_delete/_restore need a `code` only glossary_user_create can
    mint. With no prior state they must return None (skip), never invent one."""
    from tool_liveness.user_fixture import UserFixture, authored_user_args

    fx = UserFixture()
    for tool in ("glossary_user_patch", "glossary_user_delete", "glossary_user_restore",
                 "kg_view_upsert", "kg_view_delete"):
        assert authored_user_args(tool, fx, {}) is None, f"{tool} must skip without state"


def test_chained_tools_consume_the_creator_result():
    from tool_liveness.user_fixture import UserFixture, authored_user_args

    fx = UserFixture()
    state = {"glossary_user_create": {"code": "tle_kind", "base_version": "v1"},
             "kg_project_create": {"project_id": "p-1"},
             "kg_view_upsert": {}}
    patch = authored_user_args("glossary_user_patch", fx, state)
    assert patch["code"] == "tle_kind" and patch["base_version"] == "v1", patch
    assert authored_user_args("glossary_user_delete", fx, state)["code"] == "tle_kind"
    assert authored_user_args("kg_view_delete", fx, state)["project_id"] == "p-1"


def test_the_chain_order_creates_before_it_consumes():
    """Sweep order is load-bearing: a delete before its create silently skips forever."""
    from tool_liveness.user_fixture import USER_SWEEP_ORDER as O

    for creator, consumer in (("glossary_user_create", "glossary_user_patch"),
                              ("glossary_user_create", "glossary_user_delete"),
                              ("glossary_user_delete", "glossary_user_restore"),
                              ("kg_project_create", "kg_view_upsert"),
                              ("kg_view_upsert", "kg_view_delete")):
        assert O.index(creator) < O.index(consumer), f"{creator} must precede {consumer}"


# ── phase 1: the book/project-scoped composition + planforge chain ──────────────
#
# composition_create_work mints the COMPOSITION project_id (distinct from the kg project),
# plan_propose_spec mints run_id (sync, rules mode), and the node/rule creators mint ids
# their update/delete twins consume. Ordering is load-bearing: a delete before its
# read/update siblings starves them.

def test_project_chain_orders_creators_before_consumers_and_deletes_last():
    from tool_liveness.project_chain import PROJECT_SWEEP_ORDER as O

    for creator, consumer in (
        ("composition_create_work", "composition_outline_node_create"),
        ("composition_create_work", "composition_canon_rule_create"),
        ("plan_propose_spec", "plan_apply_revision"),
        ("plan_propose_spec", "plan_interpret_feedback"),
        ("composition_outline_node_create", "composition_outline_node_update"),
        ("composition_canon_rule_create", "composition_canon_rule_update"),
    ):
        assert O.index(creator) < O.index(consumer), f"{creator} must precede {consumer}"
    # a delete destroys the id its read/update siblings need → it must come after them
    assert O.index("composition_outline_node_update") < O.index("composition_outline_node_delete")
    assert O.index("composition_canon_rule_update") < O.index("composition_canon_rule_delete")


def test_project_chain_creators_need_only_book_and_are_reachable():
    """The two roots need nothing but the fixture book — everything else chains from them."""
    from tool_liveness.project_chain import authored_project_args

    ids = {"book_id": "b-1"}
    assert authored_project_args("composition_create_work", ids, {})["book_id"] == "b-1"
    assert authored_project_args("plan_propose_spec", ids, {})["book_id"] == "b-1"


def test_project_chain_consumers_skip_without_the_creator_result():
    """No composition project, no run, no node/rule → each consumer returns None (skip),
    never a fabricated id."""
    from tool_liveness.project_chain import authored_project_args

    ids = {"book_id": "b-1", "project_id": "kg-1"}  # kg project is NOT the composition one
    for tool in ("composition_outline_node_create", "composition_canon_rule_create",
                 "plan_apply_revision", "composition_outline_node_update",
                 "composition_canon_rule_delete", "composition_outline_node_delete"):
        assert authored_project_args(tool, ids, {}) is None, f"{tool} must skip without state"


def test_project_chain_consumers_consume_the_minted_ids_and_versions():
    from tool_liveness.project_chain import authored_project_args

    ids = {"book_id": "b-1"}
    state = {
        "composition_create_work": {"project_id": "cproj-1"},
        "plan_propose_spec": {"run_id": "run-1"},
        "composition_outline_node_create": {"id": "node-1", "version": 3},
        "composition_canon_rule_create": {"id": "rule-1", "version": 2},
    }
    assert authored_project_args("plan_apply_revision", ids, state) == \
        {"book_id": "b-1", "run_id": "run-1"}
    upd = authored_project_args("composition_outline_node_update", ids, state)
    assert upd["args"]["node_id"] == "node-1" and upd["args"]["expected_version"] == 3
    rup = authored_project_args("composition_canon_rule_update", ids, state)
    assert rup["args"]["rule_id"] == "rule-1" and rup["args"]["expected_version"] == 2
    assert authored_project_args("composition_canon_rule_delete", ids, state)["rule_id"] == "rule-1"


def test_project_chain_uses_the_composition_project_not_the_kg_one():
    """The bug this guards: feeding the kg project_id to a composition tool fails with
    'not found or not accessible'. The chain must read the composition project minted by
    composition_create_work, never ids['project_id'] (which is the kg project)."""
    from tool_liveness.project_chain import authored_project_args

    ids = {"book_id": "b-1", "project_id": "kg-project", "chapter_id": "c-1"}
    state = {"composition_create_work": {"project_id": "composition-project"}}
    args = authored_project_args("composition_outline_node_create", ids, state)
    assert args["args"]["project_id"] == "composition-project", args


# ── the manifest MERGE (sweep + matrix → contracts/tool-liveness.json) ──────────
#
# A tool runs in more than one sweep phase, so build() sees duplicate rows. The three-valued
# `executes` must be preserved across the merge: a conclusive result must never be erased by
# a later `null`, and the matrix (a real model turn) outranks the deterministic sweep.

def test_manifest_merge_conclusive_survives_a_later_null():
    from tool_liveness.manifest import build

    # same tool: phase 1 could not reach it (null), phase 2 executed it (true). Order in the
    # list mimics phase order; the PASS must win regardless of which comes last.
    sweep_pass_last = [
        {"tool": "composition_motif_get", "executes": None},
        {"tool": "composition_motif_get", "executes": True},
    ]
    sweep_null_last = [
        {"tool": "composition_motif_get", "executes": True},
        {"tool": "composition_motif_get", "executes": None},
    ]
    for sweep in (sweep_pass_last, sweep_null_last):
        m = build([], {}, sweep)
        assert m["tools"]["composition_motif_get"]["executes"] is True, sweep


def test_manifest_merge_a_broken_result_is_never_erased_by_a_null():
    from tool_liveness.manifest import build

    m = build([], {}, [
        {"tool": "settings_get_profile", "executes": False},
        {"tool": "settings_get_profile", "executes": None},
    ])
    assert m["tools"]["settings_get_profile"]["executes"] is False


def test_manifest_matrix_outranks_the_sweep_and_sets_proven():
    from tool_liveness.manifest import build

    rows = [{"tool": "book_create", "status": "PASS", "G3": "PASS", "G4": "PASS"}]
    sweep = [{"tool": "book_create", "executes": None}]
    m = build(rows, {}, sweep)["tools"]["book_create"]
    assert m["executes"] is True and m["proven"] is True


def test_manifest_null_executes_never_read_as_false_by_blocked():
    """The load-bearing consumer predicate: `blocked` fires ONLY on explicit false."""
    from tool_liveness.manifest import blocked, build

    m = build([], {}, [{"tool": "x", "executes": None}, {"tool": "y", "executes": False}])
    assert blocked(m, "x") is False and blocked(m, "y") is True
    assert blocked(m, "absent-tool") is False


# ── step 5: the description-quality selection proxy (selection.py) ───────────────
#
# Pure parts: which synonym becomes the ask, and how an answer is scored HIT/MISS. The
# model call itself is live (validated separately). A wrong scorer would silently invert the
# whole signal, so both are pinned.

def test_selection_ask_is_the_longest_synonym_or_none():
    from tool_liveness.selection import _synonym_ask

    assert _synonym_ask({"meta": {"synonyms": ["tts", "narration", "audio"]}}) == "narration"
    assert _synonym_ask({"meta": {"synonyms": []}}) is None
    assert _synonym_ask({"meta": {}}) is None
    assert _synonym_ask({}) is None


def test_selection_scores_exact_and_tolerant_hits():
    from tool_liveness.selection import _score

    names = {"book_create", "book_get", "composition_publish"}
    # exact
    assert _score("book_create", "book_create", names)[0] == "HIT"
    # formatting noise (backticks, trailing period, quotes)
    assert _score("`book_create`.", "book_create", names)[0] == "HIT"
    assert _score('"book_create"', "book_create", names)[0] == "HIT"
    # first line only (model added an explanation on line 2)
    assert _score("book_create\nbecause the user wants a book", "book_create", names)[0] == "HIT"


def test_selection_scores_a_sibling_pick_as_a_miss_naming_the_sibling():
    from tool_liveness.selection import _score

    names = {"book_chapter_publish", "composition_publish"}
    verdict, picked = _score("composition_publish", "book_chapter_publish", names)
    assert verdict == "MISS" and picked == "composition_publish", (verdict, picked)


def test_selection_scores_an_unrecognized_answer_as_a_miss():
    from tool_liveness.selection import _score

    verdict, picked = _score("I would use the create tool", "book_create", {"book_create"})
    assert verdict == "MISS" and picked == "(unrecognized)"


# ── WS-D4: executes ∧ effect for the workflow-critical set (critical.py) ─────────
#
# The critical tools (what a curated workflow references) are held to a stronger bar than
# `executes`: their EFFECT is verified via an independent read-back. A tool that returns ok
# but whose effect does not land is a silent success — scored executes:false, so the gate
# rejects any workflow referencing it.

def test_critical_authored_refuses_the_paid_tool_and_missing_book():
    from tool_liveness.critical import _authored

    # glossary_extract_entities_from_doc is paid (an LLM extraction) — never call it at $0
    assert _authored("glossary_extract_entities_from_doc", {"book_id": "b"}) is None
    assert _authored("some_unknown_tool", {"book_id": "b"}) is None
    assert _authored("book_get", {}) is None, "no book → cannot exercise"
    assert _authored("book_get", {"book_id": "b"}) == {"book_id": "b"}
    items = _authored("glossary_propose_entities", {"book_id": "b"})
    assert items["items"] and items["items"][0]["kind"] == "character"


def test_critical_effect_detects_a_landed_effect_and_a_silent_success():
    from tool_liveness.critical import _effect

    ids = {"book_id": "b-1"}
    # book_get: the returned book must be the fixture book
    assert _effect("book_get", ids, {"book": {"book_id": "b-1"}})[0] is True
    assert _effect("book_get", ids, {"book": {"book_id": "other"}})[0] is False
    # adopt_standards (Tier W): a real confirm_token is the verifiable call-time effect
    assert _effect("glossary_adopt_standards", ids, {"confirm_token": "TOK"})[0] is True
    assert _effect("glossary_adopt_standards", ids, {"ok": True})[0] is False, \
        "ok with NO confirm_token is a silent success"
    # propose_entities: a result claiming creation but carrying no entity_id never landed
    assert _effect("glossary_propose_entities", ids, {"results": [{}]})[0] is False
    # a tool with no oracle is inconclusive, never a false pass
    assert _effect("mystery_tool", ids, {})[0] is None


def test_manifest_carries_effect_verified_and_folds_silent_success():
    """A critical row with executes:false (silent success) must REJECT via the manifest, and
    a verified effect surfaces as effect_verified:true."""
    from tool_liveness.manifest import blocked, build

    sweep = [
        {"tool": "book_get", "executes": True},  # plain sweep: executes only
        {"tool": "book_get", "executes": True, "effect_verified": True},  # critical: stronger
        {"tool": "liar", "executes": False, "effect_verified": False},    # silent success
    ]
    m = build([], {}, sweep)
    assert m["tools"]["book_get"]["effect_verified"] is True
    assert blocked(m, "liar") is True, "a silent-success critical tool must be blocked"


def test_manifest_omits_effect_verified_when_not_earned():
    from tool_liveness.manifest import build

    m = build([], {}, [{"tool": "plain", "executes": True}])
    assert "effect_verified" not in m["tools"]["plain"], "lean: only annotate what was verified"


# ── #1 build: reaching the fixture-buildable null residue ───────────────────────

def test_project_chain_glossary_direct_and_array_tools():
    from tool_liveness.project_chain import authored_project_args

    ids = {"book_id": "b", "entity_id": "e"}
    assert authored_project_args("glossary_propose_new_kind", ids, {})["code"] == "tle_probe_kind"
    attr = authored_project_args("glossary_propose_new_attribute", ids, {})
    assert attr["kind_code"] == "character" and attr["code"] == "tle_probe_attr"
    # array-item shapes mapped from the Go structs
    up = authored_project_args("glossary_ontology_upsert", ids, {})
    assert up["items"][0] == {"level": "kind", "code": "tle_upsert_kind", "name": "TLE Upsert Kind"}
    al = authored_project_args("glossary_propose_aliases", ids, {})
    assert al["items"][0]["entity_id"] == "e" and al["items"][0]["aliases"]
    batch = authored_project_args("glossary_propose_batch", ids, {})
    assert batch["ops"][0]["type"] == "create_kinds" and batch["ops"][0]["params"]["kinds"]


def test_project_chain_lower_yield_handful_authors_and_chains():
    from tool_liveness.project_chain import authored_project_args

    ids = {"book_id": "b", "chapter_id": "c", "entity_id": "e1", "entity_id2": "e2",
           "project_id": "kg-1", "authoring_run_id": "run1"}
    # authored payloads
    bulk = authored_project_args("book_chapter_bulk_create", ids, {})
    assert bulk["chapters"][0] == {"title": "TLE Bulk Chapter", "content": "TLE body"}
    assert authored_project_args("glossary_book_set_kind_genres", ids, {})["kind_code"] == "character"
    # propose_merge uses two DISTINCT fixture entities
    merge = authored_project_args("glossary_propose_merge", ids, {})
    assert merge["winner_id"] == "e1" and merge["loser_ids"] == ["e2"]
    # revert_all reuses the seeded authoring run (args-wrapped)
    assert authored_project_args("composition_authoring_run_revert_all", ids, {}) == \
        {"args": {"book_id": "b", "run_id": "run1"}}
    # memory: remember mints a fact_id (valid enum) that forget consumes
    rem = authored_project_args("memory_remember", ids, {})
    assert rem["fact_type"] == "preference" and rem["project_id"] == "kg-1"
    assert authored_project_args("memory_forget", ids, {}) is None  # no fact yet
    state = {"memory_remember": {"fact_id": "f1"}}
    assert authored_project_args("memory_forget", ids, state)["fact_id"] == "f1"


def test_project_chain_restore_revision_consumes_the_listed_revision():
    from tool_liveness.project_chain import authored_project_args

    ids = {"book_id": "b", "chapter_id": "c"}
    assert authored_project_args("book_chapter_restore_revision", ids, {}) is None
    state = {"book_list_revisions": {"revisions": [{"revision_id": "r1"}]}}
    assert authored_project_args("book_chapter_restore_revision", ids, state)["revision_id"] == "r1"


def test_project_chain_authoring_run_consumers_wrap_args_and_need_the_seed():
    """The 3 authoring-run consumers use the composition `args` envelope and the seeded
    run id; without a seeded authoring_run_id they skip (→ null, block nothing)."""
    from tool_liveness.project_chain import authored_project_args

    assert authored_project_args("composition_authoring_run_get", {"book_id": "b"}, {}) is None
    ids = {"book_id": "b", "authoring_run_id": "run1"}
    for tool in ("composition_authoring_run_get", "composition_authoring_run_gate",
                 "composition_authoring_run_close"):
        assert authored_project_args(tool, ids, {}) == {"args": {"book_id": "b", "run_id": "run1"}}


def test_seed_authoring_run_uses_a_valid_level_and_is_book_scoped():
    """authoring_runs.level has a CHECK ∈ {3,4}; the seed must use a valid one, and INSERT
    only the columns keyed to the throwaway book (teardown_composition cleans it)."""
    import inspect

    from tool_liveness import project_chain

    src = inspect.getsource(project_chain.seed_authoring_run)
    assert "INSERT INTO authoring_runs" in src
    assert ",3,'draft')" in src, "level must be 3 or 4 (CHECK constraint)"


def test_teardown_composition_is_book_scoped_and_verifies_completeness():
    """A teardown keyed on anything broader than the created book id would delete another
    user's composition rows. And it must VERIFY nothing survives — an earlier version listed
    5 tables and silently leaked a generation_job row per run."""
    import inspect

    from tool_liveness import project_chain

    src = inspect.getsource(project_chain.teardown_composition)
    # every DELETE is book-scoped; there is no unscoped `DELETE FROM x` anywhere
    assert "DELETE FROM {table} WHERE book_id='{bid}'" in src
    assert "DELETE FROM composition" not in src, "no hardcoded/unscoped table delete"
    # discovers tables at runtime (no hardcoded list to drift) and verifies no leak remains
    assert "information_schema" in src and "leaked" in src


def test_project_chain_motif_crud_is_a_phase2_user_chain_not_here():
    """The user-scoped motif CRUD (create/get/patch/archive/adopt/link_list) lives in
    user_fixture (phase 2), NOT this book-scoped module — a regression that moved it here
    would sweep it against the wrong identity. (motif_suggest_for_chapter IS book-scoped —
    it takes project_id+node_id — so it correctly stays in the phase-1 order.)"""
    from tool_liveness.project_chain import PROJECT_SWEEP_ORDER as O
    from tool_liveness.user_fixture import USER_SWEEP_ORDER as U

    user_motif_crud = ("composition_motif_create", "composition_motif_get",
                       "composition_motif_patch", "composition_motif_archive",
                       "composition_motif_adopt", "composition_motif_link_list")
    for t in user_motif_crud:
        assert t in U, f"{t} must be a phase-2 user chain"
        assert t not in O, f"{t} must NOT be in the book-scoped phase-1 chain"


def test_user_fixture_teardown_is_scoped_to_the_id_it_created():
    """A teardown keyed on anything broader than the created id would delete real rows."""
    import inspect

    from tool_liveness import user_fixture

    src = inspect.getsource(user_fixture.UserFixture.teardown)
    assert "WHERE {col}='{uid}'" in src or "WHERE id='{uid}'" in src
    assert "DELETE FROM users WHERE id='{uid}'" in src
    # every owned-row entry names an owner column — never an unscoped DELETE
    for _db, table, col in user_fixture._OWNED_ROWS:
        assert col in ("user_id", "owner_user_id"), f"{table}: unscoped owner column {col!r}"


# ── D-TRACKD-REACCOUNT: the `waived` mechanism (WS-D4 exit criterion) ──────────────
# A tool that is not `executes:true` must carry an EXPLICIT `waived:{reason,gate}` in the
# manifest — the mechanism the 2026-07-15 audit found was never built (13 waives were
# prose-only, byte-indistinguishable from un-probed). These pin its invariants.


def test_build_stamps_waived_on_a_non_executing_tool():
    out = build(rows=[], meta={}, sweep=[{"tool": "book_chapter_save_draft", "executes": None}])
    row = out["tools"]["book_chapter_save_draft"]
    assert row["executes"] is None                      # not faked to true
    assert row["waived"]["gate"] in GATES               # closed-enum gate
    assert row["waived"]["reason"].strip()              # a real reason, not empty


def test_build_never_waives_a_tool_that_executes():
    # executes:true wins — a proven tool is never stamped waived, even if it's in WAIVERS.
    out = build(rows=[], meta={}, sweep=[{"tool": "book_chapter_save_draft", "executes": True}])
    assert "waived" not in out["tools"]["book_chapter_save_draft"]


def test_build_refuses_to_waive_a_broken_tool():
    # a waiver must NEVER hide an executes:false (BROKEN) tool from the ship gate.
    with pytest.raises(ValueError, match="never hide a broken"):
        build(rows=[], meta={}, sweep=[{"tool": "book_chapter_save_draft", "executes": False}])


def test_every_waiver_has_a_closed_gate_and_a_reason():
    for tool, w in WAIVERS.items():
        assert w["gate"] in GATES, f"{tool}: gate {w['gate']!r} not in {sorted(GATES)}"
        assert w["reason"].strip(), f"{tool}: empty reason"


def test_shipped_manifest_has_no_prose_only_waive():
    # the SHIPPED manifest: every executes:null tool carries an explicit waiver (0 orphans).
    import pathlib
    m = json.loads(pathlib.Path("contracts/tool-liveness.json").read_text(encoding="utf-8"))
    orphans = [k for k, v in m["tools"].items() if v.get("executes") is None and "waived" not in v]
    assert orphans == [], f"executes:null with NO waiver (prose-only waive): {orphans}"
