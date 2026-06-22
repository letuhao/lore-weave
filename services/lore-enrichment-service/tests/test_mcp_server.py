"""Tests for the lore-enrichment MCP server facade.

Two layers (mirrors the proven composition/jobs S-* facades):

  1. **Wire path** (loopback uvicorn, real MCP streamable-HTTP): `tools/list`
     returns the single auto-enrich tool with valid `_meta`; no scope/identity arg
     leaks; auth failures (missing/wrong internal token, bad user-id) are rejected
     as tool errors BEFORE any handler runs.

  2. **Handler shape** (direct call, stubbed `auto_enrich` + pool): identity comes
     from the envelope; the tool builds the REST body + delegates; an HTTPException
     from the REST handler degrades to a structured tool refusal.
"""

from __future__ import annotations

import socket
import threading
import time
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
import uvicorn
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# conftest.py sets the required env BEFORE app import.

_GOOD_TOKEN = "test_internal_token"  # tests/conftest.py INTERNAL_SERVICE_TOKEN
TEST_USER = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOOK = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PROJECT = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
EMB = uuid.UUID("11111111-1111-1111-1111-111111111111")
GEN = uuid.UUID("22222222-2222-2222-2222-222222222222")

EXPECTED_TOOLS = {"lore_enrichment_auto_enrich"}


# ── wire-path fixture ─────────────────────────────────────────────────────────


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def mcp_base_url():
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


# ── Wire path: catalog + _meta + auth ─────────────────────────────────────────


async def test_tools_list_returns_the_catalog(mcp_base_url):
    async with _mcp_client(mcp_base_url, {"X-Internal-Token": _GOOD_TOKEN}) as session:
        listing = await session.list_tools()
    assert {t.name for t in listing.tools} == EXPECTED_TOOLS


async def test_tool_carries_valid_meta(mcp_base_url):
    async with _mcp_client(mcp_base_url, {"X-Internal-Token": _GOOD_TOKEN}) as session:
        listing = await session.list_tools()
    tool = next(t for t in listing.tools if t.name == "lore_enrichment_auto_enrich")
    assert tool.description
    meta = tool.meta
    assert meta is not None
    assert meta.get("tier") == "A"
    assert meta.get("scope") == "book"
    assert isinstance(meta.get("synonyms"), list) and meta["synonyms"]


async def test_no_tool_leaks_a_scope_arg(mcp_base_url):
    async with _mcp_client(mcp_base_url, {"X-Internal-Token": _GOOD_TOKEN}) as session:
        listing = await session.list_tools()
    forbidden = {"user_id", "owner_user_id", "session_id", "ctx", "internal_token"}
    for tool in listing.tools:
        schema = tool.inputSchema
        names: set[str] = set(schema.get("properties", {}))
        for definition in (schema.get("$defs") or {}).values():
            names |= set(definition.get("properties", {}))
        assert not (names & forbidden), f"{tool.name!r} leaks scope args"


async def test_rejects_missing_internal_token(mcp_base_url):
    async with _mcp_client(mcp_base_url, headers={}) as session:
        result = await session.call_tool(
            "lore_enrichment_auto_enrich",
            {"project_id": str(PROJECT),
             "args": {"book_id": str(BOOK), "embedding_model_ref": str(EMB),
                      "generation_model_ref": str(GEN)}},
        )
    assert result.isError is True
    assert "x-internal-token" in _error_text(result)


async def test_rejects_wrong_internal_token(mcp_base_url):
    headers = {"X-Internal-Token": "nope", "X-User-Id": str(TEST_USER), "X-Session-Id": "s1"}
    async with _mcp_client(mcp_base_url, headers) as session:
        result = await session.call_tool(
            "lore_enrichment_auto_enrich",
            {"project_id": str(PROJECT),
             "args": {"book_id": str(BOOK), "embedding_model_ref": str(EMB),
                      "generation_model_ref": str(GEN)}},
        )
    assert result.isError is True
    assert "invalid internal token" in _error_text(result)


# ── Handler shape (direct call, stubbed REST handler + pool) ───────────────────


class _Ctx:
    def __init__(self, user_id=TEST_USER):
        self.user_id = user_id
        self.session_id = "s1"
        self.project_id = None
        self.trace_id = None
        self.internal_token = _GOOD_TOKEN


@asynccontextmanager
async def _patched(auto_enrich_impl):
    import app.mcp.server as srv
    with (
        patch.object(srv, "_ctx", side_effect=lambda ctx: ctx),
        patch.object(srv, "get_pool", return_value=object()),
        patch.object(srv, "auto_enrich", new=auto_enrich_impl),
    ):
        yield srv


async def test_auto_enrich_delegates_with_envelope_identity():
    import app.mcp.server as srv

    captured = {}

    async def fake_auto_enrich(project_id, body, *, principal, pool):
        captured["project_id"] = project_id
        captured["book_id"] = body.book_id
        captured["user_id"] = principal.user_id
        captured["max_gaps"] = body.max_gaps
        return {"project_id": str(project_id), "job_id": "job-1", "enqueued": True}

    async with _patched(AsyncMock(side_effect=fake_auto_enrich)):
        res = await srv.lore_enrichment_auto_enrich(
            _Ctx(), project_id=str(PROJECT),
            args=srv._AutoEnrichArgs(
                book_id=str(BOOK), embedding_model_ref=str(EMB),
                generation_model_ref=str(GEN), max_gaps=7,
            ),
        )
    assert res["job_id"] == "job-1"
    assert captured["project_id"] == PROJECT
    assert captured["book_id"] == BOOK
    assert captured["user_id"] == TEST_USER  # identity from the envelope, not an arg
    assert captured["max_gaps"] == 7


async def test_auto_enrich_passes_explicit_targets():
    import app.mcp.server as srv

    captured = {}

    async def fake_auto_enrich(project_id, body, *, principal, pool):
        captured["targets"] = body.targets
        return {"enqueued": True}

    async with _patched(AsyncMock(side_effect=fake_auto_enrich)):
        await srv.lore_enrichment_auto_enrich(
            _Ctx(), project_id=str(PROJECT),
            args=srv._AutoEnrichArgs(
                book_id=str(BOOK), embedding_model_ref=str(EMB),
                generation_model_ref=str(GEN),
                targets=[{"canonical_name": "Dracula", "entity_kind": "vampire"}],
            ),
        )
    assert captured["targets"] is not None
    assert captured["targets"][0].canonical_name == "Dracula"


async def test_auto_enrich_http_error_becomes_tool_refusal():
    import app.mcp.server as srv

    async def boom(project_id, body, *, principal, pool):
        raise HTTPException(status_code=400, detail="unknown technique 'bogus'")

    async with _patched(AsyncMock(side_effect=boom)):
        res = await srv.lore_enrichment_auto_enrich(
            _Ctx(), project_id=str(PROJECT),
            args=srv._AutoEnrichArgs(
                book_id=str(BOOK), embedding_model_ref=str(EMB),
                generation_model_ref=str(GEN), technique="bogus",
            ),
        )
    assert res["success"] is False
    assert "bogus" in res["error"]
    assert res["status"] == 400
