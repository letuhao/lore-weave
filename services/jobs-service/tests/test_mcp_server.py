"""S-JOBS — tests for the jobs-service MCP server facade (MCP fan-out 2026-06-20).

Two layers:

  1. **Wire path** (loopback uvicorn server, real MCP streamable-HTTP, mirrors the
     knowledge-service test pattern): `tools/list` returns the three `jobs_*` reads;
     each carries `_meta` (tier R + scope user); no tool leaks a scope arg; auth
     failures (missing / wrong internal token, malformed user-id) are rejected as
     tool errors BEFORE any store access.

  2. **Handler shape + scope** (direct calls against a seeded fake store): each tool
     returns the documented shape over a seeded store; identity is taken from the
     envelope; a user can only ever read their OWN jobs (the store filters on
     `owner_user_id`), so a foreign caller sees an empty list / a not-accessible
     `job_get`.

The wire-path server runs in a daemon thread with its own event loop (the
StreamableHTTP session manager is once-per-instance and pytest runs
function-scoped loops under `asyncio_mode = auto`).
"""

from __future__ import annotations

import socket
import threading
import time
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# conftest.py sets the required env BEFORE app import.
from .conftest import TEST_USER  # noqa: E402

EXPECTED_TOOLS = {"jobs_list", "jobs_summary", "job_get"}

# Matches conftest.py's INTERNAL_SERVICE_TOKEN default so the auth check passes
# when we want it to.
_GOOD_TOKEN = "test_internal_token"

OTHER_USER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def mcp_base_url():
    """Serve the /mcp ASGI app on a loopback uvicorn server in a daemon thread
    (its own event loop) for the whole module — the same transport the chat-service
    MCP client uses, so these tests cover the actual wire path."""
    from app.mcp.server import build_mcp_app

    app = build_mcp_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("MCP loopback server did not start in time")
        time.sleep(0.02)

    try:
        # streamable_http_path="/" → unmounted, the endpoint is at the root.
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@asynccontextmanager
async def _mcp_client(base_url: str, headers: dict[str, str]):
    async with streamablehttp_client(base_url, headers=headers) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _error_text(result) -> str:
    assert result.content, "expected tool error content, got none"
    return result.content[0].text.lower()


# ── Wire path: catalog + _meta ────────────────────────────────────────────────


async def test_tools_list_returns_the_three_jobs_reads(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    assert {t.name for t in listing.tools} == EXPECTED_TOOLS


async def test_every_tool_has_name_and_description(mcp_base_url):
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    assert listing.tools
    for tool in listing.tools:
        assert tool.name
        assert tool.description, f"tool {tool.name!r} missing a description"


async def test_every_tool_carries_valid_meta(mcp_base_url):
    """C-TOOL: each tool's `_meta` must declare tier=R + a valid scope, and the
    `jobs_*` reads are user-scoped. find_tools recall (H6) relies on synonyms."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    for tool in listing.tools:
        meta = tool.meta
        assert meta is not None, f"tool {tool.name!r} has no _meta"
        assert meta.get("tier") == "R", f"{tool.name}: expected tier R, got {meta.get('tier')!r}"
        assert meta.get("scope") == "user", f"{tool.name}: expected scope user"
        # synonyms feed find_tools recall — every jobs read declares them.
        syns = meta.get("synonyms")
        assert isinstance(syns, list) and syns, f"{tool.name}: missing synonyms"


async def test_no_tool_leaks_a_scope_arg(mcp_base_url):
    """Identity ids are NEVER tool params — they arrive via the envelope headers."""
    headers = {"X-Internal-Token": _GOOD_TOKEN}
    async with _mcp_client(mcp_base_url, headers) as session:
        listing = await session.list_tools()
    forbidden = {"user_id", "owner_user_id", "project_id", "session_id", "ctx"}
    for tool in listing.tools:
        props = set(tool.inputSchema.get("properties", {}))
        leaked = props & forbidden
        assert not leaked, f"tool {tool.name!r} leaks scope args: {leaked}"


# ── Wire path: identity / auth from headers ───────────────────────────────────


async def test_rejects_missing_internal_token(mcp_base_url):
    async with _mcp_client(mcp_base_url, headers={}) as session:
        result = await session.call_tool("jobs_summary", {})
    assert result.isError is True
    assert "x-internal-token" in _error_text(result)


async def test_rejects_wrong_internal_token(mcp_base_url):
    headers = {
        "X-Internal-Token": "not-the-real-token",
        "X-User-Id": TEST_USER,
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("jobs_summary", {})
    assert result.isError is True
    assert "invalid internal token" in _error_text(result)


async def test_rejects_bad_user_id_uuid(mcp_base_url):
    headers = {
        "X-Internal-Token": _GOOD_TOKEN,
        "X-User-Id": "not-a-uuid",
        "X-Session-Id": "sess-1",
    }
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool("jobs_summary", {})
    assert result.isError is True
    assert "x-user-id" in _error_text(result)


# ── Handler shape + scope (direct calls against a seeded fake store) ───────────


class _FakeStore:
    """An owner-filtering stand-in for the projection store. Holds a list of job
    dicts (each with an `owner_user_id`) and serves only the rows owned by the
    queried `owner_user_id` — exactly the security property the real SQL WHERE
    clause provides, so a scope test does not need a live Postgres."""

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 200

    def __init__(self, jobs: list[dict]):
        self._jobs = jobs

    async def list_jobs(self, conn, owner_user_id, **kw):
        mine = [j for j in self._jobs if j["owner_user_id"] == owner_user_id]
        return mine, None

    async def count_summary(self, conn, owner_user_id):
        mine = [j for j in self._jobs if j["owner_user_id"] == owner_user_id]
        active = sum(1 for j in mine if j["status"] in ("pending", "running", "paused"))
        return {
            "active": active,
            "completed": sum(1 for j in mine if j["status"] == "completed"),
            "failed": sum(1 for j in mine if j["status"] == "failed"),
            "cancelled": sum(1 for j in mine if j["status"] == "cancelled"),
        }

    async def get_job(self, conn, owner_user_id, service, job_id):
        for j in self._jobs:
            if (
                j["owner_user_id"] == owner_user_id
                and j["service"] == service
                and j["job_id"] == job_id
            ):
                return dict(j)
        return None


def _seed() -> _FakeStore:
    return _FakeStore(
        [
            {
                "owner_user_id": TEST_USER,
                "service": "translation",
                "job_id": "11111111-1111-1111-1111-111111111111",
                "kind": "translation:book",
                "status": "running",
                "params": None,
            },
            {
                "owner_user_id": TEST_USER,
                "service": "knowledge",
                "job_id": "22222222-2222-2222-2222-222222222222",
                "kind": "knowledge:extraction",
                "status": "completed",
                "params": None,
            },
            {
                "owner_user_id": OTHER_USER,
                "service": "translation",
                "job_id": "99999999-9999-9999-9999-999999999999",
                "kind": "translation:book",
                "status": "running",
                "params": None,
            },
        ]
    )


@asynccontextmanager
async def _patched(store_obj):
    """Patch the server's store + pool getter so the handlers run against the fake
    store with no DB. `build_tool_context` is patched to return the envelope ctx
    directly (the wire-path tests above already cover its real header parsing)."""
    from loreweave_mcp import ToolContext

    import app.mcp.server as srv

    def _ctx(user_id):
        return ToolContext(user_id=user_id, session_id="sess-1")

    with (
        patch.object(srv, "store", store_obj),
        patch.object(srv, "get_pool", return_value=object()),
        patch.object(srv, "build_tool_context", side_effect=lambda ctx, tok: ctx),
    ):
        yield srv, _ctx


async def test_jobs_list_shape_and_owner_scope():
    from uuid import UUID

    async with _patched(_seed()) as (srv, _ctx):
        res = await srv.jobs_list(_ctx(UUID(TEST_USER)))
    assert set(res) == {"items", "next_cursor"}
    # Only the TEST_USER's two jobs — never OTHER_USER's.
    ids = {j["job_id"] for j in res["items"]}
    assert ids == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    }
    # control_caps derived per-row (the running translation job can be cancelled).
    running = next(j for j in res["items"] if j["status"] == "running")
    assert "cancel" in running["control_caps"]


async def test_jobs_list_foreign_user_sees_nothing():
    from uuid import UUID

    async with _patched(_seed()) as (srv, _ctx):
        # A user with no jobs of their own gets an empty list (no leak).
        empty_user = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
        res = await srv.jobs_list(_ctx(empty_user))
    assert res["items"] == []


async def test_jobs_summary_shape_and_owner_scope():
    from uuid import UUID

    async with _patched(_seed()) as (srv, _ctx):
        res = await srv.jobs_summary(_ctx(UUID(TEST_USER)))
    assert res == {"active": 1, "completed": 1, "failed": 0, "cancelled": 0}


async def test_job_get_shape_for_owned_job():
    from uuid import UUID

    async with _patched(_seed()) as (srv, _ctx):
        res = await srv.job_get(
            _ctx(UUID(TEST_USER)),
            service="translation",
            job_id="11111111-1111-1111-1111-111111111111",
        )
    assert res["job_id"] == "11111111-1111-1111-1111-111111111111"
    assert res["status"] == "running"
    assert "control_caps" in res


async def test_job_get_foreign_job_is_not_accessible():
    """A user cannot read another user's job — the store returns None (anti-oracle),
    surfaced as the uniform not-accessible tool error, NOT the foreign job."""
    from uuid import UUID

    async with _patched(_seed()) as (srv, _ctx):
        res = await srv.job_get(
            _ctx(UUID(TEST_USER)),
            service="translation",
            job_id="99999999-9999-9999-9999-999999999999",  # OTHER_USER's job
        )
    assert res == {"success": False, "error": "not found or not accessible"}
