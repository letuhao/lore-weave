"""CD1 wire gate — `_meta.async` honesty for the composition MCP catalog.

Asserts over the served `tools/list` output — NOT the `require_meta(...)` source —
because FastMCP can strip fields between the decorator declaration and what a client
sees (the known repo bug class: a schema declared in several places, one of which
FastMCP drops). We read the catalog via `mcp_server.list_tools()`, which is the
EXACT method the streamable-HTTP `tools/list` handler calls server-side: it builds
the same `MCPTool` objects with `_meta=info.meta` from the tool manager's
post-registration store, so any stripping is captured here identically to the wire.

Using the in-process method (rather than a second loopback uvicorn server, as the
sibling tests/unit/test_mcp_server.py does) is deliberate: FastMCP's
`StreamableHTTPSessionManager.run()` is once-per-instance, and the server app is
built from the module-level `mcp_server` singleton — so a SECOND wire-server module
in the same worker process fails to start ("can only be called once per instance").
This module avoids that entirely while asserting the same served meta.

`_meta.async == true` tells the chat-service workflow step-runner that a tool STARTS
a background job — the result is NOT in the tool's return value, so the step must be
annotated `async_job` and the model must not treat "called" as "done". This gate
locks in the eight tools the old tool-name heuristic silently missed:

  - 5 Tier-W confirm-then-job tools (mint a confirm_token; the confirmed action
    enqueues the job): composition_motif_mine, composition_arc_import_analyze,
    composition_conformance_run, composition_authoring_run_start,
    composition_authoring_run_resume.
  - 3 Tier-A PlanForge tools that enqueue at tool-time in their async mode
    (mode='llm' / worker-on refine / run_pipeline=true) and return a job id:
    plan_propose_spec, plan_apply_revision, plan_compile.
"""

from __future__ import annotations

# conftest.py (tests/conftest.py) sets the required env BEFORE app import.

# The eight tools that START a background job — every one must declare _meta.async.
ASYNC_JOB_TOOLS = {
    # Tier-W confirm-then-job (confirm_token → confirmed action enqueues)
    "composition_motif_mine",
    "composition_arc_import_analyze",
    "composition_conformance_run",
    "composition_authoring_run_start",
    "composition_authoring_run_resume",
    # Tier-A enqueue-at-tool-time (returns a job id in its async mode)
    "plan_propose_spec",
    "plan_apply_revision",
    "plan_compile",
}

# Negative control — a known-SYNCHRONOUS read tool whose result IS its return value.
# It must NOT carry _meta.async, or the runner would poll a job that never started.
SYNC_CONTROL_TOOL = "composition_get_work"

# Other synchronous Tier-R reads that likewise must never carry the flag.
OTHER_SYNC_READS = (
    "composition_list_outline",
    "composition_get_prose",
    "composition_list_canon_rules",
    "composition_get_generation_job",
)

_VALID_TIERS = {"R", "A", "W", "S"}
_VALID_SCOPES = {"book", "project", "user", "none"}


async def _list_by_name():
    from app.mcp.server import mcp_server

    tools = await mcp_server.list_tools()
    assert tools, "tools/list returned an empty catalog"
    return {t.name: (t.meta or {}) for t in tools}


async def test_every_tool_declares_valid_tier_and_scope():
    """CD1 (1): every advertised tool carries a valid `_meta.tier` + `_meta.scope`.

    An absent/invalid tier silently defaults to R (inert) on the consumer and
    un-gates a write; an invalid scope picks the wrong ownership guard."""
    by_name = await _list_by_name()
    for name, meta in by_name.items():
        assert isinstance(meta, dict) and meta, f"tool {name!r} carries no _meta"
        assert meta.get("tier") in _VALID_TIERS, (
            f"tool {name!r} has invalid/absent _meta.tier {meta.get('tier')!r}"
        )
        assert meta.get("scope") in _VALID_SCOPES, (
            f"tool {name!r} has invalid/absent _meta.scope {meta.get('scope')!r}"
        )


async def test_async_job_tools_declare_meta_async():
    """CD1 (2): the eight job-STARTING tools declare `_meta.async == true` on the
    served catalog — the durable async-honesty signal the workflow step-runner reads
    instead of guessing from the tool name (the heuristic silently missed these)."""
    by_name = await _list_by_name()
    for name in ASYNC_JOB_TOOLS:
        assert name in by_name, f"expected async tool {name!r} missing from the catalog"
        assert by_name[name].get("async") is True, (
            f"tool {name!r} STARTS a background job but does not declare _meta.async — "
            "the runner would treat its return as the finished result (hallucinated done)"
        )


async def test_sync_control_tool_does_not_declare_async():
    """CD1 (3): negative control — a known-synchronous read (composition_get_work)
    must NOT carry `_meta.async`. A false async flag makes the runner poll for a job
    that never started, which is as harmful as a missing one."""
    by_name = await _list_by_name()
    assert SYNC_CONTROL_TOOL in by_name
    assert "async" not in by_name[SYNC_CONTROL_TOOL], (
        f"{SYNC_CONTROL_TOOL} is synchronous — its result IS its return value; "
        "it must not be flagged async"
    )
    # The other Tier-R read tools are likewise synchronous — none may carry the flag.
    # (composition_generate is a legitimate pre-existing async job-starter, so a blanket
    # "only these 8 are async" assertion would be wrong; assert the read tools instead.)
    for name in OTHER_SYNC_READS:
        assert "async" not in by_name[name], (
            f"read tool {name!r} must not declare _meta.async"
        )
