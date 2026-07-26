"""Test env defaults — set before app.config.Settings() loads at import time.

Matches the Dockerfile test-stage env (INTERNAL_SERVICE_TOKEN=test_token) so
the internal-auth header assertions line up.
"""

import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("COMPOSITION_DB_URL", "postgresql://u:p@h:5432/composition")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_token")
os.environ.setdefault("JWT_SECRET", "s" * 32)
os.environ.setdefault("CONFIRM_TOKEN_SIGNING_SECRET", "c" * 32)


@pytest.fixture(autouse=True)
def _isolate_mcp_session_manager():
    """D-W2-MCP-SESSION-ISOLATION (part 2 — the cross-file collision).

    FastMCP's StreamableHTTPSessionManager.run() may be called only ONCE per instance.
    app.main's lifespan runs it (main.py:~105), so EVERY `with TestClient(app.main)` (the
    ~18 router test files) consumes the global mcp_server's session manager. After the
    first, later runs raise — the lifespan swallows it so REST tests still pass, but
    test_mcp_server's loopback (build_mcp_app + uvicorn, which runs the SAME global session
    manager) then fails to start in a full-suite run ('did not start in time').

    Stub ONLY the `app.main.mcp_server` binding (a no-op session_manager.run) so no app.main
    lifespan consumes the real manager. test_mcp_server uses build_mcp_app →
    `app.mcp.server.mcp_server` (a DIFFERENT module binding), so its real loopback is
    unaffected and becomes the sole, order-independent consumer."""
    @asynccontextmanager
    async def _noop_run():
        yield

    stub = MagicMock()
    stub.session_manager.run = _noop_run
    try:
        import app.main  # noqa: F401 — ensure the module is importable to patch its binding
    except Exception:
        yield
        return
    with patch("app.main.mcp_server", stub):
        yield
