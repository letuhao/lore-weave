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
    task_envelope_from_content,
    task_envelope_from_result,
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
