"""Public MCP-key spend attribution carrier (P4 / Wave-C, slice D).

A public MCP-key call traverses ``mcp-public-gateway → ai-gateway → domain
service → provider-registry``. The ``X-Mcp-Key-Id`` / ``X-Mcp-Spend-Cap-Usd``
headers minted at the edge **die** on the domain-service→provider-registry hop:
``Client.submit_job`` builds a fresh typed request and does not forward ambient
headers. So the carrier across that hop is ``job_meta`` — bridged here via a
contextvar set per-call (by ``loreweave_mcp.build_tool_context``) and merged into
``job_meta`` at the single submit chokepoint (``Client.submit_job``).

This mirrors the ``campaign_id`` contextvar pattern (translation-service
``app/llm_client.py``) but lives in the SHARED SDK because ``mcp_key_id`` is
cross-cutting — any public call, any domain — unlike ``campaign_id``, which is
translation-specific and so lives in that service's own wrapper.

SECURITY: these are SERVER-SET attribution — the edge minted the key id + cap
from the authenticated ``/internal/mcp-keys/resolve``. They **overwrite** any
caller-supplied ``job_meta`` value (a public agent must not be able to spoof its
own key id or raise its own spend cap by stuffing ``job_meta``). Contrast with
``campaign_id``, which lets an explicit caller value win.
"""

from __future__ import annotations

import contextvars
from typing import Any

# Per-async-task carriers. Default None → a first-party call (which never sets
# them) carries no attribution and is never per-key capped.
_mcp_key_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "loreweave_mcp_key_id", default=None,
)
_spend_cap_usd_ctx: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "loreweave_mcp_spend_cap_usd", default=None,
)


def set_public_key_attribution(
    mcp_key_id: str | None, spend_cap_usd: float | None,
) -> None:
    """Set (or CLEAR) the public-MCP-key attribution for provider jobs submitted
    on this async task.

    Call at the START of every MCP tool handler (``loreweave_mcp`` does this in
    ``build_tool_context``): pass the values for a public-key call, or
    ``(None, None)`` to CLEAR for a first-party call. Clearing matters — a
    contextvar can otherwise leak a prior call's key across a pooled task (cf. the
    campaign_id leak lesson). A None key disables the merge entirely.
    """
    _mcp_key_id_ctx.set(mcp_key_id)
    _spend_cap_usd_ctx.set(spend_cap_usd)


def get_public_key_attribution() -> tuple[str | None, float | None]:
    """Read the current task's (mcp_key_id, spend_cap_usd). Both None for
    first-party traffic."""
    return _mcp_key_id_ctx.get(), _spend_cap_usd_ctx.get()


def merge_attribution_into_job_meta(
    job_meta: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Fold the current task's public-key attribution into ``job_meta``.

    Returns ``job_meta`` UNCHANGED (same object) when no public key is in scope —
    so the caller can cheaply detect "no change" by identity. When a key is in
    scope, returns a NEW dict with ``mcp_key_id`` (and ``spend_cap_usd`` when
    set) **overwriting** any caller value (server-set wins — see module docstring).
    """
    key_id, cap = get_public_key_attribution()
    if key_id is None:
        return job_meta
    merged = dict(job_meta or {})
    merged["mcp_key_id"] = key_id
    if cap is not None:
        merged["spend_cap_usd"] = cap
    return merged
