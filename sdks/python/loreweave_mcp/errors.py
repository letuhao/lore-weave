"""Shared arg-model base + the uniform not-accessible error (H13).

`ForbidExtra` is the `extra="forbid"` Pydantic base every tool arg model extends
(INV-2) — an unexpected/injected field is rejected, so the LLM cannot smuggle an
identity/scope id past the envelope.

`uniform_not_accessible` collapses "you don't have access" (403) and "it doesn't
exist" (404) into ONE indistinguishable error so a tool can't be used as an
enumeration oracle (H13): a denied caller and a non-existent resource look
identical, so the agent can't probe which book ids exist by watching the error.
"""

from __future__ import annotations

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, ConfigDict

__all__ = ["ForbidExtra", "NotAccessibleError", "uniform_not_accessible"]

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
