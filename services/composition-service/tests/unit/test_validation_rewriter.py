"""TOOLV2 LOOP #90 — composition-service was the last service leaking raw pydantic dumps.

Measured across the corpus, raw dumps by owning service: composition 58 across 8 tools and 9
sessions (last 2026-07-30), kg 8, translation 3, jobs 1, memory 1. Every one of the others
predates the rewriter shipping in their own service. Composition never had it, so it was the
only live producer — and what it emitted included the errors.pydantic.dev URL, which is noise a
model cannot act on.
"""

from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, ValidationError


class _Args(BaseModel):
    book_id: str


def _validation_error() -> ValidationError:
    with pytest.raises(ValidationError) as exc:
        _Args()
    return exc.value


def test_THE_SERVER_REWRITES_A_VALIDATION_ERROR_INTO_ONE_LINE():
    """Asserted through the installed wrapper, not by calling the kit helper — a helper-level
    test stays green when the install is removed, which has happened repeatedly in this loop."""
    from app.mcp import server

    async def _raise(name, arguments, *a, **k):
        raise ToolError("wrapped") from _validation_error()

    manager = server.mcp_server._tool_manager
    original = manager.call_tool
    manager.call_tool = _raise
    try:
        server._install_validation_error_rewriter(server.mcp_server)
        rewritten = manager.call_tool
    finally:
        pass

    import asyncio

    with pytest.raises(ToolError) as exc:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            rewritten("composition_package_tree", {})
        )
    manager.call_tool = original

    msg = str(exc.value)
    assert "invalid arguments for composition_package_tree" in msg, msg
    assert "`book_id`: Field required" in msg, msg
    # The two things that made the raw dump unusable.
    assert "pydantic.dev" not in msg, f"the doc URL must not reach the model: {msg}"
    assert "\n" not in msg, f"the directive is ONE line: {msg!r}"
    # And iteration 65's correction must hold here too: a missing field has no sent value.
    assert "you sent a" not in msg, msg


def test_A_NON_VALIDATION_TOOLERROR_PASSES_THROUGH_UNTOUCHED():
    """The rewriter must not swallow or reword a real tool failure."""
    from app.mcp import server

    async def _raise(name, arguments, *a, **k):
        raise ToolError("not found or not accessible")

    manager = server.mcp_server._tool_manager
    original = manager.call_tool
    manager.call_tool = _raise
    try:
        server._install_validation_error_rewriter(server.mcp_server)
        rewritten = manager.call_tool
        import asyncio

        with pytest.raises(ToolError) as exc:
            asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
                rewritten("composition_get_work", {})
            )
        assert str(exc.value) == "not found or not accessible"
    finally:
        manager.call_tool = original


def test_THE_REWRITER_IS_INSTALLED_AT_IMPORT_NOT_MERELY_DEFINED():
    """The guard the other two could not be.

    Both tests above call `_install_validation_error_rewriter` themselves, so they prove the
    WRAPPER and stay green when the module-level install line is deleted — verified by deleting
    it. A defined-but-uninstalled rewriter is exactly the shape this loop keeps finding, so the
    install gets its own assertion: the manager's `call_tool` must already be our closure.
    """
    from app.mcp import server

    got = server.mcp_server._tool_manager.call_tool
    assert getattr(got, "__qualname__", "").startswith("_install_validation_error_rewriter"), (
        "composition-service must install the validation rewriter at import; the tool manager's "
        f"call_tool is {getattr(got, '__qualname__', got)!r}, which is the unwrapped original — "
        "raw pydantic dumps would reach the model again"
    )

