"""K17 — a failed tool call must say so in `isError`, not only inside its payload.

THE BUG. composition-service has 60 return sites shaped `{"success": False, "error": …}`.
Returning normally means the MCP envelope carries `isError: false`, so at the protocol level
a failure is indistinguishable from a success; the only evidence is prose inside the result.
Live example: `composition_motif_link_create` refusing an invalid edge came back
`isError: false` with `{"success": false, "error": "invalid edge (self-link, cycle, or
cross-tier)"}` in the text.

knowledge-service already fixed exactly this (D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR — "raises
on a tool failure, and its error text is the C4-shaped JSON body"). The fix was never
propagated, so the sibling service kept the old behaviour.

SCOPE, HONESTLY. This is NOT a first-party production bug: chat-service's MCP client
explicitly re-reads `payload.get("success") is False` and converts it, so the model and the
telemetry do see the failure. The exposure is the PUBLIC MCP surface (mcp-public-gateway,
OAuth scope `domain:*`), where an external client that follows the MCP spec — reading
`isError`, as it should — reads our failures as successes. It also silently fooled this
repo's own K13 idempotency probe, which keyed on `isError` and therefore scored two
correct conflict-rejections as passes.

THE `applied_conflict` CARVE-OUT — the part that makes this safe. Of the 60 sites, 16 return
`{"success": False, "outcome": "applied_conflict"}`, which is an IDEMPOTENT NO-OP ("that
already exists"), not a failure — K13 audited those tools and confirmed they are correct.
Flagging them as errors would repeat S2b, where `created: 0` on a correct no-op was read as
failure and the agent told the user *"I can't save that"*. So a payload that declares an
`outcome` is treated as a recognised, non-error result and passes through untouched.

WHY THE ERROR TEXT IS C4-SHAPED. Marking `isError` alone would REGRESS the first-party path:
chat-service's `_error_envelope` decodes `{"code"?, "message", "detail"?}` and otherwise
falls back to the raw text — so a bare `{"success": false, "error": …}` would reach the model
as a JSON blob instead of today's clean sentence. Re-shaping `error` → `message` keeps the
model's prose byte-identical while fixing the protocol signal. Both consumers win; neither
regresses.

Applied once per process from `make_stateless_fastmcp`, in the same defensive style as the
other kit patches: idempotent, and a no-op with a warning if the SDK's shape changes.
"""

from __future__ import annotations

import functools
import json
import logging

logger = logging.getLogger(__name__)

_PATCHED = "_lw_error_signal_patched"


def failure_message(payload) -> str | None:
    """Return the C4-shaped error body for a FAILED tool payload, else None.

    A dict with `success is False` is a failure UNLESS it declares an `outcome` — the
    marker for a recognised non-error result (today: `applied_conflict`, an idempotent
    no-op). Pure function; unit-tested directly.
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("success") is not False:
        return None
    if payload.get("outcome") is not None:
        return None
    body: dict = {"message": str(payload.get("error") or "tool error")}
    if payload.get("code") is not None:
        body["code"] = payload["code"]
    if payload.get("detail") is not None:
        body["detail"] = payload["detail"]
    return json.dumps(body, ensure_ascii=False)


def patch_error_signal() -> bool:
    """Make a `{"success": False}` return raise, so the SDK's own error path sets `isError`.

    Wrapping the tool FUNCTION (rather than fabricating a result downstream) means the
    envelope, the content shape, and the logging all stay the SDK's — we only decide WHEN
    it is an error.
    """
    try:
        from mcp.server.fastmcp.exceptions import ToolError
        from mcp.server.fastmcp.tools.tool_manager import ToolManager
    except Exception:
        logger.warning(
            "loreweave_mcp.error_signal: could not import FastMCP internals — skipping; "
            "a failed tool keeps returning isError=false.",
            exc_info=True,
        )
        return False

    if getattr(ToolManager, _PATCHED, False):
        return True
    if not hasattr(ToolManager, "add_tool"):
        logger.warning(
            "loreweave_mcp.error_signal: ToolManager.add_tool not found — the mcp package "
            "shape has changed since this patch was written; skipping.",
        )
        return False

    _orig_add = ToolManager.add_tool

    def add_tool(self, fn, *a, **kw):
        tool = _orig_add(self, fn, *a, **kw)
        inner = tool.fn
        if getattr(inner, "_lw_error_signal_wrapped", False):
            return tool

        @functools.wraps(inner)
        async def wrapped(*args, **kwargs):
            result = await inner(*args, **kwargs)
            body = failure_message(result)
            if body is not None:
                raise ToolError(body)
            return result

        wrapped._lw_error_signal_wrapped = True  # noqa: SLF001
        # Only the callable is swapped. `fn_metadata` was built from the ORIGINAL signature
        # and functools.wraps preserves it, so argument validation is untouched.
        tool.fn = wrapped
        return tool

    ToolManager.add_tool = add_tool
    setattr(ToolManager, _PATCHED, True)
    return True
