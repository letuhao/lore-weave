"""K21-C (D-K21B-05) — `_row_to_message` surfaces the `tool_calls` column.

The chat_messages.tool_calls JSONB column persists the per-message
tool-call history (Cycle B); D-K21B-05 makes the message-read API
return it so the FE can replay tool-call indicators.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.routers.messages import _row_to_message


def _row(**over) -> dict:
    base = {
        "message_id": uuid4(),
        "session_id": uuid4(),
        "owner_user_id": uuid4(),
        "role": "assistant",
        "content": "hello",
        "content_parts": None,
        "tool_calls": None,
        "sequence_num": 1,
        "input_tokens": None,
        "output_tokens": None,
        "model_ref": None,
        "is_error": False,
        "error_detail": None,
        "parent_message_id": None,
        "created_at": datetime.now(timezone.utc),
    }
    base.update(over)
    return base


def test_tool_calls_none_when_column_null():
    msg = _row_to_message(_row(tool_calls=None))
    assert msg.tool_calls is None


def test_tool_calls_parsed_from_jsonb_string():
    """asyncpg returns a JSONB column as a string by default — it must
    be json-decoded into the response, like content_parts."""
    msg = _row_to_message(
        _row(tool_calls='[{"tool": "memory_search", "ok": true}]')
    )
    assert msg.tool_calls == [{"tool": "memory_search", "ok": True}]


def test_tool_calls_passthrough_when_already_decoded():
    """If a JSONB codec hands back an already-decoded value, it passes
    through unchanged."""
    decoded = [{"tool": "memory_forget", "ok": False}]
    msg = _row_to_message(_row(tool_calls=decoded))
    assert msg.tool_calls == decoded


def test_finish_reason_surfaced_when_present():
    """DBT-CHAT-PERSIST — the FE needs finish_reason to badge an incomplete
    reply (interrupted/error) instead of it looking like a finished answer."""
    assert _row_to_message(_row(finish_reason="interrupted")).finish_reason == "interrupted"
    assert _row_to_message(_row(finish_reason="error")).finish_reason == "error"
    assert _row_to_message(_row(finish_reason="stop")).finish_reason == "stop"


def test_finish_reason_degrades_to_none_before_migration():
    """A row read before the finish_reason column exists (or a partial test
    record) must degrade to None via `.get`, never KeyError."""
    msg = _row_to_message(_row())  # _row() has no finish_reason key
    assert msg.finish_reason is None
