"""Tests for loreweave_llm.Client's SSE event dispatch.

D-ERROREVENT-MASKS-UPSTREAM (2026-07-08): an `error` SSE event missing the
required `message` field used to crash `_dispatch_event` with an opaque
`pydantic.ValidationError` that masked whatever the ACTUAL upstream failure
was — found live while investigating an LM Studio tool-call-parser crash,
where the true error was only recoverable from LM Studio's own server logs,
not from this SDK's raised exception.
"""

from loreweave_llm.client import Client
from loreweave_llm.models import ErrorEvent


def test_error_event_with_message_dispatches_normally():
    ev = Client._dispatch_event(
        {"event": "error", "code": "LLM_UPSTREAM_ERROR", "message": "real upstream failure"}
    )
    assert isinstance(ev, ErrorEvent)
    assert ev.code == "LLM_UPSTREAM_ERROR"
    assert ev.message == "real upstream failure"


def test_error_event_missing_message_degrades_instead_of_crashing():
    """The exact live-reproduced shape: a producer emits {event, code} with no
    message. Must not raise ValidationError — must degrade to a best-effort
    ErrorEvent that still carries the real code and the raw payload, so a
    caller can at least see WHAT happened instead of an unrelated crash."""
    ev = Client._dispatch_event({"event": "error", "code": "LLM_UPSTREAM_ERROR"})
    assert isinstance(ev, ErrorEvent)
    assert ev.code == "LLM_UPSTREAM_ERROR"
    assert ev.message  # non-empty — carries the raw payload as a fallback
    assert "LLM_UPSTREAM_ERROR" in ev.message


def test_error_event_missing_both_code_and_message_still_degrades():
    ev = Client._dispatch_event({"event": "error"})
    assert isinstance(ev, ErrorEvent)
    assert ev.code == "LLM_ERROR"
    assert ev.message
