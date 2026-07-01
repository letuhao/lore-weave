"""ARCH-1 C3 — unit tests for the stream event emitters.

Pure/synchronous: each emitter method returns a list of SSE strings, so we drive
the framing state machine directly without a pool/LLM. The integration of these
emitters into stream_response is covered in test_stream_service.py.
"""
from __future__ import annotations

import json

from app.services.stream_events import (
    AgUiEmitter,
    LegacyEmitter,
    make_emitter,
)


def _types(lines: list[str]) -> list[str]:
    """Extract the AG-UI `type` of each SSE data line."""
    out = []
    for ln in lines:
        payload = ln.removeprefix("data: ").strip()
        if payload == "[DONE]":
            out.append("[DONE]")
        else:
            out.append(json.loads(payload)["type"])
    return out


def _parse(line: str) -> dict:
    return json.loads(line.removeprefix("data: ").strip())


# ── selection ─────────────────────────────────────────────────────────────────


class TestMakeEmitter:
    def test_agui_selected(self):
        em = make_emitter("agui", thread_id="s1", message_id="m1")
        assert isinstance(em, AgUiEmitter)

    def test_legacy_default(self):
        assert isinstance(make_emitter("legacy", thread_id="s", message_id="m"), LegacyEmitter)

    def test_unknown_falls_back_to_legacy(self):
        assert isinstance(make_emitter("bogus", thread_id="s", message_id="m"), LegacyEmitter)


# ── legacy byte-for-byte ────────────────────────────────────────────────────────


class TestLegacyEmitter:
    def setup_method(self):
        self.em = LegacyEmitter()

    def test_open_run_is_noop(self):
        assert self.em.open_run() == []

    def test_memory_mode(self):
        assert self.em.memory_mode("degraded") == [
            'data: {"type": "memory-mode", "mode": "degraded"}\n\n'
        ]

    def test_reasoning_delta(self):
        assert self.em.reasoning_delta("think") == [
            'data: {"type": "reasoning-delta", "delta": "think"}\n\n'
        ]

    def test_activity_is_noop(self):
        # C-ACTIVITY is agui-only; legacy clients don't render the Undo strip.
        assert self.em.activity({"op": "x", "summary": "y", "undo": {}}) == []

    def test_text_delta(self):
        assert self.em.text_delta("hi") == [
            'data: {"type": "text-delta", "delta": "hi"}\n\n'
        ]

    def test_tool_call_only_tool_and_ok(self):
        tc = {"id": "call_1", "tool": "memory_search", "ok": True,
              "args": {"q": "Kai"}, "result": {"hit": 1}, "error": None}
        assert self.em.tool_call(tc) == [
            'data: {"type": "tool-call", "tool": "memory_search", "ok": true}\n\n'
        ]

    def test_persisted_data(self):
        payload = {"message_id": "m1", "has_reasoning": True}
        assert self.em.persisted_data(payload) == [
            'data: {"type": "data", "data": [{"message_id": "m1", "has_reasoning": true}]}\n\n'
        ]

    def test_finish_preserves_payload(self):
        payload = {
            "finishReason": "stop",
            "usage": {"promptTokens": 1, "completionTokens": 2},
            "timing": {"responseTimeMs": 10, "timeToFirstTokenMs": 5},
        }
        line = self.em.finish(payload)[0]
        parsed = _parse(line)
        assert parsed["type"] == "finish-message"
        assert parsed["finishReason"] == "stop"
        assert parsed["usage"] == {"promptTokens": 1, "completionTokens": 2}

    def test_error(self):
        assert self.em.error("boom") == [
            'data: {"type": "error", "errorText": "boom"}\n\n'
        ]

    def test_done(self):
        assert self.em.done() == ["data: [DONE]\n\n"]


# ── AG-UI framing state machine ─────────────────────────────────────────────────


class TestAgUiEmitter:
    def _em(self) -> AgUiEmitter:
        return AgUiEmitter(thread_id="sess-1", message_id="msg-1")

    def test_open_run(self):
        line = self._em().open_run()[0]
        ev = _parse(line)
        assert ev["type"] == "RUN_STARTED"
        assert ev["threadId"] == "sess-1"
        assert ev["runId"]  # a generated uuid

    def test_memory_mode_is_custom(self):
        ev = _parse(self._em().memory_mode("static")[0])
        assert ev == {"type": "CUSTOM", "name": "memoryMode", "value": {"mode": "static"}}

    def test_activity_is_custom_event(self):
        # MCP-fanout C-ACTIVITY (H16) — Tier-A visibility + Undo strip.
        payload = {"op": "chapter.create", "summary": "Created draft chapter",
                   "undo": {"available": True, "tool": "chapter_delete", "args": {}}}
        ev = _parse(self._em().activity(payload)[0])
        assert ev == {"type": "CUSTOM", "name": "activity", "value": payload}

    def test_agent_surface_is_custom_event(self):
        payload = {
            "phase": "Curated",
            "pinned_count": 2,
            "hot_seed_count": 0,
            "activated_count": 0,
            "injected_skills": ["universal"],
            "running_tool": None,
            "last_find_tools_query": None,
            "find_tools_call_count": 0,
        }
        ev = _parse(self._em().agent_surface(payload)[0])
        assert ev == {"type": "CUSTOM", "name": "agentSurface", "value": payload}

    def test_text_happy_path_frames_once(self):
        em = self._em()
        first = em.text_delta("Hi ")
        second = em.text_delta("there")
        assert _types(first) == ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT"]
        # second delta does NOT re-open the message
        assert _types(second) == ["TEXT_MESSAGE_CONTENT"]
        # messageId threads through
        assert _parse(first[0])["messageId"] == "msg-1"
        assert _parse(first[0])["role"] == "assistant"

    def test_reasoning_frames_once(self):
        em = self._em()
        first = em.reasoning_delta("a")
        second = em.reasoning_delta("b")
        assert _types(first) == [
            "REASONING_START", "REASONING_MESSAGE_START", "REASONING_MESSAGE_CONTENT",
        ]
        assert _types(second) == ["REASONING_MESSAGE_CONTENT"]

    def test_reasoning_to_text_transition_closes_reasoning(self):
        em = self._em()
        em.reasoning_delta("thinking")
        lines = em.text_delta("answer")
        # the reasoning message is closed (END pair) right before TEXT_MESSAGE_START
        assert _types(lines) == [
            "REASONING_MESSAGE_END", "REASONING_END",
            "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT",
        ]

    def test_finish_closes_open_text_then_run_finished(self):
        em = self._em()
        em.text_delta("answer")
        payload = {
            "finishReason": "stop",
            "usage": {"promptTokens": 3, "completionTokens": 4},
            "timing": {"responseTimeMs": 12, "timeToFirstTokenMs": 6},
        }
        lines = em.finish(payload)
        assert _types(lines) == ["TEXT_MESSAGE_END", "RUN_FINISHED"]
        result = _parse(lines[-1])["result"]
        assert result["finishReason"] == "stop"
        assert result["usage"] == {"promptTokens": 3, "completionTokens": 4}
        assert result["timing"]["responseTimeMs"] == 12
        assert result["messageId"] == "msg-1"
        assert "type" not in result  # the leading finish-message "type" key is dropped

    def test_finish_reasoning_only_closes_reasoning(self):
        em = self._em()
        em.reasoning_delta("just thinking")
        lines = em.finish({"finishReason": "stop", "usage": {}, "timing": {}})
        assert _types(lines) == ["REASONING_MESSAGE_END", "REASONING_END", "RUN_FINISHED"]

    def test_finish_no_open_message(self):
        em = self._em()
        lines = em.finish({"finishReason": "stop", "usage": {}, "timing": {}})
        assert _types(lines) == ["RUN_FINISHED"]

    def test_close_message_ends_open_text_then_finish_is_clean(self):
        em = self._em()
        em.text_delta("answer")
        closed = em.close_message()
        assert _types(closed) == ["TEXT_MESSAGE_END"]
        # finish() after close_message() does NOT re-emit an END (state cleared)
        fin = em.finish({"finishReason": "stop", "usage": {}, "timing": {}})
        assert _types(fin) == ["RUN_FINISHED"]

    def test_close_message_noop_when_nothing_open(self):
        assert self._em().close_message() == []

    def test_tool_call_four_event_sequence(self):
        em = self._em()
        tc = {"id": "call_42", "tool": "memory_search",
              "args": {"query": "Kai"}, "ok": True,
              "result": {"hits": [1]}, "error": None}
        lines = em.tool_call(tc)
        assert _types(lines) == [
            "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT",
        ]
        start, args, end, result = (_parse(x) for x in lines)
        # toolCallId is consistent across all four
        assert start["toolCallId"] == args["toolCallId"] == end["toolCallId"] == result["toolCallId"] == "call_42"
        assert start["toolCallName"] == "memory_search"
        assert start["parentMessageId"] == "msg-1"
        assert json.loads(args["delta"]) == {"query": "Kai"}
        # content carries the authoritative ok flag + the result envelope.
        assert json.loads(result["content"]) == {"ok": True, "result": {"hits": [1]}}
        assert result["role"] == "tool"

    def test_tool_call_missing_id_gets_synthesized_unique_id(self):
        em = self._em()
        tc = {"id": "", "tool": "memory_search", "args": {}, "ok": True,
              "result": {}, "error": None}
        ids = {_parse(x).get("toolCallId") for x in em.tool_call(tc)}
        # all four events share ONE non-empty synthesized id
        assert len(ids) == 1
        only = ids.pop()
        assert only  # non-empty
        # a second id-less call gets a DIFFERENT id (no "" collision)
        other = _parse(em.tool_call(tc)[0])["toolCallId"]
        assert other and other != only

    def test_tool_call_error_content(self):
        em = self._em()
        tc = {"id": "c1", "tool": "memory_search", "args": {}, "ok": False,
              "result": None, "error": "entity not found"}
        result = _parse(em.tool_call(tc)[-1])
        assert json.loads(result["content"]) == {"ok": False, "error": "entity not found"}

    def test_tool_call_ok_flag_independent_of_result_shape(self):
        # review-impl C4 #1: a SUCCESSFUL result that itself contains an
        # "error" key must still carry ok=True, so the client can't misread it.
        em = self._em()
        tc = {"id": "c1", "tool": "memory_search", "args": {}, "ok": True,
              "result": {"hits": [], "error": None}, "error": None}
        result = _parse(em.tool_call(tc)[-1])
        payload = json.loads(result["content"])
        assert payload["ok"] is True
        assert payload["result"] == {"hits": [], "error": None}

    def test_tool_call_does_not_close_open_text(self):
        em = self._em()
        em.text_delta("preamble ")
        em.tool_call({"id": "c1", "tool": "t", "args": {}, "ok": True,
                      "result": {}, "error": None})
        after = em.text_delta("answer")
        # text message survived the tool call — only CONTENT, no second START
        assert _types(after) == ["TEXT_MESSAGE_CONTENT"]

    def test_error_emits_run_error_only_and_resets(self):
        em = self._em()
        em.text_delta("partial")  # opens a text message
        lines = em.error("An internal error occurred. Please try again.")
        assert _types(lines) == ["RUN_ERROR"]  # NO TEXT_MESSAGE_END
        ev = _parse(lines[0])
        assert ev["message"] == "An internal error occurred. Please try again."
        assert ev["code"] == "STREAM_ERROR"
        # state was reset → finish/done are clean no-ops
        assert em.done() == []

    def test_persisted_data_camelcase_optional_keys(self):
        em = self._em()
        ev = _parse(em.persisted_data({"message_id": "m1", "output_id": "o1", "has_reasoning": True})[0])
        assert ev["name"] == "persisted"
        assert ev["value"] == {"messageId": "m1", "outputId": "o1", "hasReasoning": True}
        # optional keys omitted when absent
        ev2 = _parse(em.persisted_data({"message_id": "m1"})[0])
        assert ev2["value"] == {"messageId": "m1"}

    def test_done_is_empty(self):
        assert self._em().done() == []
