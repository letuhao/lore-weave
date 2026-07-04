"""L3 (Context Budget Law §6a) — concise tool-result wire serialization.

Single funnel for every model-facing tool-result ``content`` string in the chat
turn loop (``stream_service._stream_with_tools`` + the resume path). Two jobs:

1. ``ensure_ascii=False`` — kill the ``\\uXXXX`` tax. Under Python's default
   ``ensure_ascii=True`` a Vietnamese ``Lâm Uyển`` serializes to
   ``L\\u00e2m Uy\\u1ec3n`` — a ~2–3× byte inflation on VI/CJK content that the
   model then pays for as input tokens (the 146K case study, spec §1).
2. drop-``None`` — omit fields whose value is ``null`` (the common MCP
   optional-field padding), recursively, WITHOUT dropping semantically-meaningful
   values. Empty containers are DELIBERATELY KEPT: ``{"results": []}`` is a
   "searched, found nothing" signal the model must still see, and ``0`` / ``False``
   / ``""`` are meaningful scalars (``{"success": false}`` must survive).

This affects ONLY the bytes the model reads. The FE ``result`` chunk and DB
persistence use the raw dict on separate seams, so trimming here never changes
what the UI shows or what is stored.

One helper, one language, zero domain-tool edits — fixes the wire for all 94
MCP tools at once (spec §14a; this is tier **T0**).
"""

from __future__ import annotations

import json
from typing import Any

from loreweave_context.tokens import estimate_tokens


def prune_none(value: Any) -> Any:
    """Recursively drop dict keys whose value is ``None``.

    Empty containers (``{}``, ``[]``) and falsy scalars (``0``, ``False``, ``""``)
    are preserved — see the module docstring for why. Lists recurse element-wise
    (indices are preserved; ``None`` elements are kept, since a list position can
    be load-bearing).
    """
    if isinstance(value, dict):
        return {k: prune_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [prune_none(v) for v in value]
    return value


def tool_result_content(payload: Any) -> str:
    """Serialize a tool result into the model-facing ``content`` string (L3).

    ``default=str`` is a robustness belt (payloads are post-JSON-parse from the
    gateway envelope and already pure-JSON, but locally-built payloads —
    subagent, compose_prose — could carry a stray non-JSON type; better to
    stringify than crash the turn).
    """
    return json.dumps(prune_none(payload), ensure_ascii=False, default=str)


def _overflow_error(*, tokens: int, cap: int, tool_name: str | None) -> str:
    """The D7 self-correcting overflow notice (spec §7, L5/D7). A single tool result
    that alone blows the per-contributor ceiling is WITHHELD and replaced with an
    actionable error naming the size + the exact remedies (which map to T1's
    `apply_response_contract` knobs: detail / limit / fields / get-by-id) — never a
    silent truncation (the cross-cutting "self-correcting, never silent" rule), and
    never a window-blowing dump. The model re-calls at a smaller scope, so the turn is
    preserved rather than broken."""
    tool = tool_name or "the tool"
    return tool_result_content({
        "error": "tool_result_overflow",
        "tool": tool_name,
        "tokens": tokens,
        "cap": cap,
        "message": (
            f"The result from `{tool}` is ~{tokens} tokens, over the {cap}-token "
            "per-result budget, so it was withheld to protect the context window. "
            f"Re-call `{tool}` with a smaller scope — e.g. `detail=summary`, a `limit`, "
            "a `fields` subset, or a specific id/range — then fetch details on demand."
        ),
    })


def tool_result_content_capped(
    payload: Any, *, tool_name: str | None = None, token_cap: int | None
) -> str:
    """L3 + D7: serialize a tool result, but if it ALONE exceeds `token_cap` (the
    per-contributor ceiling), withhold it and return the self-correcting overflow
    notice instead (see `_overflow_error`). `token_cap` None or ≤0 disables the cap
    (byte-identical to `tool_result_content`). Apply ONLY to re-requestable data-dump
    results (the generic MCP dispatch) — NOT to generative outputs like `{"prose": …}`,
    which are legitimately large and cannot be re-requested smaller."""
    content = tool_result_content(payload)
    if token_cap and token_cap > 0:
        est = estimate_tokens(content)
        if est > token_cap:
            return _overflow_error(tokens=est, cap=token_cap, tool_name=tool_name)
    return content
