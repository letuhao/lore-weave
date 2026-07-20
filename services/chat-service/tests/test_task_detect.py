"""ext-tasks client detection (T1c(3)) — recognise a durable task in a tool result.

Covers both shapes: a wire CreateTaskResult (`.task`), and the gate HANDLE in tool
content (`type == GATE_RESULT_TYPE`). A normal tool result must NOT be misread as a
task (dormant-safe: chat-service doesn't declare tasks yet, so nothing fires today).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.task_detect import (
    GATE_RESULT_TYPE,
    PROPOSE_EDIT_DIRECTIVE_TYPE,
    propose_edit_suspend_args_from_result,
    task_envelope_from_content,
    task_envelope_from_result,
    tasks_capability_meta,
)


# ── CreateTaskResult (.task) ──────────────────────────────────────────────────
def test_create_task_result_becomes_task_envelope():
    result = SimpleNamespace(task=SimpleNamespace(taskId="task_abc", status="input_required", pollInterval=1000))
    env = task_envelope_from_result(result)
    assert env is not None
    assert env["success"] is True and env["result"] is None and env["error"] is None
    assert env["task"] == {"taskId": "task_abc", "status": "input_required",
                           "inputRequests": None, "pollIntervalMs": 1000}


def test_normal_call_tool_result_is_not_a_task():
    result = SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")], isError=False)
    assert task_envelope_from_result(result) is None


def test_task_object_missing_fields_is_none():
    assert task_envelope_from_result(SimpleNamespace(task=SimpleNamespace(taskId="", status=""))) is None


# ── gate HANDLE in content ────────────────────────────────────────────────────
def test_handle_dict_becomes_task_envelope():
    handle = {"type": GATE_RESULT_TYPE, "taskId": "task_9", "status": "input_required",
              "inputRequests": {"title": "Publish?"}, "pollIntervalMs": 500}
    env = task_envelope_from_content(handle)
    assert env is not None
    assert env["task"]["taskId"] == "task_9"
    assert env["task"]["inputRequests"] == {"title": "Publish?"}
    assert env["task"]["pollIntervalMs"] == 500


def test_handle_json_string_becomes_task_envelope():
    env = task_envelope_from_content(json.dumps(
        {"type": GATE_RESULT_TYPE, "taskId": "task_j", "status": "input_required"}))
    assert env is not None and env["task"]["taskId"] == "task_j"


def test_non_handle_dict_is_none():
    assert task_envelope_from_content({"some": "normal", "tool": "result"}) is None


def test_wrong_type_marker_is_none():
    assert task_envelope_from_content({"type": "something/else", "taskId": "x", "status": "y"}) is None


def test_non_json_string_is_none():
    assert task_envelope_from_content("just prose, not json") is None


def test_handle_missing_task_id_is_none():
    assert task_envelope_from_content({"type": GATE_RESULT_TYPE, "status": "input_required"}) is None


# ── the client declaration ↔ server read must agree on the wire ───────────────
def test_capability_meta_is_read_by_the_server_side_helper():
    """The _meta chat-service would attach to opt into tasks must be exactly what
    the domain's client_supports_tasks reads → they can't drift out of sync."""
    from types import SimpleNamespace

    from loreweave_mcp.tasks_wire import client_supports_tasks

    ctx = SimpleNamespace(request_context=SimpleNamespace(meta=tasks_capability_meta()))
    assert client_supports_tasks(ctx) is True
    # and without it, the server reads False (the confirm_token fallback)
    assert client_supports_tasks(SimpleNamespace(request_context=SimpleNamespace(meta={}))) is False


# ── Phase 2 — the propose_edit gated proposal directive detector ──────────────
def test_propose_edit_directive_becomes_the_legacy_suspend_args():
    d = {"type": PROPOSE_EDIT_DIRECTIVE_TYPE, "operation": "insert_at_cursor",
         "text": "Hi", "rationale": "clarity"}
    assert propose_edit_suspend_args_from_result(d) == {
        "operation": "insert_at_cursor", "text": "Hi", "rationale": "clarity"}


def test_propose_edit_directive_omits_absent_rationale():
    d = {"type": PROPOSE_EDIT_DIRECTIVE_TYPE, "operation": "replace_selection", "text": "x"}
    assert propose_edit_suspend_args_from_result(d) == {"operation": "replace_selection", "text": "x"}


def test_non_propose_edit_result_is_none():
    # a normal tool result, a ui-directive, and junk are all None (not a suspend)
    assert propose_edit_suspend_args_from_result({"books": []}) is None
    assert propose_edit_suspend_args_from_result({"type": "io.loreweave/ui-directive"}) is None
    assert propose_edit_suspend_args_from_result(None) is None
    assert propose_edit_suspend_args_from_result("nope") is None


def test_propose_edit_directive_missing_fields_is_none():
    # a malformed directive (no operation/text) must not produce a broken suspend
    assert propose_edit_suspend_args_from_result({"type": PROPOSE_EDIT_DIRECTIVE_TYPE, "text": "x"}) is None
    assert propose_edit_suspend_args_from_result({"type": PROPOSE_EDIT_DIRECTIVE_TYPE, "operation": "insert_at_cursor"}) is None
