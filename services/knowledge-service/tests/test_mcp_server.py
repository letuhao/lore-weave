"""ARCH-1 C1 — tests for the knowledge-service MCP server facade.

These exercise the *real* MCP streamable-HTTP protocol over a loopback
uvicorn server: the client speaks JSON-RPC over HTTP to the ``/mcp``
ASGI app served on an ephemeral 127.0.0.1 port. This is the same
transport the chat-service MCP client (C2) uses, so the tests cover the
actual wire path — header extraction, JSON-RPC framing, tool-result
encoding — not a mock of it.

A loopback server (rather than httpx ``ASGITransport``) is used because
the streamable-HTTP client opens a streaming channel that ASGITransport
does not faithfully emulate; a real server exercises the protocol end to
end.

Event-loop design: ``StreamableHTTPSessionManager.run()`` is
once-per-instance, and the project's pytest config is
``asyncio_mode = auto`` with the default *function*-scoped loop. To keep
the long-lived server off the per-test loop entirely, the server runs in
a dedicated background thread with its own event loop (started once per
module). Each test then talks to it over real TCP on its own loop. This
sidesteps the cross-loop fragility of a module-scoped async fixture
under function-scoped tests.

What is covered here WITHOUT a live DB:
  * ``tools/list`` — static per process; never touches a repo.
  * scope-leak guard — no tool input schema exposes user/project/session.
  * auth failures (missing / wrong token, malformed user-id) — these are
    rejected inside ``_build_tool_context`` BEFORE any repo access, so
    the structured tool-error encoding is exercised without Postgres or
    Neo4j.

A live-DB ``memory_recall_entity`` call (plan Test 2) belongs to the
cross-service smoke gate, not this unit file, so it is omitted here.
"""

from __future__ import annotations

import socket
import threading
import time
from contextlib import asynccontextmanager

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.mcp.server import build_mcp_app
from app.tools.definitions import TOOL_DEFINITIONS

EXPECTED_TOOLS = {
    "memory_search",
    "memory_recall_entity",
    "memory_timeline",
    "memory_remember",
    "memory_forget",
}

# Matches conftest.py's INTERNAL_SERVICE_TOKEN default so the auth check
# in _build_tool_context passes when we want it to.
_GOOD_TOKEN = "default_test_token"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def mcp_base_url():
    """Serve the /mcp ASGI app on a loopback uvicorn server in a daemon
    thread (its own event loop) for the whole module. uvicorn runs the
    app's lifespan, which starts the StreamableHTTP session manager
    (once-per-instance). Running off the test loop avoids cross-loop
    fragility under ``asyncio_mode = auto`` (function-scoped loops)."""
    app = build_mcp_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for the server (and the app lifespan / session manager) to be
    # ready before any test connects.
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("MCP loopback server did not start in time")
        time.sleep(0.02)

    try:
        # The standalone MCP app serves its endpoint at "/" because
        # streamable_http_path="/" (so that FastAPI's app.mount("/mcp", ..)
        # in production resolves to /mcp). Unmounted here, the endpoint is
        # at the root — the client must target "/" directly.
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@asynccontextmanager
async def _mcp_client(base_url: str, headers: dict[str, str]):
    """Open an initialized MCP ClientSession with the given context
    headers against the loopback server."""
    async with streamablehttp_client(base_url, headers=headers) as (
        read,
        write,
        _get_session_id,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def test_mcp_tools_list_returns_all_expected_names(mcp_base_url):
    """tools/list must return exactly the five memory tool names."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    names = {t.name for t in listing.tools}
    assert names == EXPECTED_TOOLS


async def test_mcp_tools_list_each_tool_has_name_and_description(mcp_base_url):
    """Every listed tool carries a non-empty name and description — the
    LLM relies on the description to decide when to call each tool."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    assert listing.tools, "tools/list returned an empty tool list"
    for tool in listing.tools:
        assert tool.name, "a tool is missing its name"
        assert tool.description, f"tool {tool.name!r} is missing a description"


async def test_mcp_tools_list_exposes_no_scope_args(mcp_base_url):
    """Design D3 — user_id / project_id / session_id are NEVER tool
    parameters; they arrive via context headers. Assert no tool's input
    schema leaks a scope id (which would let the LLM override scope) or
    the injected FastMCP context object."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    forbidden = {"user_id", "project_id", "session_id", "ctx"}
    for tool in listing.tools:
        props = set(tool.inputSchema.get("properties", {}))
        leaked = props & forbidden
        assert not leaked, f"tool {tool.name!r} leaks scope args: {leaked}"


async def test_mcp_inputschema_mirrors_bespoke_openai_schema(mcp_base_url):
    """FIX #7 (schema fidelity) — the MCP inputSchema the LLM sees on the
    MCP path must carry the SAME constraints as the bespoke OpenAI
    function-calling schema (app/tools/definitions.py TOOL_DEFINITIONS) on
    the /internal/tools/execute path. Otherwise the LLM gets two different
    contracts for one tool, and the MCP path could silently accept inputs
    the bespoke path rejects (or vice versa).

    For each tool we assert, between the bespoke `parameters` block and the
    MCP `inputSchema`:
      (a) the required set matches exactly;
      (b) every bespoke `enum` value is a subset of the MCP enum for that
          param (the MCP Literal annotation must cover at least the bespoke
          choices — tightened in the server annotations);
      (c) integer params' minimum/maximum match.

    This should PASS now the server annotations carry Field(ge=…, le=…) and
    Literal enums. If it fails, the server annotation missed a constraint —
    the failure message names the tool + param so the code owner can fix it.
    """
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    mcp_by_name = {t.name: t for t in listing.tools}

    for bespoke in TOOL_DEFINITIONS:
        fn = bespoke["function"]
        name = fn["name"]
        assert name in mcp_by_name, f"MCP is missing tool {name!r}"
        params = fn["parameters"]
        bespoke_props = params["properties"]
        bespoke_required = set(params.get("required", []))

        schema = mcp_by_name[name].inputSchema
        mcp_props = schema.get("properties", {})
        mcp_required = set(schema.get("required", []))

        # (a) required set matches exactly.
        assert mcp_required == bespoke_required, (
            f"{name}: required mismatch — MCP {sorted(mcp_required)} "
            f"vs bespoke {sorted(bespoke_required)}"
        )

        for prop_name, bespoke_spec in bespoke_props.items():
            assert prop_name in mcp_props, (
                f"{name}.{prop_name}: present in bespoke schema but missing "
                f"from MCP inputSchema"
            )
            mcp_spec = mcp_props[prop_name]

            # (b) every bespoke enum value is covered by the MCP enum.
            if "enum" in bespoke_spec:
                mcp_enum = _mcp_enum_values(mcp_spec)
                assert mcp_enum is not None, (
                    f"{name}.{prop_name}: bespoke schema declares an enum "
                    f"{bespoke_spec['enum']} but MCP inputSchema exposes no "
                    f"enum constraint"
                )
                missing = set(bespoke_spec["enum"]) - mcp_enum
                assert not missing, (
                    f"{name}.{prop_name}: MCP enum {sorted(mcp_enum)} is "
                    f"missing bespoke value(s) {sorted(missing)}"
                )

            # (c) integer minimum/maximum match.
            if bespoke_spec.get("type") == "integer":
                for bound in ("minimum", "maximum"):
                    if bound in bespoke_spec:
                        mcp_bound = _mcp_numeric_bound(mcp_spec, bound)
                        assert mcp_bound == bespoke_spec[bound], (
                            f"{name}.{prop_name}: {bound} mismatch — MCP "
                            f"{mcp_bound!r} vs bespoke {bespoke_spec[bound]!r}"
                        )


def _mcp_enum_values(spec: dict) -> set | None:
    """Collect enum choices from an MCP inputSchema property.

    The MCP path annotates optional Literal params as
    ``Literal[...] | None``, which Pydantic renders as ``anyOf`` of a
    ``{"enum": [...]}`` branch + a ``{"type": "null"}`` branch rather than a
    flat top-level ``enum``. Pull the enum from whichever shape is present."""
    if "enum" in spec:
        return set(spec["enum"])
    values: set = set()
    found = False
    for branch in spec.get("anyOf", []):
        if "enum" in branch:
            values |= set(branch["enum"])
            found = True
    return values if found else None


def _mcp_numeric_bound(spec: dict, bound: str):
    """Read minimum/maximum from an MCP inputSchema property, descending
    into an ``anyOf`` branch if the param is rendered as a union."""
    if bound in spec:
        return spec[bound]
    for branch in spec.get("anyOf", []):
        if bound in branch:
            return branch[bound]
    return None


def _error_text(result) -> str:
    """First text content of a tool result, lowercased.

    Auth/header failures in ``_build_tool_context`` raise ValueError,
    which FastMCP surfaces as a protocol-level tool error: ``isError`` is
    True and the first content item is plain text ("Error executing tool
    <name>: <msg>"), NOT a JSON dict. Asserting on ``isError`` + this
    text is the correct contract for those failures — they are rejected
    BEFORE any repo touch, so no scoped data is ever reached."""
    assert result.content, "expected tool error content, got none"
    return result.content[0].text.lower()


async def test_mcp_server_rejects_missing_internal_token(mcp_base_url):
    """A tool call without X-Internal-Token is rejected as a tool error
    (isError=True), NOT a 5xx and NOT a successful result — the auth
    check raises before any repo access."""
    async with _mcp_client(mcp_base_url, headers={}) as session:
        result = await session.call_tool("memory_search", {"query": "anything"})
    assert result.isError is True
    assert "x-internal-token" in _error_text(result)


async def test_mcp_server_rejects_wrong_internal_token(mcp_base_url):
    """A wrong X-Internal-Token is rejected as a tool error — defence
    against a leaked-but-stale or spoofed token. The message says the
    token is invalid (not which header is missing)."""
    headers = {
        "X-Internal-Token": "not-the-real-token",
        "X-User-Id": "11111111-1111-1111-1111-111111111111",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("memory_search", {"query": "anything"})
    assert result.isError is True
    assert "invalid internal token" in _error_text(result)


async def test_mcp_server_rejects_bad_user_id_uuid(mcp_base_url):
    """A valid token but a non-UUID X-User-Id is rejected, naming the
    offending header — scope ids never come from the LLM, so a malformed
    one is the caller's bug, surfaced clearly and before any repo touch."""
    headers = {
        "X-Internal-Token": _GOOD_TOKEN,
        "X-User-Id": "not-a-uuid",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("memory_search", {"query": "anything"})
    assert result.isError is True
    assert "x-user-id" in _error_text(result)
