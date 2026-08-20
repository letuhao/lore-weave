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
from pydantic import BaseModel, ConfigDict, ValidationError

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


def _render_input(value: object, *, limit: int = 80) -> str:
    """Describe what the caller actually sent, preferring the VALUE over its type.

    The clause used to read ``(you sent a {type.__name__})``, so a model that sent
    ``unit_index: -1`` against a ``minimum: 0`` bound was told 'you sent a int' — a fact it
    already knew, and not the one it needed. The value is what lets a caller see its own
    mistake: -1 versus 0, or a uuid with a duplicated group (TOOLV2 LOOP #172; the same
    argument that #148 had to hand-roll for uuid parsing in composition-service).

    Long or unprintable inputs fall back to the type, because a refusal that pastes an entire
    document back at the model is its own failure — the clause has to stay one readable line.
    """
    try:
        shown = repr(value)
    except Exception:  # noqa: BLE001 — a repr that raises must not break the refusal
        return f"a {type(value).__name__}"
    if len(shown) > limit:
        return f"a {type(value).__name__} of {len(shown)} chars"
    return shown


def validation_directive(tool_name: str, exc: ValidationError, *, max_errors: int = 3) -> str:
    """One line per failing argument: what pydantic expected, and what was actually sent.

    🔴 **THE TYPE CLAUSE USED TO LIE, AND IT LIED ON THE MOST COMMON FAILURE THERE IS.**
    Three services carried a byte-identical copy of this function, each rendering
    ``(you sent a {type(err["input"]).__name__})`` for every error. For a ``missing`` error
    pydantic sets ``input`` to the PARENT object — there is no field value, because the field
    was never sent — so the clause reported the type of the arguments dict and the model was
    told ``fact_text: Field required (you sent a dict)`` when it had sent no arguments at all.

    Measured before the fix: **79 calls, 7 tools, 16 sessions, and in 100% of them the args
    were `{}`.** Every single rendering of that clause was false, and it pointed the model at a
    type error it had not made. One of those models then tried the field as a differently-typed
    argument, which is what a misattributed cause does to a caller that trusts it.

    So a ``missing`` error now says what is true — the field is absent — and, when the model
    sent nothing at all, says that too, because "you sent no arguments" is the one fact that
    distinguishes an empty call from a wrong one. Non-``missing`` errors keep the type clause,
    where ``input`` really is the offending value and the clause was always correct.

    Lives in the kit because all three copies said it should: each carried the comment "the
    loreweave_mcp kit will absorb the shared copy later", and three copies is how one of them
    drifts.
    """
    parts: list[str] = []
    errs = exc.errors(include_url=False)
    sent_nothing = all(
        err.get("type") == "missing" and isinstance(err.get("input"), dict) and not err["input"]
        for err in errs
    ) and bool(errs)
    for err in errs[:max_errors]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "arguments"
        msg = err.get("msg", "invalid value")
        if err.get("type") == "missing":
            # No value exists to describe. `input` here is the parent object, not the field.
            parts.append(f"`{loc}`: {msg}")
        else:
            parts.append(f"`{loc}`: {msg} (you sent {_render_input(err.get('input'))})")
    if len(errs) > max_errors:
        parts.append(f"(+{len(errs) - max_errors} more)")
    tail = (
        " You sent no arguments at all — supply the required ones and call the tool again."
        if sent_nothing
        else " Fix the argument and call the tool again."
    )
    return f"invalid arguments for {tool_name} — " + "; ".join(parts) + "." + tail
