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

# Derived from the single source of truth (TOOL_DEFINITIONS) so a tool added
# to the catalog (lane LF appended the KG ontology tools) keeps this in sync.
# The memory tools are asserted present below as a floor.
EXPECTED_TOOLS = {d["function"]["name"] for d in TOOL_DEFINITIONS}
_MEMORY_TOOLS = {
    "memory_search",
    "memory_recall_entity",
    "memory_timeline",
    "memory_remember",
    "memory_forget",
}
assert _MEMORY_TOOLS.issubset(EXPECTED_TOOLS)

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


async def test_mcp_tools_list_every_tool_declares_meta_tier_and_scope(mcp_base_url):
    """C-TOOL / D-KNOWLEDGE-META-ADOPTION regression gate.

    Every tool MUST declare `_meta.tier` + `_meta.scope`. This is load-bearing: a
    consumer reads `_meta.tier` to gate execution, and an ABSENT tier silently
    defaults to "R" (read/inert) — which once let every knowledge WRITE tool
    (kg_view_delete, memory_forget, kg_schema_edit, kg_sync_apply, …) run in
    read-only *ask* mode and skip the Tier-A approval card. A new untiered tool
    must fail here rather than reintroduce that hole.
    """
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    assert listing.tools, "tools/list returned an empty tool list"
    for tool in listing.tools:
        meta = getattr(tool, "meta", None)
        assert isinstance(meta, dict) and meta, f"tool {tool.name!r} carries no _meta"
        assert meta.get("tier") in ("R", "A", "W", "S"), (
            f"tool {tool.name!r} has an invalid/absent _meta.tier {meta.get('tier')!r} — "
            "an absent tier silently defaults to R (inert) and un-gates a write"
        )
        assert meta.get("scope") in ("book", "project", "user", "none"), (
            f"tool {tool.name!r} has an invalid/absent _meta.scope {meta.get('scope')!r}"
        )


async def test_mcp_tools_list_async_job_tools_declare_meta_async(mcp_base_url):
    """The two job-STARTING tools carry `_meta.async` so the workflow step-runner
    annotates them without a tool-name heuristic (async-honesty, OQ9/F7). Both are
    also Tier-W: they return a confirm_token and the job starts only after a human
    confirms — so "called" never means "done"."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    by_name = {t.name: (getattr(t, "meta", None) or {}) for t in listing.tools}
    for name in ("kg_build_graph", "kg_build_wiki"):
        assert by_name[name].get("async") is True, f"{name} must declare _meta.async"
        assert by_name[name].get("tier") == "W", f"{name} must be Tier-W (confirm_token)"
    # a read tool must NOT be flagged async
    assert "async" not in by_name["memory_search"]


# ── CD2 · the `propose_*` semantics law (Track D WS-D1) ──────────────────────────
# `propose_*` spans two legitimate behaviors and the NAME does not say which:
#   token pattern (tier W) — mints a confirm_token; writes NOTHING
#   draft pattern (tier A) — writes a clearly-marked draft a human must approve
# Rule 1: a propose_* tool is never tier R (an R propose_* is callable in read-only
# `ask` mode and skips the approval card). Rule 4: its DESCRIPTION must declare which
# pattern it is — that prose is the only signal the model gets, and a Tier-W tool that
# omits it is exactly how a model claims success for work that never happened.
# Spec: docs/specs/2026-07-09-mcp-tool-liveness-eval/contracts.md § CD2.
_CD2_CONFIRM_MARKERS = ("confirm card", "confirm_token", "confirm token")
_CD2_DRAFT_MARKERS = (
    "draft", "triage inbox", "pending", "awaiting", "human review", "for review", "proposal",
)


def _contains_any(text: str, needles) -> bool:
    low = (text or "").lower()
    return any(n in low for n in needles)


async def test_cd2_propose_tools_are_never_tier_r_and_declare_their_pattern(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()

    proposers = [t for t in listing.tools if "propose" in t.name]
    assert proposers, "no propose_* tools on the wire — this lint is testing nothing"

    saw_a = False
    for tool in proposers:
        meta = getattr(tool, "meta", None) or {}
        tier = meta.get("tier")
        assert tier in ("A", "W"), (
            f"CD2: propose_* tool {tool.name!r} has tier {tier!r} — must be W (mints a "
            "confirm_token) or A (writes a draft)."
        )
        desc = tool.description or ""
        assert desc.strip(), f"CD2: propose_* tool {tool.name!r} has no description"
        if tier == "W":
            assert _contains_any(desc, _CD2_CONFIRM_MARKERS), (
                f"CD2: Tier-W propose_* tool {tool.name!r} never tells the model a human "
                f"must confirm (no {_CD2_CONFIRM_MARKERS} in its description)."
            )
        else:
            saw_a = True
            assert _contains_any(desc, _CD2_DRAFT_MARKERS), (
                f"CD2: Tier-A propose_* tool {tool.name!r} never says it writes a DRAFT "
                f"awaiting approval (no {_CD2_DRAFT_MARKERS} in its description)."
            )
            assert not _contains_any(desc, ("confirm_token", "confirm token")), (
                f"CD2: Tier-A propose_* tool {tool.name!r} claims a confirm_token it never "
                "mints — the model waits for a round-trip that never comes."
            )
    # knowledge's propose_* tools are all draft-pattern (kg_propose_edge/fact park rows in
    # the triage inbox); if that ever stops being true, this reminds the author to check
    # the W branch is exercised somewhere.
    assert saw_a, "expected at least one Tier-A (draft) propose_* tool in knowledge"


def test_cd2_marker_predicate_discriminates():
    """The lint above is worthless if its predicate matches everything. Prove it doesn't."""
    assert not _contains_any("Propose a merge of two entities. The merge happens.", _CD2_CONFIRM_MARKERS)
    assert not _contains_any("Immediately writes the value into canon.", _CD2_DRAFT_MARKERS)
    assert _contains_any("Returns a confirm card; a human approves.", _CD2_CONFIRM_MARKERS)
    assert _contains_any("parked in the triage inbox — NEVER written to the graph", _CD2_DRAFT_MARKERS)
    # the `draft` STATUS VALUE must never satisfy a Tier-W confirm requirement
    assert not _contains_any("status change (active | inactive | draft | rejected)", _CD2_CONFIRM_MARKERS)


async def test_mcp_tools_list_exposes_no_scope_args(mcp_base_url):
    """Design D3 / INV-K2 (H-I-amended) — user_id / session_id are NEVER tool
    parameters (identity arrives via context headers); the injected FastMCP ctx
    must not leak either. project_id is DELIBERATELY excluded from this set: it is
    now an allowed, ownership-checked scope arg (the public edge mints no
    X-Project-Id, so a public agent supplies it; the owner gate confines it to the
    caller's own projects)."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    forbidden = {"user_id", "session_id", "ctx"}
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

            # (d) array-of-object params must carry the SAME per-item shape on
            # both paths (a bare list[dict] shim would advertise a structureless
            # object array to the LLM while bespoke names the item fields — the
            # exact MCP-vs-bespoke drift FIX #7 guards, but for nested items).
            bespoke_items = bespoke_spec.get("items")
            if isinstance(bespoke_items, dict) and bespoke_items.get("type") == "object":
                mcp_items = _mcp_array_items(mcp_spec, schema)
                assert mcp_items is not None, (
                    f"{name}.{prop_name}: bespoke schema declares object array "
                    f"items but MCP inputSchema exposes no item schema"
                )
                bespoke_item_props = set(bespoke_items.get("properties", {}))
                mcp_item_props = set(mcp_items.get("properties", {}))
                assert mcp_item_props == bespoke_item_props, (
                    f"{name}.{prop_name}.items: property mismatch — MCP "
                    f"{sorted(mcp_item_props)} vs bespoke {sorted(bespoke_item_props)}"
                )
                assert set(mcp_items.get("required", [])) == set(
                    bespoke_items.get("required", [])
                ), f"{name}.{prop_name}.items: required mismatch"


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


def _resolve_ref(node: dict, root: dict) -> dict:
    """Follow a local ``$ref`` (#/$defs/Name) into the root inputSchema.

    Pydantic renders a nested model param (``list[SomeModel]``) as a ``$ref``
    into a top-level ``$defs`` block rather than inlining the item properties,
    so the item schema must be resolved before its fields can be compared."""
    ref = node.get("$ref")
    if not ref or not ref.startswith("#/"):
        return node
    cur: dict = root
    for part in ref[2:].split("/"):
        cur = cur.get(part, {}) if isinstance(cur, dict) else {}
    return cur if isinstance(cur, dict) else node


def _mcp_array_items(spec: dict, root: dict) -> dict | None:
    """Read an array param's resolved ``items`` schema from an MCP inputSchema
    property, descending into an ``anyOf`` Optional union (``list[...] | None``)
    and resolving a local ``$ref`` to its ``$defs`` entry."""
    for branch in (spec, *spec.get("anyOf", [])):
        if branch.get("type") == "array" and isinstance(branch.get("items"), dict):
            return _resolve_ref(branch["items"], root)
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


# ── RAID Wave C5 — MCP resources + prompts ─────────────────────────────
# The resource URIs are TEMPLATES ({project_id}), advertised via
# resources/templates/list. What is covered WITHOUT a live DB mirrors the tool
# tests above: listings (static per process) and the auth/validation failures
# that reject inside _require_owned_project BEFORE any repo access. A live-DB
# summary/entities read belongs to the cross-service smoke gate, not here.

EXPECTED_RESOURCE_TEMPLATES = {
    "knowledge://project/{project_id}/summary",
    "knowledge://project/{project_id}/entities",
}
EXPECTED_PROMPTS = {"recap_story_so_far", "entity_dossier"}

# Valid-shape ids for the auth-failure reads (rejected before any repo touch,
# so they never need to exist).
_PROJ_UUID = "22222222-2222-2222-2222-222222222222"
_SUMMARY_URI = f"knowledge://project/{_PROJ_UUID}/summary"
_ENTITIES_URI = f"knowledge://project/{_PROJ_UUID}/entities"


async def test_mcp_resource_templates_list(mcp_base_url):
    """resources/templates/list must advertise exactly the two project-scoped
    resource templates, each with the right MIME type and a description."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_resource_templates()
    by_uri = {t.uriTemplate: t for t in listing.resourceTemplates}
    assert set(by_uri) == EXPECTED_RESOURCE_TEMPLATES
    assert by_uri["knowledge://project/{project_id}/summary"].mimeType == "text/plain"
    assert by_uri["knowledge://project/{project_id}/entities"].mimeType == "application/json"
    for tpl in listing.resourceTemplates:
        assert tpl.name, f"template {tpl.uriTemplate!r} is missing a name"
        assert tpl.description, f"template {tpl.uriTemplate!r} is missing a description"


async def test_mcp_prompts_list(mcp_base_url):
    """prompts/list must advertise both canned prompts, each with exactly its
    one semantic argument (required) — the injected ctx must never leak into
    the advertised argument list (same D3 guarantee the tool schemas carry)."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_prompts()
    prompts = {p.name: p for p in listing.prompts}
    assert set(prompts) == EXPECTED_PROMPTS
    recap_args = {a.name: a for a in prompts["recap_story_so_far"].arguments}
    assert set(recap_args) == {"project_id"}
    assert recap_args["project_id"].required is True
    dossier_args = {a.name: a for a in prompts["entity_dossier"].arguments}
    assert set(dossier_args) == {"entity_name"}
    assert dossier_args["entity_name"].required is True
    for p in listing.prompts:
        assert p.description, f"prompt {p.name!r} is missing a description"


async def test_mcp_prompt_get_renders_recap(mcp_base_url):
    """prompts/get renders the recap instructions with the project id embedded
    and points the model at the memory tools (grounding, not invention)."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        res = await session.get_prompt("recap_story_so_far", {"project_id": _PROJ_UUID})
    assert res.messages, "prompt rendered no messages"
    text = res.messages[0].content.text
    assert _PROJ_UUID in text
    assert "memory_timeline" in text
    assert "memory_search" in text


async def test_mcp_prompt_get_renders_entity_dossier(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        res = await session.get_prompt("entity_dossier", {"entity_name": "Mira"})
    text = res.messages[0].content.text
    assert "Mira" in text
    assert "memory_recall_entity" in text
    assert "kg_graph_query" in text


async def test_mcp_resource_read_rejects_missing_token(mcp_base_url):
    """A resource read without X-Internal-Token is rejected before any repo
    access — same envelope gate as the tool path (_require_envelope_user)."""
    from mcp.shared.exceptions import McpError

    async with _mcp_client(mcp_base_url, headers={}) as session:
        with pytest.raises(McpError) as exc:
            await session.read_resource(_SUMMARY_URI)
    assert "x-internal-token" in str(exc.value).lower()


async def test_mcp_resource_read_rejects_wrong_token(mcp_base_url):
    from mcp.shared.exceptions import McpError

    headers = {
        "X-Internal-Token": "not-the-real-token",
        "X-User-Id": "11111111-1111-1111-1111-111111111111",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        with pytest.raises(McpError) as exc:
            await session.read_resource(_ENTITIES_URI)
    assert "invalid internal token" in str(exc.value).lower()


async def test_mcp_resource_read_rejects_bad_user_id_uuid(mcp_base_url):
    from mcp.shared.exceptions import McpError

    headers = {
        "X-Internal-Token": _GOOD_TOKEN,
        "X-User-Id": "not-a-uuid",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        with pytest.raises(McpError) as exc:
            await session.read_resource(_SUMMARY_URI)
    assert "x-user-id" in str(exc.value).lower()


async def test_mcp_resource_read_rejects_malformed_project_uuid(mcp_base_url):
    """A well-authenticated read of a malformed {project_id} is rejected by the
    UUID parse in _require_owned_project — BEFORE the ownership lookup, so no
    DB is touched (which is what makes this testable here)."""
    from mcp.shared.exceptions import McpError

    headers = {
        "X-Internal-Token": _GOOD_TOKEN,
        "X-User-Id": "11111111-1111-1111-1111-111111111111",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        with pytest.raises(McpError) as exc:
            await session.read_resource("knowledge://project/not-a-uuid/summary")
    assert "project_id" in str(exc.value).lower()


# P4/Wave-C slice D — knowledge builds its OWN ToolContext, so it must run the
# spend-carrier hook itself (the loreweave_mcp universal hook is bypassed). The
# header parse is the local helper; the contextvar set mirrors the proven kit
# pattern (sdks/python/loreweave_mcp/tests/test_kit.py) + the SDK merge
# (sdks/python/tests/test_attribution.py).
def test_parse_spend_cap():
    from app.mcp.server import _parse_spend_cap

    assert _parse_spend_cap("5.5") == 5.5
    assert _parse_spend_cap("0") == 0.0
    assert _parse_spend_cap(None) is None
    assert _parse_spend_cap("") is None
    assert _parse_spend_cap("not-a-number") is None  # fails open → no per-key cap
    assert _parse_spend_cap("-1") is None  # negative rejected


# ── W0 MCP reliability contract ────────────────────────────────────────
# Mirrors chat-service's FE-tools CLOSED_SET_ARGS rule for MCP: closed-set
# args are real enums; the observed one-element-list filter shape is
# tolerated; pydantic validation failures reach the model as ONE-LINE
# directives (never the raw dump with the errors.pydantic.dev URL).

# tool → args whose valid values are a finite, code-known set.
CLOSED_SET_ARGS = {
    "kg_list_templates": ["scope"],
    "kg_triage_list": ["status"],
    "kg_propose_fact": ["fact_type"],
    "kg_schema_edit": ["verb", "level"],
    "kg_triage_resolve": ["action"],
    "kg_triage_schema_write": ["action"],
    "kg_world_query": ["unify"],   # B1(4) cross-partition unification mode
    "kg_multi_query": ["unify"],
}

# (tool, arg) → the value set the advertised enum must COVER (>=, mirroring
# jobs' JOB_STATUSES pattern) — enum PRESENCE alone lets a silently
# dropped/renamed value ship unnoticed.
CLOSED_SET_VALUES = {
    ("kg_list_templates", "scope"): {"system", "user"},
    ("kg_triage_list", "status"): {"pending", "pending_glossary", "resolved", "dismissed"},
    ("kg_propose_fact", "fact_type"): {"decision", "preference", "milestone", "negation"},
    ("kg_schema_edit", "verb"): {"add", "deprecate"},
    ("kg_schema_edit", "level"): {"edge_type", "fact_type"},
    ("kg_triage_resolve", "action"): {"map", "re_target", "drop_edge", "close_previous", "dismiss"},
    ("kg_triage_schema_write", "action"): {
        "add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active",
    },
    ("kg_world_query", "unify"): {"off", "by_name", "semantic"},
    ("kg_multi_query", "unify"): {"off", "by_name", "semantic"},
}


def _closed_set_enum(spec: dict) -> set:
    """Collect enum values from a property spec, descending anyOf unions and
    array item schemas (the `X | list[X] | None` rendering)."""
    values: set = set()
    for branch in (spec, *spec.get("anyOf", [])):
        if "enum" in branch:
            values |= set(branch["enum"])
        items = branch.get("items")
        if isinstance(items, dict) and "enum" in items:
            values |= set(items["enum"])
    return values


async def test_closed_set_args_are_enums(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    by_name = {t.name: t for t in listing.tools}
    for tool_name, args in CLOSED_SET_ARGS.items():
        props = by_name[tool_name].inputSchema.get("properties", {})
        for arg in args:
            values = _closed_set_enum(props.get(arg, {}))
            assert values, f"{tool_name}.{arg}: closed-set arg MUST declare an enum"
            want = CLOSED_SET_VALUES[(tool_name, arg)]
            assert values >= want, (
                f"{tool_name}.{arg}: enum {sorted(values)} must cover {sorted(want)}"
            )


async def test_kg_list_templates_scope_accepts_one_element_list(monkeypatch):
    """W0 #3 — the observed `scope: [\"system\"]` shape must dispatch exactly
    like `scope: \"system\"` (unwrap, not error)."""
    import app.mcp.server as srv

    calls = []

    async def _fake_dispatch(ctx, tool_name, tool_args):
        calls.append((tool_name, tool_args))
        return {"templates": []}

    monkeypatch.setattr(srv, "_dispatch", _fake_dispatch)
    fn = srv.mcp_server._tool_manager._tools["kg_list_templates"].fn
    await fn(None, scope=["system"])
    await fn(None, scope="system")
    assert calls[0] == calls[1] == ("kg_list_templates", {"scope": "system"})


async def test_kg_list_templates_scope_multi_list_errors_with_directive(monkeypatch):
    import app.mcp.server as srv

    async def _fake_dispatch(ctx, tool_name, tool_args):  # pragma: no cover
        raise AssertionError("must not dispatch")

    monkeypatch.setattr(srv, "_dispatch", _fake_dispatch)
    fn = srv.mcp_server._tool_manager._tools["kg_list_templates"].fn
    with pytest.raises(ValueError) as exc:
        await fn(None, scope=["system", "user"])
    msg = str(exc.value)
    assert "scope" in msg and "single value" in msg


async def test_validation_error_reaches_model_as_one_line_directive(mcp_base_url):
    """W0 #4b — a bad enum value surfaces as the rewritten one-line directive:
    names the arg, states what pydantic expected, never the pydantic-docs URL
    or the multi-line dump. Validation fails BEFORE auth/repo access."""
    headers = {
        "X-Internal-Token": _GOOD_TOKEN,
        "X-User-Id": "11111111-1111-1111-1111-111111111111",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("kg_list_templates", {"scope": "bogus"})
    assert result.isError is True
    text = result.content[0].text
    assert "errors.pydantic.dev" not in text
    assert "\n" not in text.strip(), f"directive must be one line, got: {text!r}"
    assert "invalid arguments for kg_list_templates" in text
    assert "scope" in text


async def test_project_in_scope_error_is_a_directive():
    """W0 #4a — the grant gate's no-project error must tell the model HOW to
    fix it: name the `project_id` arg + the kg_project_list discovery tool."""
    from uuid import uuid4

    from app.tools.executor import ToolExecutionError
    from app.tools.graph_schema_tools import _resolve_project_owner

    class _Ctx:
        project_id = None
        user_id = uuid4()
        mcp_key_id = None

    from loreweave_grants import GrantLevel

    with pytest.raises(ToolExecutionError) as exc:
        await _resolve_project_owner(_Ctx(), GrantLevel.VIEW)
    msg = str(exc.value)
    assert "project_id" in msg
    assert "kg_project_list" in msg


async def test_kg_project_list_is_advertised_with_no_scope_leak(mcp_base_url):
    """The discovery tool the #4a directive points at must exist on the MCP
    surface, owner-scoped via the envelope (no user_id/project_id args)."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    by_name = {t.name: t for t in listing.tools}
    assert "kg_project_list" in by_name
    props = set(by_name["kg_project_list"].inputSchema.get("properties", {}))
    assert props == {"include_archived", "limit"}
