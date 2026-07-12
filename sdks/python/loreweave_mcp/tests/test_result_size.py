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


def test_the_44kb_bomb_WARNS_and_a_true_runaway_FAILS(caplog):
    # The 44KB bomb is BELOW the catastrophe ceiling (a review proved a low hard-fail bricks
    # 88.7% of books on legitimate reads). It is caught by the WARN — which is the "find
    # broken tools" mechanism — and was in fact found that way, then fixed.
    with caplog.at_level("WARNING"):
        _check_size("glossary_list_system_standards", {"blob": "x" * 44_254})
    assert any("crowd the caller's context" in r.message for r in caplog.records)

    # A genuine runaway (an unbounded list) still hard-FAILS.
    with pytest.raises(ResultTooLargeError) as ei:
        _check_size("some_unbounded_list", {"blob": "x" * 600_000})
    msg = str(ei.value)
    assert "BUG IN THE TOOL" in msg
    assert "Do not retry" in msg
    assert "paginate" in msg


def test_it_is_on_by_default():
    """The gate must be active with no env configured — a runaway over the default ceiling
    is rejected out of the box. Fails if anyone makes it opt-in."""
    assert result_max_bytes() == 512_000
    with pytest.raises(ResultTooLargeError):
        _check_size("some_tool", {"blob": "x" * 520_000})


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


# ── the WIRE test the review demanded ────────────────────────────────────────
#
# The tests above call the private _check_size directly. That proves the CHECK works; it
# proves NOTHING about whether the check is CONNECTED — and the first cut shipped a Python
# gate that was a complete NO-OP, keyed on output_schema (None for every `-> dict` tool), and
# every _check_size unit test stayed green. So this drives a REAL FastMCP tool, annotated
# `-> dict` (the annotation EVERY real tool in this repo uses — `dict[str, Any]` would pass
# while missing the bug), through the real run path.
import asyncio

import pytest


@pytest.mark.asyncio
async def test_the_gate_fires_on_a_real_dict_tool_through_Tool_run(monkeypatch):
    from mcp.server.fastmcp.tools.base import Tool

    from loreweave_mcp.compact_content import ResultTooLargeError, patch_tool_run_size_gate

    patch_tool_run_size_gate()
    monkeypatch.setenv("LW_MCP_RESULT_MAX_BYTES", "2000")

    # a tool with the EXACT annotation every real tool in the repo uses
    def big_tool() -> dict:
        return {"blob": "x" * 5000}

    tool = Tool.from_function(big_tool)
    with pytest.raises((ResultTooLargeError, Exception)) as ei:
        await tool.run({})
    # the tool NAME must be in the failure (the whole WARN/ERROR tier is unactionable
    # otherwise — the first cut logged tool=unknown_tool for everything)
    assert "big_tool" in str(ei.value)


@pytest.mark.asyncio
async def test_a_normal_dict_tool_still_works_through_Tool_run():
    from mcp.server.fastmcp.tools.base import Tool

    from loreweave_mcp.compact_content import patch_tool_run_size_gate

    patch_tool_run_size_gate()

    def small_tool() -> dict:
        return {"ok": True, "answer": "a reasonable size"}

    tool = Tool.from_function(small_tool)
    result = await tool.run({})
    assert result == {"ok": True, "answer": "a reasonable size"}
