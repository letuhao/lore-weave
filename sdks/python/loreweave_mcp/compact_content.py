"""External MCP discoverability audit #9 — payload duplication.

Every structured FastMCP tool result comes back as BOTH `structuredContent`
(the real, parsed JSON) AND `content[0].text` (the SAME payload, JSON-dumped
again) — confirmed via ``mcp.server.fastmcp.utilities.func_metadata.
FuncMetadata.convert_result`` (mcp 1.28.1, the version every Python MCP
provider in this repo resolves to): when the tool has an output schema, it
UNCONDITIONALLY builds ``unstructured_content = _convert_to_content(result)``
(a full ``pydantic_core.to_json`` dump) alongside ``structured_content`` and
returns both. Confirmed live: ~2x tokens on every large read
(``glossary_book_ontology_read``, ``jobs_list``, chapter bodies) — the exact
opposite of the whole reason `find_tools`/`invoke_tool` exist (keep token
usage down for LLM callers).

Unlike the Go SDK (`sdks/go/loreweave_mcp.RegisterTool` — a handler can leave
`Content` nil and the SDK fills a fallback only then), FastMCP exposes NO
per-tool escape hatch: the duplication is built inside `convert_result`
itself, called by the low-level dispatch with no override point a service's
own tool-handler code can influence. The only way to change this behavior
without forking FastMCP is a monkeypatch of `convert_result` — applied ONCE,
in this one shared place, rather than by each of 5 Python MCP services
independently reinventing it.

Deliberately DEFENSIVE: `convert_result` is FastMCP's own private/internal
method, not a stable public API — a future `mcp` release could change its
signature or remove it entirely. `patch_convert_result()` therefore NEVER
raises: if the target doesn't look like what this patch expects, it logs a
warning and leaves FastMCP's original (duplicating) behavior in place. A
find_tools/tool-call response staying 2x its ideal size is a token-budget
regression; a service that fails to START because a patch broke is a much
worse one to accept in exchange for a purely cosmetic savings.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

__all__ = ["patch_convert_result", "ResultTooLargeError", "result_max_bytes", "result_warn_bytes"]

_PATCHED_ATTR = "_loreweave_compact_content_patched"
_PLACEHOLDER_TEXT = "ok — see structuredContent for the full result"


# ── the HARD CAP on what an MCP tool may return ──────────────────────────────
#
# Mirrors the Go SDK's gate (sdks/go/loreweave_mcp/result_size.go) so a Python tool cannot
# do what a Go tool now cannot.
#
# A tool's result lands verbatim in the calling agent's context window. A tool that returns
# more than the agent can hold is not merely wasteful — it is destructive, and it fails in a
# way that looks like a MODEL problem rather than a TOOL problem, which is why it survived
# so long here:
#
#   Measured 2026-07-12: `glossary_list_system_standards` returned **44,254 characters**
#   (~11k tokens — a THIRD of a chat turn's entire budget) by inlining every kind's full
#   attribute definitions: 86% of the payload, none of it actionable (you adopt a standard by
#   CODE). In a live run gemma called it TWENTY-FOUR times and built nothing — each call
#   pushed the previous answer further out of the window, so the model could never see what
#   it had already fetched. Every unit test was green. The tool "worked".
#
# A tool whose result cannot fit in the context of the agent that calls it is not a tool. It
# is a context bomb with a friendly description. So the SDK refuses to ship one.
#
# Deliberately a HARD ERROR, deliberately ON BY DEFAULT: a warning would be filed under
# "known noise" inside a week; an error gets the tool fixed. Ratchet MAX down as tools are
# fixed — no tool should ever need half of it.
_DEFAULT_WARN_BYTES = 8_000
_DEFAULT_MAX_BYTES = 32_000


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
    return default


def result_warn_bytes() -> int:
    return _env_int("LW_MCP_RESULT_WARN_BYTES", _DEFAULT_WARN_BYTES)


def result_max_bytes() -> int:
    return _env_int("LW_MCP_RESULT_MAX_BYTES", _DEFAULT_MAX_BYTES)


class ResultTooLargeError(ValueError):
    """Raised when a tool's structured result exceeds the hard ceiling.

    The message is written for two readers at once: the agent (which must not retry) and the
    human who has to go fix the tool."""

    def __init__(self, tool: str, size: int, maximum: int) -> None:
        self.tool, self.size, self.maximum = tool, size, maximum
        super().__init__(
            f"tool {tool!r} returned {size} bytes, over the {maximum}-byte MCP result "
            "ceiling. This is a BUG IN THE TOOL, not in the caller: a result this large does "
            "not fit in the context of the agent that called it, and it will crowd out the "
            "very question it was meant to answer. Do not retry it. Fix the tool: return a "
            "summary or the identifiers the caller can act on, paginate, or split the "
            "drill-down into a second tool."
        )


def _check_size(tool: str, structured) -> None:
    try:
        payload = json.dumps(structured, default=str)
    except Exception:  # noqa: BLE001 — not our failure to diagnose
        return
    n = len(payload)
    maximum = result_max_bytes()
    if n > maximum:
        logger.error(
            "mcp tool result EXCEEDS the hard ceiling — failing the call: "
            "tool=%s bytes=%d max=%d", tool, n, maximum,
        )
        raise ResultTooLargeError(tool, n, maximum)
    warn = result_warn_bytes()
    if n > warn:
        logger.warning(
            "mcp tool result is large — it will crowd the caller's context window: "
            "tool=%s bytes=%d (warn>%d, hard max %d)", tool, n, warn, maximum,
        )


def patch_convert_result() -> bool:
    """Monkeypatch ``FuncMetadata.convert_result`` so the unstructured
    ``content`` half of a structured tool result becomes a short constant
    placeholder instead of a full duplicate JSON dump.

    Idempotent — safe to call from multiple services/modules in the same
    process; the second+ call is a no-op (checked via a sentinel attribute
    on the class, not a module-level flag, so it holds even if this module
    is imported under two different paths).

    Returns ``True`` if the patch was applied (or already had been),
    ``False`` if it was skipped because the expected internal shape wasn't
    found (never raises — see module docstring).
    """
    try:
        from mcp.server.fastmcp.utilities import func_metadata as _fm
        from mcp.types import CallToolResult, TextContent
    except Exception:
        logger.warning(
            "loreweave_mcp.compact_content: could not import FastMCP internals "
            "(mcp package missing/changed) — skipping the payload-dedup patch; "
            "tool results will keep the SDK's default (duplicated) shape.",
            exc_info=True,
        )
        return False

    cls = _fm.FuncMetadata
    if getattr(cls, _PATCHED_ATTR, False):
        return True

    if not hasattr(cls, "convert_result"):
        logger.warning(
            "loreweave_mcp.compact_content: FuncMetadata.convert_result not "
            "found — mcp package shape has changed since this patch was "
            "written; skipping (tool results will keep the SDK default).",
        )
        return False

    original = cls.convert_result

    def convert_result(self, result):  # noqa: ANN001 - mirrors FastMCP's own untyped signature
        # A CallToolResult the tool built itself is passed through unchanged —
        # this patch only ever touches the SDK's OWN auto-generated duplicate,
        # never a result a handler deliberately constructed.
        if isinstance(result, CallToolResult):
            return original(self, result)
        if getattr(self, "output_schema", None) is None:
            # No structured output configured — nothing to dedupe against.
            return original(self, result)
        converted = original(self, result)
        if not (isinstance(converted, tuple) and len(converted) == 2):
            # Unexpected shape (a future mcp version changed the contract) —
            # return the original untouched rather than guess.
            return converted
        _unstructured, structured = converted
        # THE RESULT-SIZE GATE. Every structured Python MCP tool result flows through
        # convert_result, so this is the one place that can guarantee no Python tool ships a
        # payload its caller cannot hold. Raises ResultTooLargeError → the call fails loudly
        # with a message that tells the agent not to retry and tells the author what to fix.
        _check_size(getattr(self, "name", None) or "unknown_tool", structured)
        return [TextContent(type="text", text=_PLACEHOLDER_TEXT)], structured

    convert_result.__wrapped__ = original
    setattr(cls, _PATCHED_ATTR, True)
    cls.convert_result = convert_result
    return True
