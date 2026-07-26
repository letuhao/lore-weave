"""CD1 wire gate — `_meta` tier/scope validity + `_meta.async` honesty for the
lore-enrichment MCP catalog.

Asserts over the served `tools/list` output — NOT the `require_meta(...)` source —
because FastMCP can strip fields between the decorator and what a client sees (the
known repo bug class). We read the catalog via `mcp_server.list_tools()`, the EXACT
method the streamable-HTTP `tools/list` handler calls server-side (it builds the
same `MCPTool` objects with `_meta=info.meta` from the post-registration store), so
any stripping is captured identically to the wire — without standing up a second
loopback server (FastMCP's session manager is once-per-instance, and the sibling
tests/test_mcp_server.py already runs one from the same `mcp_server` singleton).

This service exposes a SINGLE tool, `lore_enrichment_auto_enrich`. Its handler
detects gaps and ENQUEUES a background job immediately (no confirm_token — safety is
quarantine of every proposal + a `max_spend_tokens` cap), returning the job id right
away, so it is correctly Tier A + `_meta.async == true`. Because the catalog has
only the one (async) tool, there is NO synchronous tool here to name as a negative
control — that assertion lives in composition-service (composition_get_work). We
still assert the generic invariant (no tool outside the async set carries the flag),
which holds vacuously here and stays correct if a sync tool is added later.
"""

from __future__ import annotations

ASYNC_JOB_TOOLS = {"lore_enrichment_auto_enrich"}

_VALID_TIERS = {"R", "A", "W", "S"}
_VALID_SCOPES = {"book", "project", "user", "none"}


async def _list_by_name():
    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    assert tools, "tools/list returned an empty catalog"
    return {t.name: (t.meta or {}) for t in tools}


async def test_every_tool_declares_valid_tier_and_scope():
    """CD1 (1): every advertised tool carries a valid `_meta.tier` + `_meta.scope`."""
    by_name = await _list_by_name()
    for name, meta in by_name.items():
        assert isinstance(meta, dict) and meta, f"tool {name!r} carries no _meta"
        assert meta.get("tier") in _VALID_TIERS, (
            f"tool {name!r} has invalid/absent _meta.tier {meta.get('tier')!r}"
        )
        assert meta.get("scope") in _VALID_SCOPES, (
            f"tool {name!r} has invalid/absent _meta.scope {meta.get('scope')!r}"
        )


async def test_auto_enrich_declares_meta_async():
    """CD1 (2): the auto-enrich tool ENQUEUES a background job and returns the job id
    immediately, so it must declare `_meta.async == true` — and it stays Tier A
    (quarantine + spend-cap safety, no confirm_token gate)."""
    by_name = await _list_by_name()
    meta = by_name["lore_enrichment_auto_enrich"]
    assert meta.get("async") is True, "lore_enrichment_auto_enrich must declare _meta.async"
    assert meta.get("tier") == "A", "auto-enrich is Tier A (no confirm_token — quarantine + spend cap)"


async def test_no_non_async_tool_declares_async():
    """CD1 (3): generic negative control — no tool OUTSIDE the async set may carry
    `_meta.async`. Vacuously true today (the catalog is the single async tool); it
    stays correct if a synchronous tool is added later."""
    by_name = await _list_by_name()
    for name, meta in by_name.items():
        if name not in ASYNC_JOB_TOOLS:
            assert "async" not in meta, (
                f"tool {name!r} is not a known job-starter but declares _meta.async"
            )
