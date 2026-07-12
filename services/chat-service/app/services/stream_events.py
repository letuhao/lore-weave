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
import re
from typing import Protocol
from uuid import uuid4

__all__ = [
    "StreamEmitter",
    "LegacyEmitter",
    "AgUiEmitter",
    "make_emitter",
    "scrub_jargon",
]


def _sse(obj: dict) -> str:
    """Encode one event dict as an SSE data line."""
    return f"data: {json.dumps(obj)}\n\n"


# ── Track C §4 vocabulary guard (DETERMINISTIC "speak plainly") ──────────────────
# The flagship promises the novelist never hears the SYSTEM's words. The rail asks the
# model to speak plainly, but a mid-tier model (gemma) does not reliably comply — measured,
# it leaks `glossary`/`entity`/`ontology`/`knowledge graph`/`vision-to-book` to the user.
# So we ENFORCE it: rewrite the UNAMBIGUOUS §4 jargon in the assistant's user-facing text to
# plain novelist words, at the wire chokepoint. Only terms with NO innocuous English use are
# here — `kind`/`tool`/`spec`/`job`/`token` are deliberately EXCLUDED (a model says "what
# kind of story" / "a tool for you" innocuously; rewriting those would mangle normal prose,
# and they are not real jargon leaks). Ordered plural-before-singular so both forms match.
_JARGON_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bknowledge\s+graphs?\b", re.I), "connection map"),
    (re.compile(r"\bvision[-\s]?to[-\s]?book\b", re.I), "book-building"),
    (re.compile(r"\bNovelSystemSpec\b", re.I), "plan"),
    (re.compile(r"\bPlanForge\b", re.I), "the planner"),
    (re.compile(r"\bglossaries\b", re.I), "story bibles"),
    (re.compile(r"\bglossary\b", re.I), "story bible"),
    (re.compile(r"\bontolog(?:y|ies)\b", re.I), "categories"),
    (re.compile(r"\bentities\b", re.I), "elements"),
    (re.compile(r"\bentity\b", re.I), "element"),
    (re.compile(r"\battributes\b", re.I), "details"),
    (re.compile(r"\battribute\b", re.I), "detail"),
    (re.compile(r"\bschemas\b", re.I), "structures"),
    (re.compile(r"\bschema\b", re.I), "structure"),
    (re.compile(r"\bpipelines\b", re.I), "processes"),
    (re.compile(r"\bpipeline\b", re.I), "process"),
    (re.compile(r"\bworkflows\b", re.I), "recipes"),
    (re.compile(r"\bworkflow\b", re.I), "recipe"),
    (re.compile(r"\bwikis?\b", re.I), "notes"),
]
# The longest phrase above is "knowledge graph" (2 words). The stream buffer holds back a
# trailing word that could START such a phrase so it is never split across two deltas.
_JARGON_PHRASE_STARTS = {"knowledge"}

# Every lowercase word a jargon rule could match — used to decide whether a trailing partial
# word is "risky" (a prefix of a jargon token) and must be HELD until it completes, vs. safe
# to emit immediately. This keeps the stream eager for all normal prose and only buffers when
# text could be forming a jargon word/phrase.
_JARGON_WORDS = frozenset({
    "glossary", "glossaries", "ontology", "ontologies", "entity", "entities",
    "attribute", "attributes", "schema", "schemas", "pipeline", "pipelines",
    "workflow", "workflows", "wiki", "wikis", "novelsystemspec", "planforge",
    "vision-to-book", "vision", "knowledge",
})


def _is_risky_tail(tail: str) -> bool:
    """True when a trailing partial word could still grow into a jargon token (so it must be
    held). False for a token no jargon word starts with (safe to emit now)."""
    t = tail.lower().lstrip("\"'([{")
    if not t:
        return False
    return any(w.startswith(t) for w in _JARGON_WORDS)


def _match_case(repl: str, orig: str) -> str:
    """Carry the original token's casing onto the replacement (ALL-CAPS / Capitalized / lower)."""
    if orig.isupper() and orig.lower() != orig:
        return repl.upper()
    if orig[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def scrub_jargon(text: str) -> str:
    """Rewrite unambiguous §4 system-jargon to plain novelist words. Idempotent, case-aware."""
    for pat, repl in _JARGON_SUBS:
        text = pat.sub(lambda m: _match_case(repl, m.group(0)), text)
    return text


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

    def composing(self, active: bool) -> list[str]:
        """A2A phase-2 — the in-turn composer model started/stopped streaming.
        Lets the UI show a transient "✍️ Drafting…" indicator while the (often
        slow) writer model runs, instead of a silent panel."""
        ...

    def activity(self, payload: dict) -> list[str]:
        """MCP-fanout C-ACTIVITY (H16) — a Tier-A auto-write happened. ``payload``
        = {op, summary, undo}; the FE renders an "agent did X · Undo" strip so a
        low-blast auto-commit is visible, not a silent surprise."""
        ...

    def context_budget(self, payload: dict) -> list[str]:
        """RAID A2 / W1 — the per-turn context-window frame ({used_tokens,
        context_length, effective_limit, pct} + W1's breakdown / baseline_tokens /
        until_compact_pct). Legacy clients have no meter → no-op there, but the
        method MUST exist so the Protocol is honest (no try/except at call sites)."""
        ...

    def compaction(self, payload: dict) -> list[str]:
        """W1 — compaction actually changed the prompt this turn. ``payload`` is
        CompactionReport.to_event(). Feeds the W2 "earlier turns summarized"
        toast; legacy clients no-op."""
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

    def composing(self, active: bool) -> list[str]:
        # Legacy chat page has no composer model → no-op.
        return []

    def activity(self, payload: dict) -> list[str]:
        # C-ACTIVITY is an agui-surface affordance; legacy clients don't render
        # the Undo strip → no-op (the tool-call event still conveys the write).
        return []

    def agent_surface(self, payload: dict) -> list[str]:
        return []

    def context_budget(self, payload: dict) -> list[str]:
        # W1 — legacy clients have no context meter → no-op, but the method
        # exists so emit sites need no defensive try/except (Protocol parity).
        return []

    def compaction(self, payload: dict) -> list[str]:
        # W1 — compaction visibility is an agui affordance; legacy no-op.
        return []

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
        # §4 vocab guard — trailing UNSETTLED text held back so a multi-word jargon phrase
        # ("knowledge graph") is never split across two deltas before scrub_jargon sees it.
        self._jargon_buf: str = ""

    # ── private framing helpers ───────────────────────────────────────────

    def _text_content(self, delta: str) -> str:
        return _sse({
            "type": "TEXT_MESSAGE_CONTENT",
            "messageId": self._message_id,
            "delta": delta,
        })

    def _split_settled(self, buf: str) -> tuple[str, str]:
        """Split a text buffer into (settled, held). `settled` is safe to emit now; `held` is
        a trailing run kept back ONLY when it could still grow into a jargon token — so normal
        prose streams eagerly and only jargon-forming text buffers.

        Two things can be risky: (1) the trailing partial word is a prefix of a jargon token
        (e.g. "gloss" → glossary); (2) the last COMPLETE word could start a multi-word phrase
        (e.g. "knowledge" → knowledge graph)."""
        idx = max(buf.rfind(" "), buf.rfind("\n"), buf.rfind("\t"))
        tail = buf[idx + 1:] if idx >= 0 else buf
        if not _is_risky_tail(tail):
            # tail is safe; but the last COMPLETE word before it may be a phrase-start.
            settled = buf
            held = ""
            stripped = settled.rstrip()
            words = stripped.split()
            last = words[-1] if words else ""
            if last.lower().strip(".,!?;:\"'()") in _JARGON_PHRASE_STARTS:
                cut = settled.rfind(last)
                if cut >= 0:
                    held = settled[cut:]
                    settled = settled[:cut]
            return settled, held
        # tail is a jargon prefix → hold it (and, if idx<0, everything).
        return (buf[: idx + 1] if idx >= 0 else ""), tail

    def _close_open(self) -> list[str]:
        """Emit the END event(s) for whichever message is open, and clear state."""
        if self._open == "text":
            self._open = None
            lines: list[str] = []
            if self._jargon_buf:  # flush any held tail through the scrubber
                try:
                    tail = scrub_jargon(self._jargon_buf)
                except Exception:
                    tail = self._jargon_buf
                self._jargon_buf = ""
                if tail:
                    lines.append(self._text_content(tail))
            lines.append(_sse({"type": "TEXT_MESSAGE_END", "messageId": self._message_id}))
            return lines
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

    def composing(self, active: bool) -> list[str]:
        return [_sse({
            "type": "CUSTOM",
            "name": "composing",
            "value": {"active": active},
        })]

    def activity(self, payload: dict) -> list[str]:
        # C-ACTIVITY (H16) — Tier-A auto-write visibility + Undo affordance. The
        # FE renders {op, summary, undo} as a strip in chat; clicking Undo issues
        # the named reverse tool when undo.available.
        return [_sse({
            "type": "CUSTOM",
            "name": "activity",
            "value": payload,
        })]

    def agent_surface(self, payload: dict) -> list[str]:
        # Story 04 / #07b — inspector state machine; emitted on phase transitions only.
        return [_sse({
            "type": "CUSTOM",
            "name": "agentSurface",
            "value": payload,
        })]

    def context_budget(self, payload: dict) -> list[str]:
        # RAID Wave A2 — context-window usage vs the model's context_length. The FE
        # meter (studio status bar + chat header) reads {used_tokens, context_length,
        # effective_limit, pct}; NULL context_length → the meter shows "—".
        return [_sse({
            "type": "CUSTOM",
            "name": "contextBudget",
            "value": payload,
        })]

    def compaction(self, payload: dict) -> list[str]:
        # W1 — emitted only when compaction DID something (CompactionReport
        # .did_work): {triggered, tool_results_cleared, turns_truncated,
        # summarized, summarize_failed, overflowed, tokens_before, tokens_after,
        # steps}. The FE shows the "earlier turns summarized/trimmed" toast.
        return [_sse({
            "type": "CUSTOM",
            "name": "compaction",
            "value": payload,
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
        # §4 vocab guard: buffer, scrub the SETTLED prefix, hold a trailing partial/phrase-start.
        # Fail-safe — any error in the guard falls back to emitting the raw delta unchanged, so
        # the guard can never break or drop the assistant's output.
        try:
            self._jargon_buf += delta
            settled, self._jargon_buf = self._split_settled(self._jargon_buf)
            if settled:
                lines.append(self._text_content(scrub_jargon(settled)))
        except Exception:
            if self._jargon_buf:
                lines.append(self._text_content(self._jargon_buf))
                self._jargon_buf = ""
            lines.append(self._text_content(delta))
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
        #
        # `tc` is the suspend chunk's `pending_tool_call` — its canonical shape
        # is {id, name, args} (the same dict `finish(pending=...)` reads `name`
        # /`id` from below). Accept the legacy `tool` key too for safety.
        tool_id = tc.get("id") or str(uuid4())
        tool_name = tc.get("name") or tc.get("tool")
        return [
            _sse({
                "type": "TOOL_CALL_START",
                "toolCallId": tool_id,
                "toolCallName": tool_name,
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
        self._jargon_buf = ""  # partial content is discarded on RUN_ERROR
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
