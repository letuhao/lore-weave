"""Tiered-MCP-tools T4c — the chat-service ADMIN surface (cms admin chat).

Three guarantees, each mapped to a spec invariant:

1. **Catalog isolation (E17 / INV-T6).** `get_admin_tool_definitions` dials the
   SEPARATE `/mcp/admin` endpoint with `X-Admin-Token`; the user/book
   `get_tool_definitions` dials `/mcp`. The two caches are distinct, so admin
   tool names can never appear in a non-admin session's catalog.
2. **Authority routing (INV-T2).** `mcp_execute_tool(admin_token=…)` routes to
   `/mcp/admin` with `X-Admin-Token` and sends NO `X-User-Id` — admin authority
   is the verified RS256 token, never the user id.
3. **Surface curation (E17, TESTED not trusted).** A request carrying
   `admin_context` advertises ONLY the admin catalog + `glossary_confirm_action`
   — never the book/user write-back tools; a book request advertises the
   book/user tools and never reaches `/mcp/admin`.

Plus bearer hygiene: the `X-Admin-Token` value never appears in the logs (§6.7).
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Importing these test modules also performs their os.environ setup (DATABASE_URL,
# JWT_SECRET, INTERNAL_SERVICE_TOKEN, …) which the app config requires at import.
from tests.test_knowledge_client import _make_client, _mcp_tool, _patch_list_tools  # noqa: E402
from tests.test_mcp_execute_tool import _call_tool_result, _patch_mcp, _text_content  # noqa: E402
from tests.test_stream_service import (  # noqa: E402
    TEST_MODEL_REF,
    TEST_SESSION_ID,
    TEST_USER_ID,
    _make_creds,
    _make_pool_with_conn,
    _patched_knowledge,
)
from tests.test_stream_tools import _patch_client, _FakeClient, _drain, done, tok, usage  # noqa: E402

ADMIN_TOKEN = "rs256.admin.token.value.do-not-log"


# ════════════════════════════════════════════════════════════════════════════
# 1. get_admin_tool_definitions — /mcp/admin catalog isolation
# ════════════════════════════════════════════════════════════════════════════


class TestGetAdminToolDefinitions:
    @pytest.mark.asyncio
    async def test_no_token_returns_empty_without_transport(self):
        """No admin token → [] and NO transport opened (can't list /mcp/admin)."""
        client = _make_client()
        tpatch, spatch, factory = _patch_list_tools(tools=[_mcp_tool("glossary_admin_standards_read")])
        with tpatch, spatch:
            out = await client.get_admin_tool_definitions(None)
        assert out == []
        factory.assert_not_called()
        await client.aclose()

    @pytest.mark.asyncio
    async def test_fetches_from_mcp_admin_with_admin_token_header(self):
        """The catalog comes from `/mcp/admin` (NOT `/mcp`) with the RS256 token
        in `X-Admin-Token`, converted to the OpenAI function shape."""
        client = _make_client()
        tpatch, spatch, factory = _patch_list_tools(tools=[
            _mcp_tool("glossary_admin_standards_read", "read system standards"),
            _mcp_tool("glossary_admin_propose_create", "propose a system create"),
        ])
        with tpatch, spatch:
            out = await client.get_admin_tool_definitions(ADMIN_TOKEN)
        url = factory.call_args.args[0]
        assert url.endswith("/mcp/admin")
        headers = factory.call_args.kwargs["headers"]
        assert headers["X-Admin-Token"] == ADMIN_TOKEN
        assert "X-User-Id" not in headers  # admin authority is the token, not a user id
        names = [t["function"]["name"] for t in out]
        assert names == ["glossary_admin_standards_read", "glossary_admin_propose_create"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_admin_catalog_cached_separately_from_user_catalog(self):
        """The admin catalog is cached in its OWN field — a second call doesn't
        refetch, and the user `_tool_definitions` cache stays untouched (no
        cross-contamination of admin tools into the /mcp catalog)."""
        client = _make_client()
        tpatch, spatch, factory = _patch_list_tools(tools=[_mcp_tool("glossary_admin_standards_read")])
        with tpatch, spatch:
            first = await client.get_admin_tool_definitions(ADMIN_TOKEN)
            second = await client.get_admin_tool_definitions(ADMIN_TOKEN)
        assert first == second
        assert factory.call_count == 1  # cached
        assert client._tool_definitions is None  # user catalog never populated
        await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_failure_returns_empty_and_does_not_cache(self):
        """A transport/auth failure (incl. the 401 transport gate) degrades to
        [] and is NOT cached, so a later turn retries."""
        import httpx

        client = _make_client()
        tpatch, spatch, _ = _patch_list_tools(transport_side_effect=httpx.ConnectError("401"))
        with tpatch, spatch:
            assert await client.get_admin_tool_definitions(ADMIN_TOKEN) == []
        assert client._admin_tool_definitions is None  # not cached
        tpatch2, spatch2, _ = _patch_list_tools(tools=[_mcp_tool("glossary_admin_standards_read")])
        with tpatch2, spatch2:
            assert await client.get_admin_tool_definitions(ADMIN_TOKEN) != []
        await client.aclose()

    @pytest.mark.asyncio
    async def test_admin_token_never_logged_on_failure(self, caplog):
        """§6.7 — a fetch failure logs only the exception shape, never the
        bearer token."""
        import httpx

        client = _make_client()
        tpatch, spatch, _ = _patch_list_tools(transport_side_effect=httpx.ConnectError("boom"))
        with caplog.at_level(logging.WARNING), tpatch, spatch:
            await client.get_admin_tool_definitions(ADMIN_TOKEN)
        assert ADMIN_TOKEN not in caplog.text
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# 2. mcp_execute_tool(admin_token=…) — authority routing (INV-T2)
# ════════════════════════════════════════════════════════════════════════════


class TestAdminExecRouting:
    @pytest.mark.asyncio
    async def test_admin_exec_routes_to_admin_endpoint_no_user_id(self):
        """With admin_token set, the call dials `/mcp/admin`, carries
        `X-Admin-Token`, and sends NO `X-User-Id` (INV-T2)."""
        client = _make_client()
        result = _call_tool_result(content=[_text_content("{}")])
        tpatch, spatch, transport_factory, _, _ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="should-be-ignored",
                session_id="sess-A",
                tool_name="glossary_admin_propose_create",
                tool_args={"kind_code": "steampunk"},
                admin_token=ADMIN_TOKEN,
            )
        assert out["success"] is True
        call = transport_factory.call_args
        assert call.args[0].endswith("/mcp/admin")
        headers = call.kwargs["headers"]
        assert headers["X-Admin-Token"] == ADMIN_TOKEN
        assert "X-User-Id" not in headers
        assert "X-Project-Id" not in headers
        await client.aclose()

    @pytest.mark.asyncio
    async def test_non_admin_exec_unchanged_user_endpoint(self):
        """Without admin_token the path is unchanged: `/mcp` + `X-User-Id`,
        never an admin token."""
        client = _make_client()
        result = _call_tool_result(content=[_text_content("{}")])
        tpatch, spatch, transport_factory, _, _ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            await client.mcp_execute_tool(
                user_id="user-7", session_id="s", tool_name="memory_search", tool_args={},
            )
        call = transport_factory.call_args
        assert call.args[0].endswith("/mcp")
        assert not call.args[0].endswith("/mcp/admin")
        headers = call.kwargs["headers"]
        assert headers["X-User-Id"] == "user-7"
        assert "X-Admin-Token" not in headers
        await client.aclose()

    @pytest.mark.asyncio
    async def test_admin_token_never_logged_on_exec_failure(self, caplog):
        """§6.7 — an admin exec transport failure never logs the token."""
        import httpx

        client = _make_client()
        tpatch, spatch, *_ = _patch_mcp(transport_side_effect=httpx.ConnectError("refused"))
        with caplog.at_level(logging.WARNING), tpatch, spatch:
            await client.mcp_execute_tool(
                user_id="u", session_id="s",
                tool_name="glossary_admin_propose_create", tool_args={},
                admin_token=ADMIN_TOKEN,
            )
        assert ADMIN_TOKEN not in caplog.text
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# 3. stream_response surface curation (E17) — which tools each surface advertises
# ════════════════════════════════════════════════════════════════════════════
#
# Drive a real stream_response turn with the provider Client faked (_FakeClient
# records each StreamRequest, so request.tools is the advertised catalog) and the
# knowledge client mocked so we can see which fetch method each surface calls.


def _admin_knowledge():
    """A mock knowledge client exposing BOTH catalog fetchers so a test can
    assert which one a surface uses. Admin catalog = one admin tool; user
    catalog = one memory tool."""
    kc = _patched_knowledge(
        tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
    )
    kc.get_admin_tool_definitions = AsyncMock(return_value=[
        {"type": "function", "function": {"name": "glossary_admin_propose_create"}},
    ])
    return kc


def _advertised_tool_names() -> set[str]:
    """The function names on the FIRST provider request (iteration 0 carries the
    advertised tools)."""
    req = _FakeClient.instances[0].requests[0]
    return {t["function"]["name"] for t in (req.tools or [])}


class TestSurfaceCuration:
    @pytest.mark.asyncio
    async def test_admin_surface_only_admin_tools_plus_confirm(self):
        """admin_context → admin catalog + glossary_confirm_action ONLY. Never
        the book/user write-back tools, never the user /mcp catalog."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _admin_knowledge()

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
                _patch_client([[tok("ok"), done("stop")]]):
            from app.services.stream_service import stream_response
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="add a steampunk genre",
                user_id=TEST_USER_ID, model_source="user_model", model_ref=TEST_MODEL_REF,
                creds=_make_creds(), pool=pool, billing=AsyncMock(),
                stream_format="agui",
                admin_context={"label": "Admin"}, admin_token=ADMIN_TOKEN,
            ):
                pass

        names = _advertised_tool_names()
        assert "glossary_admin_propose_create" in names
        assert "glossary_confirm_action" in names
        # Curation: NO book/user write-back tools, NO user memory catalog.
        assert "glossary_propose_entity_edit" not in names
        assert "propose_edit" not in names
        assert "memory_search" not in names
        # The admin catalog was fetched with the token; the user catalog was NOT.
        kc.get_admin_tool_definitions.assert_awaited_once_with(ADMIN_TOKEN)
        kc.get_tool_definitions.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_book_surface_never_sees_admin_tools(self):
        """A book-scoped chat advertises the book/user tools and NEVER an
        admin tool; it never dials /mcp/admin."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _admin_knowledge()

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
                _patch_client([[tok("ok"), done("stop")]]):
            from app.services.stream_service import stream_response
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="who is Kai?",
                user_id=TEST_USER_ID, model_source="user_model", model_ref=TEST_MODEL_REF,
                creds=_make_creds(), pool=pool, billing=AsyncMock(),
                stream_format="agui",
                book_context={"book_id": "book-1"},
            ):
                pass

        names = _advertised_tool_names()
        assert "glossary_propose_entity_edit" in names
        assert "glossary_confirm_action" in names
        assert not any(n.startswith("glossary_admin_") for n in names)
        # The admin catalog was never touched on a book surface.
        kc.get_admin_tool_definitions.assert_not_awaited()


# ════════════════════════════════════════════════════════════════════════════
# 4. resume_stream_response curation (E17 on the RESUME path)
# ════════════════════════════════════════════════════════════════════════════
#
# The fresh stream curates by surface; the resume (post-confirm 2nd pass) must
# curate IDENTICALLY when the admin re-presents X-Admin-Token — else a refactor
# could silently re-advertise the book/user write-back tools on an admin resume.


def _suspended_admin():
    from app.db.suspended_runs import SuspendedRun

    return SuspendedRun(
        run_id="run-A",
        session_id=str(TEST_SESSION_ID),
        owner_user_id=str(TEST_USER_ID),
        message_id="m-A",
        working=[
            {"role": "user", "content": "add a steampunk genre"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "glossary_confirm_action", "arguments": "{}"},
                    }
                ],
            },
        ],
        pending_tool_call={"id": "c1", "name": "glossary_confirm_action", "args": {}},
        input_tokens=1,
        output_tokens=1,
        model_source="user_model",
        model_ref=str(TEST_MODEL_REF),
        parent_message_id=None,
        user_message_content="add a steampunk genre",
    )


class TestResumeCuration:
    @pytest.mark.asyncio
    async def test_admin_resume_readvertises_admin_catalog_only(self):
        """resume_stream_response(admin_token=…) re-advertises the admin catalog
        + glossary_confirm_action ONLY — never the book/user write-back tools,
        never the user /mcp catalog (curation holds across the confirm round-trip)."""
        from app.services.stream_service import resume_stream_response

        pool, conn = _make_pool_with_conn()
        conn.fetchval.return_value = 1
        pool.fetchrow.return_value = {"generation_params": {}, "project_id": None}
        kc = _admin_knowledge()
        scripts = [[tok("Done."), usage(2, 1), done("stop")]]

        with _patch_client(scripts), \
                patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
                patch("app.services.stream_service.load_suspended_run",
                      AsyncMock(return_value=_suspended_admin())), \
                patch("app.services.stream_service.delete_suspended_run", AsyncMock()):
            await _drain(resume_stream_response(
                session_id=str(TEST_SESSION_ID), user_id=str(TEST_USER_ID),
                run_id="run-A", tool_call_id="c1", outcome="action_done",
                applied_text=None, creds=_make_creds(), pool=pool, billing=AsyncMock(),
                stream_format="agui", admin_token=ADMIN_TOKEN,
            ))

        names = _advertised_tool_names()
        assert "glossary_confirm_action" in names
        assert "glossary_admin_propose_create" in names
        assert "glossary_propose_entity_edit" not in names
        assert "propose_edit" not in names
        assert "memory_search" not in names
        kc.get_admin_tool_definitions.assert_awaited_once_with(ADMIN_TOKEN)
        kc.get_tool_definitions.assert_not_awaited()
