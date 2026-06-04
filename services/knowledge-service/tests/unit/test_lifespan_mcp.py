"""FIX #14 (MED) — lifespan coverage for the ARCH-1 C1 MCP session manager.

The MCP StreamableHTTP session manager is run INSIDE main.py's lifespan
(a mounted Starlette sub-app's lifespan is not auto-run under FastAPI),
entered via an ``AsyncExitStack`` so its teardown lands ahead of
``close_pools()``. Two invariants are pinned here, hermetically (no real
DB / Neo4j / Redis / uvicorn):

  (a) happy path — the session manager IS entered on startup, and on
      shutdown its ``aclose`` runs BEFORE ``close_pools`` (so a cancelled
      in-flight tool handler unwinds against a still-open pool).
  (b) non-fatal — if the session manager fails to start, the lifespan
      STILL yields (the bespoke /internal/tools/* routes stay up — dual
      run) and ``close_pools`` still runs in teardown.

Approach mirrors test_lifespan_startup_cleanup.py: monkeypatch every
pre-yield init step to a no-op/stub, keep ``settings.neo4j_uri`` and
``settings.redis_url`` falsy so the Neo4j/Redis-gated background loops are
all skipped, and replace ``mcp_server.session_manager.run`` with a
tracking async context manager that records enter/exit ordering into a
shared list alongside the ``close_*`` spies.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

import app.main as main_mod


def _stub_pre_yield_init(monkeypatch) -> None:
    """Neutralize every pre-yield init step so the lifespan reaches the
    MCP session-manager block (and the yield) without touching real infra.

    These names mirror test_lifespan_startup_cleanup.py's happy-path stubs;
    here they all SUCCEED so we reach the yield."""
    monkeypatch.setattr(main_mod, "setup_logging", lambda *_a, **_k: None)
    monkeypatch.setattr(main_mod, "create_pools", AsyncMock(return_value=None))
    monkeypatch.setattr(main_mod, "get_knowledge_pool", lambda: "fake-pool")
    monkeypatch.setattr(main_mod, "run_migrations", AsyncMock(return_value=None))
    monkeypatch.setattr(main_mod, "init_glossary_client", lambda: None)
    monkeypatch.setattr(main_mod, "get_book_client", lambda: "fake")
    monkeypatch.setattr(main_mod, "get_embedding_client", lambda: "fake")
    monkeypatch.setattr(main_mod, "get_llm_client", lambda: "fake")
    monkeypatch.setattr(main_mod, "init_neo4j_driver", AsyncMock(return_value=None))
    monkeypatch.setattr(main_mod, "get_neo4j_driver", lambda: "fake-driver")


def _spy_close_fns(monkeypatch, order: list[str]) -> None:
    """Replace every close_* the post-yield teardown calls with a spy that
    appends its name to ``order`` when awaited. This lets us assert the MCP
    aclose lands BEFORE close_pools by index comparison on the same list."""

    def mk(name: str):
        async def _close():
            order.append(name)
        return _close

    monkeypatch.setattr(main_mod, "close_cooldown_client", mk("cooldown_client"))
    monkeypatch.setattr(main_mod, "close_llm_client", mk("llm_client"))
    monkeypatch.setattr(main_mod, "close_embedding_client", mk("embedding_client"))
    monkeypatch.setattr(main_mod, "close_book_client", mk("book_client"))
    monkeypatch.setattr(main_mod, "close_glossary_client", mk("glossary_client"))
    monkeypatch.setattr(main_mod, "close_neo4j_driver", mk("neo4j_driver"))
    monkeypatch.setattr(main_mod, "close_pools", mk("pools"))


@pytest.mark.asyncio
async def test_lifespan_runs_mcp_session_manager_and_closes_before_pools(
    monkeypatch,
):
    """(a) happy path — the MCP session manager is entered on startup, and
    its teardown (aclose) runs BEFORE close_pools on shutdown."""
    order: list[str] = []

    _stub_pre_yield_init(monkeypatch)
    _spy_close_fns(monkeypatch, order)

    @asynccontextmanager
    async def _tracking_run():
        # Records enter/exit into the SAME ordered list as the close_*
        # spies so we can assert MCP aclose precedes close_pools.
        order.append("mcp_enter")
        try:
            yield None
        finally:
            order.append("mcp_aclose")

    monkeypatch.setattr(
        main_mod.mcp_server.session_manager, "run", _tracking_run
    )

    # neo4j_uri + redis_url falsy → every Neo4j/Redis-gated background loop
    # (filter reload, event consumer, anchor/summary/reconcile/quarantine
    # schedulers, cache invalidator) is skipped, so this stays hermetic.
    with patch.object(main_mod.settings, "neo4j_uri", ""), patch.object(
        main_mod.settings, "redis_url", ""
    ):
        async with main_mod.lifespan(main_mod.app):
            # Reaching here means the lifespan yielded (startup completed).
            # The session manager must have been entered (started) by now.
            assert "mcp_enter" in order, "MCP session manager was not started"

    # After the lifespan exits, teardown has run. Assert ordering:
    # MCP aclose happened, and it happened BEFORE close_pools.
    assert "mcp_aclose" in order, "MCP session manager was not torn down"
    assert "pools" in order, "close_pools did not run in teardown"
    assert order.index("mcp_aclose") < order.index("pools"), (
        f"MCP aclose must precede close_pools; order was {order}"
    )


@pytest.mark.asyncio
async def test_lifespan_mcp_start_failure_is_non_fatal(monkeypatch):
    """(b) non-fatal — if the MCP session manager fails to start, the
    lifespan STILL yields (bespoke /internal/tools/* stay up — dual-run)
    and close_pools still runs in teardown."""
    order: list[str] = []

    _stub_pre_yield_init(monkeypatch)
    _spy_close_fns(monkeypatch, order)

    @asynccontextmanager
    async def _failing_run():
        raise RuntimeError("session manager refused to start")
        yield None  # pragma: no cover — unreachable; keeps it a generator CM

    monkeypatch.setattr(
        main_mod.mcp_server.session_manager, "run", _failing_run
    )

    reached_yield = False
    with patch.object(main_mod.settings, "neo4j_uri", ""), patch.object(
        main_mod.settings, "redis_url", ""
    ):
        # No exception must escape the lifespan — the MCP-start failure is
        # caught and logged inside it.
        async with main_mod.lifespan(main_mod.app):
            reached_yield = True

    assert reached_yield, "lifespan did not yield despite a non-fatal MCP failure"
    # Teardown still closed the pools (and never attempted an MCP aclose,
    # since the exit stack was rolled back at start).
    assert "pools" in order, "close_pools did not run after non-fatal MCP failure"
    assert "mcp_aclose" not in order, (
        "MCP aclose should not run when the session manager never started"
    )
