"""K17 — a failed tool call must set `isError`, and an idempotent no-op must NOT.

composition-service had 60 sites returning `{"success": False, …}` as a NORMAL result, so
the MCP envelope said `isError: false` and a failure was indistinguishable from a success at
the protocol level. knowledge-service already fixed this (D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR);
the fix was never propagated.

The two things these tests must hold together, because getting either alone is worse than
the bug:
  * a real failure raises ⇒ `isError: true`, with a C4-shaped body so the first-party error
    prose does NOT regress;
  * `outcome: applied_conflict` (an idempotent no-op K13 audited as CORRECT) stays a normal
    result — flagging it would repeat S2b, where `created: 0` was read as failure and the
    agent told the user "I can't save that".
"""
from __future__ import annotations

import json

import pytest

from loreweave_mcp.error_signal import failure_message, patch_error_signal


class TestFailureMessage:
    def test_a_plain_failure_becomes_a_c4_body(self):
        body = failure_message({"success": False, "error": "invalid edge"})
        assert json.loads(body) == {"message": "invalid edge"}

    def test_the_key_is_message_not_error(self):
        # chat-service's `_error_envelope` decodes {"code"?, "message", "detail"?} and
        # otherwise falls back to the RAW TEXT. Emitting `error` would hand the model a
        # JSON blob where it used to get a clean sentence — fixing the protocol signal by
        # regressing the prose the model actually reads.
        body = json.loads(failure_message({"success": False, "error": "nope"}))
        assert "message" in body and "error" not in body

    def test_code_and_detail_survive(self):
        body = json.loads(failure_message({
            "success": False, "error": "missing", "code": "COMP_X", "detail": {"missing": ["a"]},
        }))
        assert body["code"] == "COMP_X" and body["detail"] == {"missing": ["a"]}

    def test_applied_conflict_is_NOT_a_failure(self):
        # The carve-out that makes this patch safe.
        assert failure_message({
            "success": False, "outcome": "applied_conflict", "error": "that edge already exists",
        }) is None

    def test_any_declared_outcome_is_treated_as_a_recognised_result(self):
        assert failure_message({"success": False, "outcome": "skipped_exists"}) is None

    def test_a_success_is_not_a_failure(self):
        assert failure_message({"success": True, "id": "1"}) is None
        assert failure_message({"id": "1"}) is None

    def test_non_dict_payloads_are_survived(self):
        assert failure_message(None) is None
        assert failure_message("text") is None
        assert failure_message([1, 2]) is None

    def test_a_failure_with_no_error_text_still_gets_a_message(self):
        # Never emit an empty message — an error the model cannot read is a silent failure
        # wearing an error's clothes.
        assert json.loads(failure_message({"success": False}))["message"]


async def _failing_tool(x: str) -> dict:
    return {"success": False, "error": "invalid edge (self-link, cycle, or cross-tier)"}


async def _conflict_tool(x: str) -> dict:
    return {"success": False, "outcome": "applied_conflict", "error": "that edge already exists"}


async def _ok_tool(x: str) -> dict:
    return {"success": True, "echo": x}


class TestAgainstARealFastMCPServer:
    """Proven end to end — a correct predicate that the server never consults is the
    silent-no-op shape this repo keeps rediscovering."""

    @pytest.fixture
    def server(self):
        from mcp.server.fastmcp import FastMCP

        patch_error_signal()
        mcp = FastMCP("k17-test")
        mcp.tool(name="failing", description="fails")(_failing_tool)
        mcp.tool(name="conflict", description="idempotent no-op")(_conflict_tool)
        mcp.tool(name="ok", description="succeeds")(_ok_tool)
        return mcp

    @pytest.mark.asyncio
    async def test_a_failure_raises_so_the_sdk_sets_isError(self, server):
        from mcp.server.fastmcp.exceptions import ToolError

        with pytest.raises(ToolError) as exc:
            await server.call_tool("failing", {"x": "a"})
        text = str(exc.value)
        # The SDK PREFIXES the message: `Error executing tool <name>: {c4 body}`. That is
        # not cosmetic — chat-service's `_error_envelope` keys on `startswith("{")`, so the
        # prefix is exactly why its C4 decoding never fired in production (K18, fixed
        # alongside this). Assert the real wire text, not the idealised body.
        assert text.startswith("Error executing tool failing: ")
        body = json.loads(text.split(": ", 1)[1])
        assert body["message"] == "invalid edge (self-link, cycle, or cross-tier)", (
            "the model must still read the SAME sentence it read before the patch"
        )

    @pytest.mark.asyncio
    async def test_an_idempotent_no_op_is_still_a_NORMAL_result(self, server):
        # Must NOT raise. This is the S2b guard: an "already exists" no-op reported as an
        # error makes the agent apologise for work it correctly did not need to do.
        out = await server.call_tool("conflict", {"x": "a"})
        assert "already exists" in str(out)

    @pytest.mark.asyncio
    async def test_a_success_is_untouched(self, server):
        out = await server.call_tool("ok", {"x": "hello"})
        assert "hello" in str(out)

    @pytest.mark.asyncio
    async def test_argument_validation_still_runs_through_the_original_signature(self, server):
        # The patch swaps `tool.fn` only; fn_metadata was built from the ORIGINAL signature
        # and functools.wraps preserves it. If the swap had broken that, a missing required
        # arg would sail through instead of failing.
        with pytest.raises(Exception):
            await server.call_tool("ok", {})

    def test_the_patch_is_idempotent(self):
        assert patch_error_signal() is True
        assert patch_error_signal() is True
