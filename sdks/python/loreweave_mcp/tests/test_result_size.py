"""The MCP result-size hard cap (mirrors the Go SDK's gate).

A tool's result lands verbatim in the calling agent's context window. `glossary_list_system_standards`
shipped **44,254 characters** — ~11k tokens, a THIRD of a chat turn's budget — and gemma called it
24 times in one live run and built nothing: each call pushed the previous answer out of the window,
so the model could never see what it had already fetched. Every unit test was green.
"""
from __future__ import annotations

import pytest

from loreweave_mcp.compact_content import (
    ResultTooLargeError,
    _check_size,
    result_max_bytes,
    result_warn_bytes,
)


def test_a_small_result_passes():
    _check_size("glossary_search", {"hits": ["a", "b"]})


def test_the_44kb_bomb_is_rejected():
    with pytest.raises(ResultTooLargeError) as ei:
        _check_size("glossary_list_system_standards", {"blob": "x" * 44_254})
    err = ei.value
    assert err.tool == "glossary_list_system_standards"
    assert err.size > 44_000
    # actionable for BOTH readers: the model (do not retry) and the human (fix the tool)
    msg = str(err)
    assert "BUG IN THE TOOL" in msg
    assert "Do not retry" in msg
    assert "paginate" in msg


def test_it_is_on_by_default():
    """A soft warning gets filed under 'known noise' inside a week. An error gets the tool
    fixed. This fails if anyone makes the gate opt-in."""
    assert result_max_bytes() == 32_000
    with pytest.raises(ResultTooLargeError):
        _check_size("some_tool", {"blob": "x" * 33_000})


def test_the_ceiling_is_tunable(monkeypatch):
    monkeypatch.setenv("LW_MCP_RESULT_MAX_BYTES", "50")
    with pytest.raises(ResultTooLargeError):
        _check_size("tiny", {"blob": "x" * 200})
    monkeypatch.setenv("LW_MCP_RESULT_MAX_BYTES", "100000")
    _check_size("tiny", {"blob": "x" * 200})


def test_a_large_but_legal_result_warns_and_passes(caplog):
    monkeypatch_warn = result_warn_bytes()
    assert monkeypatch_warn == 8_000
    with caplog.at_level("WARNING"):
        _check_size("book_get_chapter", {"prose": "x" * 12_000})
    assert any("crowd the caller's context" in r.message for r in caplog.records)
