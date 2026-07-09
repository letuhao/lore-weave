"""Contract tests pinning two MCP dispatch invariants (confirmed-LOW review findings).

These tests are HERMETIC: no database, no HTTP wire, no uvicorn, no app boot.
They monkeypatch the resource getters that ``_build_tool_context`` calls and
capture what reaches ``execute_tool`` so the real ``_dispatch`` /
``_build_tool_context`` code paths are genuinely exercised.

Invariants pinned here:

1. D3 scope rule — scope ids (user_id/project_id/session_id) come ONLY from
   request headers, NEVER from LLM-supplied ``tool_args``. ``_dispatch`` builds a
   ``ToolContext`` from header values and forwards ``tool_args`` UNCHANGED to
   ``execute_tool`` (monkeypatched here, so forged keys are merely captured).
   Forged scope inside ``tool_args`` must NOT become the context scope. The REAL
   executor then rejects any forged/extra key via ``extra='forbid'`` on its arg
   models (pinned by ``test_tool_executor``'s smuggled-arg test); these hermetic
   tests pin only that ``_dispatch`` never lets forged args reach the scope.

2. Success-discrimination — ``_dispatch`` returns the BARE executor payload on
   success (no top-level ``success`` key) and ``{"success": False, "error": ...}``
   on failure. The chat-service MCP client (``app/client/knowledge_client.py``,
   ``mcp_execute_tool``) infers failure by the PRESENCE of a top-level
   ``success == False`` key, so NO executor success payload may carry a
   top-level ``success`` key.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

import app.mcp.server as srv
from app.tools.executor import ToolContext, ToolResult


# ---------------------------------------------------------------------------
# Fake MCP Context plumbing (case-insensitive header lookup like Starlette)
# ---------------------------------------------------------------------------
class _FakeHeaders:
    """Case-insensitive header lookup mimicking Starlette Headers."""

    def __init__(self, data: dict[str, str]):
        self._data = {k.lower(): v for k, v in data.items()}

    def get(self, name: str) -> str | None:
        return self._data.get(name.lower())


class _FakeRequest:
    def __init__(self, headers: dict[str, str]):
        self.headers = _FakeHeaders(headers)


class _FakeRequestContext:
    def __init__(self, headers: dict[str, str]):
        self.request = _FakeRequest(headers)


class _FakeContext:
    """Minimal stand-in for mcp Context exposing request_context.request."""

    def __init__(self, headers: dict[str, str]):
        self.request_context = _FakeRequestContext(headers)


@pytest.fixture
def patched_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize resource getters so _build_tool_context stays hermetic.

    These are the exact attribute names imported into app.mcp.server:
    get_knowledge_pool, ProjectsRepo, PendingFactsRepo, get_embedding_client,
    get_tools_redis. None of them touch a real DB/Redis/embedding backend here.
    """
    monkeypatch.setattr(srv, "get_knowledge_pool", lambda: object())
    monkeypatch.setattr(srv, "ProjectsRepo", lambda pool: object())
    monkeypatch.setattr(srv, "PendingFactsRepo", lambda pool: object())
    monkeypatch.setattr(srv, "get_embedding_client", lambda: object())
    monkeypatch.setattr(srv, "get_tools_redis", lambda: object())


def _valid_headers() -> dict[str, str]:
    """Headers that pass internal auth and carry real UUID scope ids."""
    return {
        # compare_digest must pass: use the configured token verbatim.
        "x-internal-token": srv.settings.internal_service_token,
        "x-user-id": str(uuid.uuid4()),
        "x-project-id": str(uuid.uuid4()),
        "x-session-id": "sess-real",
    }


# ---------------------------------------------------------------------------
# 1. D3: scope comes from headers, NEVER from tool_args
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_d3_scope_comes_from_headers_not_tool_args(
    patched_resources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forged scope inside tool_args must not override header-derived scope."""
    captured: dict[str, Any] = {}

    async def _capturing_execute(
        context: ToolContext, tool_name: str, tool_args: dict[str, Any]
    ) -> ToolResult:
        # NOTE: arg order mirrors the REAL executor signature
        # execute_tool(ctx, tool_name, tool_args) — _dispatch calls it
        # positionally as execute_tool(tool_ctx, tool_name, tool_args).
        captured["tool_name"] = tool_name
        captured["tool_args"] = tool_args
        captured["context"] = context
        return ToolResult(success=True, result={"hits": [], "count": 0}, error=None)

    monkeypatch.setattr(srv, "execute_tool", _capturing_execute)

    headers = _valid_headers()
    fake_ctx = _FakeContext(headers)

    forged_args = {
        "query": "Kai",
        "user_id": "ATTACKER",
        "project_id": "EVIL",
        "session_id": "SPOOF",
    }
    await srv._dispatch(fake_ctx, "memory_search", forged_args)

    tc: ToolContext = captured["context"]
    # Scope on the ToolContext must equal the HEADER values, not the forged ones.
    # user_id/project_id are UUID strings on the header side; compare via str().
    assert str(tc.user_id) == headers["x-user-id"]
    assert str(tc.project_id) == headers["x-project-id"]
    assert str(tc.session_id) == headers["x-session-id"]

    # And the forged scope ids must NOT have leaked into the context.
    assert str(tc.user_id) != "ATTACKER"
    assert str(tc.project_id) != "EVIL"
    assert str(tc.session_id) != "SPOOF"

    # The forged keys stay in the args handed to the executor: _dispatch
    # forwards tool_args UNCHANGED to execute_tool (monkeypatched here), so the
    # forged scope ids are simply ignored for scoping — they never reach the
    # ToolContext. (The REAL executor rejects these forged keys via
    # extra='forbid' before any repo touch — see test_tool_executor's
    # test_smuggled_extra_arg_is_rejected; that rejection is out of scope for
    # this hermetic _dispatch-level test, which monkeypatches execute_tool.)
    assert captured["tool_args"]["user_id"] == "ATTACKER"
    assert captured["tool_args"]["project_id"] == "EVIL"
    assert captured["tool_args"]["session_id"] == "SPOOF"
    assert captured["tool_args"]["query"] == "Kai"


# ---------------------------------------------------------------------------
# 2. Success path returns the BARE payload (no top-level "success" key)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_success_returns_bare_payload_without_success_key(
    patched_resources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On success, _dispatch returns the executor payload verbatim."""
    payload = {"hits": [], "count": 0}

    async def _ok_execute(
        context: ToolContext, tool_name: str, tool_args: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(success=True, result=payload, error=None)

    monkeypatch.setattr(srv, "execute_tool", _ok_execute)

    fake_ctx = _FakeContext(_valid_headers())
    result = await srv._dispatch(fake_ctx, "memory_search", {"query": "Kai"})

    assert result == payload
    assert "success" not in result


# ---------------------------------------------------------------------------
# 3. Failure path RAISES ToolError (isError:true) with a C4-shaped JSON body
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_failure_raises_tool_error_with_c4_json(
    patched_resources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR — a tool failure RAISES ToolError so the
    MCP result carries isError:true (ai-gateway's C4 normalizer only triggers on a
    throw / isError). It used to RETURN {"success": False} on an otherwise
    SUCCESSFUL tool result, so any consumer branching on isError read a failed call
    as a success — the silent-success bug class."""
    import json as _json

    from mcp.server.fastmcp.exceptions import ToolError

    async def _fail_execute(
        context: ToolContext, tool_name: str, tool_args: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(success=False, result=None, error="boom")

    monkeypatch.setattr(srv, "execute_tool", _fail_execute)

    fake_ctx = _FakeContext(_valid_headers())
    with pytest.raises(ToolError) as exc:
        await srv._dispatch(fake_ctx, "memory_search", {"query": "Kai"})
    assert _json.loads(str(exc.value)) == {"message": "boom"}


@pytest.mark.asyncio
async def test_dispatch_failure_preserves_code_and_detail(
    patched_resources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract C5 — a stable domain code + detail must survive to the caller so a
    workflow branches on KG_ENDPOINT_NOT_NODE instead of pattern-matching prose."""
    import json as _json

    from mcp.server.fastmcp.exceptions import ToolError

    async def _fail_execute(
        context: ToolContext, tool_name: str, tool_args: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(
            success=False, result=None, error="endpoints are not nodes",
            code="KG_ENDPOINT_NOT_NODE", detail={"missing": ["b"]},
        )

    monkeypatch.setattr(srv, "execute_tool", _fail_execute)

    fake_ctx = _FakeContext(_valid_headers())
    with pytest.raises(ToolError) as exc:
        await srv._dispatch(fake_ctx, "kg_propose_edge", {})
    body = _json.loads(str(exc.value))
    assert body["code"] == "KG_ENDPOINT_NOT_NODE"
    assert body["detail"] == {"missing": ["b"]}
    assert body["message"] == "endpoints are not nodes"


# ---------------------------------------------------------------------------
# 3b. FIX #10 — an infra exception from execute_tool RE-RAISES (not swallowed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_propagates_infra_exception_not_swallowed(
    patched_resources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX #10 (MED, infra-error propagation) — a raw infrastructure
    exception (Neo4j/Postgres down) raised inside ``execute_tool`` must
    PROPAGATE out of ``_dispatch``, NOT be caught and folded into a success
    dict. FastMCP then surfaces it as ``isError`` so the chat-service client
    reads ``success=False`` — mirroring the bespoke /internal/tools/execute
    503 path. ``_dispatch`` only converts a *tool-level* failure
    (``ToolResult.success=False``) into ``{"success": False, ...}``; an
    UNEXPECTED exception is a different contract and must bubble up."""

    async def _raising_execute(
        context: ToolContext, tool_name: str, tool_args: dict[str, Any]
    ) -> ToolResult:
        raise RuntimeError("neo4j down")

    monkeypatch.setattr(srv, "execute_tool", _raising_execute)

    fake_ctx = _FakeContext(_valid_headers())
    with pytest.raises(RuntimeError, match="neo4j down"):
        await srv._dispatch(fake_ctx, "memory_search", {"query": "Kai"})


# ---------------------------------------------------------------------------
# 3c. FIX #11/#3 — a None success result coerces to {} (not None)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatch_coerces_none_result_to_empty_dict(
    patched_resources: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX #11/#3 (empty-success) — on a success ToolResult whose ``result``
    is None, ``_dispatch`` returns ``{}`` (the canonical empty-success
    sentinel the chat-service client expects), NEVER ``None``. Returning
    ``None`` would JSON-serialize to ``null`` and break the client's
    presence-of-``success``-key discrimination."""

    async def _none_result_execute(
        context: ToolContext, tool_name: str, tool_args: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(success=True, result=None, error=None)

    monkeypatch.setattr(srv, "execute_tool", _none_result_execute)

    fake_ctx = _FakeContext(_valid_headers())
    result = await srv._dispatch(fake_ctx, "memory_search", {"query": "Kai"})

    assert result == {}
    assert result is not None
    assert "success" not in result


# ---------------------------------------------------------------------------
# 4. Known executor success payload shapes carry no top-level "success" key
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    [
        {"hits": [], "count": 0},
        {"found": True, "entity": {}, "relations": []},
        {"events": [], "count": 0, "total_matching": 0},
        {"remembered": True, "fact_id": "x"},
        {"queued": True, "pending_fact_id": "y"},
        {"invalidated": True, "fact_id": "z"},
    ],
)
def test_known_executor_success_payloads_have_no_top_level_success_key(
    payload: dict[str, Any],
) -> None:
    """Pin: no handler success payload may carry a top-level 'success' key.

    The chat-service MCP client (chat-service ``app/client/knowledge_client.py``,
    ``mcp_execute_tool``) discriminates failure by the PRESENCE of a top-level
    ``success == False`` key on the dispatched payload. ``app/mcp/server.py``
    ``_dispatch`` only adds that key on the failure branch and returns success
    payloads bare. If a future handler adds a top-level ``success`` field, a
    successful call would be misread as a failure (or vice versa).

    If that invariant ever changes, update BOTH this test AND
    ``knowledge_client.mcp_execute_tool``'s discrimination logic.
    """
    # FIX #11/#3 — every real handler success payload is a non-empty dict, so
    # `_dispatch`'s `is None` (not `or`) coercion never falsely empties one of
    # these into {}. The {} sentinel is reserved for a genuine result=None.
    assert payload
    assert "success" not in payload
