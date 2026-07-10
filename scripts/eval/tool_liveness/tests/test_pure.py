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
