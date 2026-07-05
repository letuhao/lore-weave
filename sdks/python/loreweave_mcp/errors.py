"""Shared arg-model base + the uniform not-accessible error (H13).

`ForbidExtra` is the `extra="forbid"` Pydantic base every tool arg model extends
(INV-2) — an unexpected/injected field is rejected, so the LLM cannot smuggle an
identity/scope id past the envelope.

`TolerantArgs` is the IN-5 (mcp-tool-io.md) sibling: same identity-smuggling
protection (still never declares user_id/session_id, so a hallucinated one is
inert either way), but `extra="ignore"` instead of `extra="forbid"` — a harmless
unknown field a weak model adds doesn't hard-fail the whole call. Ports the Go MCP
kit's `relaxAdditionalProps` (`services/glossary-service/internal/api/tool_helpers.go`)
intent to Python; Go opens `additionalProperties` on the JSON Schema itself, Pydantic
has no schema-level equivalent, so this achieves the same effect via `extra="ignore"`
at the model layer instead.

`uniform_not_accessible` collapses "you don't have access" (403) and "it doesn't
exist" (404) into ONE indistinguishable error so a tool can't be used as an
enumeration oracle (H13): a denied caller and a non-existent resource look
identical, so the agent can't probe which book ids exist by watching the error.
"""

from __future__ import annotations

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict

__all__ = ["ForbidExtra", "TolerantArgs", "NotAccessibleError", "uniform_not_accessible"]

# The single user-facing message for both "denied" and "missing". Deliberately
# does NOT reveal which of the two it is.
NOT_ACCESSIBLE_MESSAGE = "not found or not accessible"


class ForbidExtra(BaseModel):
    """Base arg model: reject any field not declared on the schema (INV-2).

    Identity/scope ids (user_id, session_id, project_id) are NEVER declared on a
    tool arg model — they come from the envelope (`build_tool_context`). Combined
    with `extra="forbid"`, an LLM that tries to supply `user_id` as an argument is
    rejected rather than silently impersonating someone.
    """

    model_config = ConfigDict(extra="forbid")


class TolerantArgs(BaseModel):
    """Base arg model: SILENTLY DROP any field not declared on the schema,
    rather than rejecting the call (IN-5, mcp-tool-io.md).

    Identity/scope ids are still NEVER declared here — the same rule as
    `ForbidExtra` — so this is not a weaker security posture, only a friendlier
    failure mode for a genuinely harmless extra: a weak model hallucinating a
    plausible-looking field (the standard's cited incident: gemma sent an
    `old_value` kwarg that 409'd an otherwise-valid `glossary_book_patch` call
    under the Go kit's un-relaxed default) gets silently ignored instead of a
    hard validation error the model then has to recover from.

    Prefer `ForbidExtra` for a tool where an unexpected field should be loud
    (e.g. you want a schema-drift bug in a CALLER to fail fast in CI); prefer
    `TolerantArgs` for a tool a weak model calls directly and often, where a
    self-correcting "keep going" beats an extra retry loop.
    """

    model_config = ConfigDict(extra="ignore")


class NotAccessibleError(ToolError):
    """The H13 uniform error. A `ToolError` so FastMCP surfaces it as a clean
    tool-level failure (not a 5xx)."""


def uniform_not_accessible(exc: BaseException | None = None) -> NotAccessibleError:
    """Return the single, indistinguishable "not found or not accessible" error
    (H13) — for BOTH a permission denial and a missing resource.

    Pass the underlying exception (if any) only so it can be chained for server
    logs via `raise uniform_not_accessible(exc) from exc`; the *message* is always
    identical regardless of `exc`, so nothing about the real cause leaks to the
    caller / chat context.
    """
    err = NotAccessibleError(NOT_ACCESSIBLE_MESSAGE)
    if exc is not None:
        err.__cause__ = exc
    return err
