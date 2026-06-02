"""ARCH-1 C3 — stream event serialization (legacy + AG-UI).

`stream_response` (app/services/stream_service.py) interleaves business logic
(DB persistence, billing, auto-title) with wire serialization. C3 extracts ONLY
the serialization behind an emitter selected per request, so the chat stream can
speak either the historical LoreWeave event vocabulary OR the AG-UI protocol
without touching any business logic.

Two implementations behind one interface:

* ``LegacyEmitter`` — the 8 historical event shapes, byte-for-byte. Default
  until the AG-UI frontend (ARCH-1 C4) ships.
* ``AgUiEmitter`` — the AG-UI protocol. Wire ``type`` is SCREAMING_SNAKE_CASE,
  fields are camelCase, encoding is the same ``data: {json}\\n\\n`` SSE the
  legacy path already uses (verified against the AG-UI SDK). Reasoning uses
  ``REASONING_*`` (``THINKING_*`` is deprecated).

Selection is PER REQUEST (header ``x-loreweave-stream-format``): LoreWeave is
multi-device, so the legacy frontend and the future AG-UI frontend hit the same
deployed backend at once — a global flag would break one of them.

Every method returns ``list[str]`` of fully-encoded SSE lines (0..N). Returning
lists (not generators) keeps the call sites in ``stream_response`` trivial and
makes these classes pure/synchronous to unit-test.
"""
from __future__ import annotations

import json
from typing import Protocol
from uuid import uuid4

__all__ = [
    "StreamEmitter",
    "LegacyEmitter",
    "AgUiEmitter",
    "make_emitter",
]


def _sse(obj: dict) -> str:
    """Encode one event dict as an SSE data line."""
    return f"data: {json.dumps(obj)}\n\n"


class StreamEmitter(Protocol):
    """Serialization seam for one chat turn. ``stream_response`` calls these in
    order; each returns the SSE lines to yield (possibly none)."""

    def open_run(self) -> list[str]:
        """Lifecycle start — emitted once, before any other event."""
        ...

    def memory_mode(self, mode: str) -> list[str]:
        """Knowledge-context mode for the turn (no_project|static|degraded)."""
        ...

    def reasoning_delta(self, delta: str) -> list[str]:
        """One reasoning ("thinking") token."""
        ...

    def text_delta(self, delta: str) -> list[str]:
        """One assistant content token."""
        ...

    def tool_call(self, tc: dict) -> list[str]:
        """One executed memory tool call. ``tc`` is the dict yielded by
        ``_stream_with_tools`` — {id, iteration, tool, args, ok, result, error}."""
        ...

    def tool_call_pending(self, tc: dict) -> list[str]:
        """ARCH-1 C6 — a FRONTEND tool call awaiting client execution. Emits
        START/ARGS/END but NO RESULT (the result comes later, on the resume
        request, after the user applies/dismisses). ``tc`` = {id, tool, args}."""
        ...

    def close_message(self) -> list[str]:
        """Close the open assistant/reasoning message — called once the token
        stream ends, before persistence/finish, so the message END frames the
        content (not the later run-level events)."""
        ...

    def persisted_data(self, payload: dict) -> list[str]:
        """Post-persistence ids ({message_id, output_id?, has_reasoning?})."""
        ...

    def finish(self, payload: dict, *, status: str = "success", pending: dict | None = None) -> list[str]:
        """End-of-turn. ``status`` is "success" normally, or "suspended" when a
        frontend tool call is awaiting client execution (``pending`` =
        {runId, toolCallId, toolName} so the FE knows what to execute/resume)."""
        ...

    def error(self, safe_msg: str) -> list[str]:
        """Turn failed — the already-sanitized error message."""
        ...

    def done(self) -> list[str]:
        """Stream terminator (legacy ``[DONE]``; nothing for AG-UI)."""
        ...


class LegacyEmitter:
    """The historical LoreWeave SSE vocabulary — zero behavior change.

    Stateless: each method returns exactly the string(s) ``stream_response``
    emitted inline before C3. A golden-list regression test locks this
    byte-for-byte."""

    def open_run(self) -> list[str]:
        # Legacy has no run-start event.
        return []

    def memory_mode(self, mode: str) -> list[str]:
        return [_sse({"type": "memory-mode", "mode": mode})]

    def reasoning_delta(self, delta: str) -> list[str]:
        return [_sse({"type": "reasoning-delta", "delta": delta})]

    def text_delta(self, delta: str) -> list[str]:
        return [_sse({"type": "text-delta", "delta": delta})]

    def tool_call(self, tc: dict) -> list[str]:
        # Legacy emits only {tool, ok}; the propagated id key is ignored.
        return [_sse({"type": "tool-call", "tool": tc["tool"], "ok": tc["ok"]})]

    def tool_call_pending(self, tc: dict) -> list[str]:
        # Frontend tools are agui-only; legacy clients never advertise them.
        # Defensive no-op so a stray call can't break the legacy wire.
        return []

    def close_message(self) -> list[str]:
        # Legacy deltas are stateless — no message to close.
        return []

    def persisted_data(self, payload: dict) -> list[str]:
        return [_sse({"type": "data", "data": [payload]})]

    def finish(self, payload: dict, *, status: str = "success", pending: dict | None = None) -> list[str]:
        # payload is built in stream_response with keys finishReason/usage/timing
        # in that order; **spread preserves it so output is identical. Legacy has
        # no suspend concept, so status/pending are ignored (frontend tools are
        # agui-only).
        return [_sse({"type": "finish-message", **payload})]

    def error(self, safe_msg: str) -> list[str]:
        return [_sse({"type": "error", "errorText": safe_msg})]

    def done(self) -> list[str]:
        return ["data: [DONE]\n\n"]


class AgUiEmitter:
    """The AG-UI protocol — stateful framing over the same SSE transport.

    Tracks the open run and which message (reasoning|text) is currently open so
    it can lazily emit the required START before the first CONTENT and the END
    on transition/finish. ``message_id`` is the assistant message's id (the same
    uuid persisted to the DB row), used as the AG-UI ``messageId`` throughout so
    the live stream and a later refetch correlate on one id."""

    def __init__(self, thread_id: str, message_id: str) -> None:
        self._thread_id = thread_id
        self._message_id = message_id
        self._run_id = str(uuid4())
        # Which message kind is currently open: None | "reasoning" | "text".
        self._open: str | None = None

    # ── private framing helpers ───────────────────────────────────────────

    def _close_open(self) -> list[str]:
        """Emit the END event(s) for whichever message is open, and clear state."""
        if self._open == "text":
            self._open = None
            return [_sse({"type": "TEXT_MESSAGE_END", "messageId": self._message_id})]
        if self._open == "reasoning":
            self._open = None
            return [
                _sse({"type": "REASONING_MESSAGE_END", "messageId": self._message_id}),
                _sse({"type": "REASONING_END", "messageId": self._message_id}),
            ]
        return []

    # ── interface ─────────────────────────────────────────────────────────

    def open_run(self) -> list[str]:
        return [_sse({
            "type": "RUN_STARTED",
            "threadId": self._thread_id,
            "runId": self._run_id,
        })]

    def memory_mode(self, mode: str) -> list[str]:
        return [_sse({
            "type": "CUSTOM",
            "name": "memoryMode",
            "value": {"mode": mode},
        })]

    def reasoning_delta(self, delta: str) -> list[str]:
        lines: list[str] = []
        if self._open != "reasoning":
            # Defensive: close a (theoretically) open text message first.
            lines += self._close_open()
            lines.append(_sse({"type": "REASONING_START", "messageId": self._message_id}))
            lines.append(_sse({
                "type": "REASONING_MESSAGE_START",
                "messageId": self._message_id,
                "role": "reasoning",
            }))
            self._open = "reasoning"
        lines.append(_sse({
            "type": "REASONING_MESSAGE_CONTENT",
            "messageId": self._message_id,
            "delta": delta,
        }))
        return lines

    def text_delta(self, delta: str) -> list[str]:
        lines: list[str] = []
        if self._open != "text":
            # Close an open reasoning message before the text message opens.
            lines += self._close_open()
            lines.append(_sse({
                "type": "TEXT_MESSAGE_START",
                "messageId": self._message_id,
                "role": "assistant",
            }))
            self._open = "text"
        lines.append(_sse({
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": self._message_id,
            "delta": delta,
        }))
        return lines

    def tool_call(self, tc: dict) -> list[str]:
        # Tool calls happen between LLM passes and are siblings of the text
        # message (both run children) — they do NOT close an open text message;
        # the next pass's text continues under the same messageId.
        # AG-UI keys all four TOOL_CALL_* events on a unique toolCallId. Most
        # providers supply one, but if a provider streamed the call without an
        # id we synthesize a unique one so the four events still correlate and
        # two id-less calls in the same turn can't collide on "".
        tool_id = tc.get("id") or str(uuid4())
        # TOOL_CALL_RESULT.content is a string per AG-UI; we put a structured
        # envelope inside it carrying the authoritative `ok` flag (the same
        # tc["ok"] the legacy path emits) plus the result/error. The client
        # reads `ok` directly rather than inferring success from payload shape,
        # so a tool result that legitimately contains an "error" field can't be
        # misread as a failure (review-impl C4 #1).
        if tc.get("ok"):
            content = json.dumps({"ok": True, "result": tc.get("result")})
        else:
            content = json.dumps({"ok": False, "error": tc.get("error")})
        return [
            _sse({
                "type": "TOOL_CALL_START",
                "toolCallId": tool_id,
                "toolCallName": tc["tool"],
                "parentMessageId": self._message_id,
            }),
            _sse({
                "type": "TOOL_CALL_ARGS",
                "toolCallId": tool_id,
                "delta": json.dumps(tc.get("args", {})),
            }),
            _sse({"type": "TOOL_CALL_END", "toolCallId": tool_id}),
            _sse({
                "type": "TOOL_CALL_RESULT",
                "messageId": self._message_id,
                "toolCallId": tool_id,
                "content": content,
                "role": "tool",
            }),
        ]

    def tool_call_pending(self, tc: dict) -> list[str]:
        # ARCH-1 C6 — a frontend tool call awaiting client execution: emit
        # START/ARGS/END but NO RESULT. The result arrives later on the resume
        # request (after the user applies/dismisses). The FE reads the proposal
        # from TOOL_CALL_ARGS and holds the call open until then.
        tool_id = tc.get("id") or str(uuid4())
        return [
            _sse({
                "type": "TOOL_CALL_START",
                "toolCallId": tool_id,
                "toolCallName": tc["tool"],
                "parentMessageId": self._message_id,
            }),
            _sse({
                "type": "TOOL_CALL_ARGS",
                "toolCallId": tool_id,
                "delta": json.dumps(tc.get("args", {})),
            }),
            _sse({"type": "TOOL_CALL_END", "toolCallId": tool_id}),
        ]

    def close_message(self) -> list[str]:
        return self._close_open()

    def persisted_data(self, payload: dict) -> list[str]:
        value: dict = {"messageId": payload.get("message_id")}
        if "output_id" in payload:
            value["outputId"] = payload["output_id"]
        if "has_reasoning" in payload:
            value["hasReasoning"] = payload["has_reasoning"]
        return [_sse({"type": "CUSTOM", "name": "persisted", "value": value})]

    def finish(self, payload: dict, *, status: str = "success", pending: dict | None = None) -> list[str]:
        # Any open message was already closed by close_message() at end-of-stream;
        # _close_open() here is a defensive no-op if so.
        lines = self._close_open()
        # payload carries finishReason/usage/timing (+ leading "type" key we drop).
        result = {k: v for k, v in payload.items() if k != "type"}
        result["messageId"] = self._message_id
        # C6: surface the run status so the FE knows a frontend tool is awaiting
        # execution (status="suspended" + pending={runId,toolCallId,toolName}).
        result["status"] = status
        if pending is not None:
            result["pendingToolCall"] = pending
        lines.append(_sse({"type": "RUN_FINISHED", "result": result}))
        return lines

    def error(self, safe_msg: str) -> list[str]:
        # RUN_ERROR is a hard terminator — AG-UI consumers discard partial
        # message state, so we do NOT emit a (misleading) END for the open
        # message; just reset so a later done() is a clean no-op.
        self._open = None
        return [_sse({
            "type": "RUN_ERROR",
            "message": safe_msg,
            "code": "STREAM_ERROR",
        })]

    def done(self) -> list[str]:
        # The run ended on RUN_FINISHED / RUN_ERROR; AG-UI has no [DONE] sentinel.
        return []


def make_emitter(
    stream_format: str,
    *,
    thread_id: str,
    message_id: str,
) -> StreamEmitter:
    """Select the emitter for a request. Any value other than ``"agui"`` (incl.
    an unknown/missing header) falls back to legacy — the safe default until
    C4 ships."""
    if stream_format == "agui":
        return AgUiEmitter(thread_id=thread_id, message_id=message_id)
    return LegacyEmitter()
