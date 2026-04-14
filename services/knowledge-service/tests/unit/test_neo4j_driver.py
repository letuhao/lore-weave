"""K11.2 unit tests — driver init + lifecycle.

Covers the no-network paths:
  - empty NEO4J_URI → init is a no-op, get_neo4j_driver raises
    Neo4jNotConfiguredError ("Track 1 mode")
  - get_neo4j_driver before init_neo4j_driver runs → raises
    Neo4jNotConfiguredError ("lifespan didn't run")
  - close_neo4j_driver is idempotent on unconfigured / already-closed
    state

The "configured + reachable" happy path is exercised by the K11.3
integration test which boots the live Neo4j and runs the schema
script. Splitting like that lets unit tests run on a laptop without
the compose stack.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.db import neo4j as neo4j_module
from app.db.neo4j import (
    Neo4jNotConfiguredError,
    Neo4jStartupError,
    close_neo4j_driver,
    get_neo4j_driver,
    init_neo4j_driver,
)


@pytest.fixture(autouse=True)
def _reset_driver_state(monkeypatch):
    """Reset the module-level singleton between tests so order
    doesn't matter and one test's init doesn't leak to the next."""
    monkeypatch.setattr(neo4j_module, "_driver", None)
    monkeypatch.setattr(neo4j_module, "_init_attempted", False)
    yield
    monkeypatch.setattr(neo4j_module, "_driver", None)
    monkeypatch.setattr(neo4j_module, "_init_attempted", False)


def test_k11_2_get_driver_before_init_raises():
    """Calling get_neo4j_driver before the lifespan hook ran is a
    programmer error — distinguish from the Track 1 'configured but
    intentionally absent' case via a different message."""
    with pytest.raises(Neo4jNotConfiguredError, match="lifespan startup hook"):
        get_neo4j_driver()


@pytest.mark.asyncio
async def test_k11_2_init_with_empty_uri_is_noop(monkeypatch):
    """K11.2 Track 1 mode: empty NEO4J_URI → init silently skips,
    get_neo4j_driver raises with the 'Track 1' message."""
    monkeypatch.setattr(settings, "neo4j_uri", "")
    await init_neo4j_driver()
    # init was called — the singleton should still be None but
    # _init_attempted should be True.
    assert neo4j_module._driver is None
    assert neo4j_module._init_attempted is True
    # Asking for the driver now should raise the Track 1 variant.
    with pytest.raises(Neo4jNotConfiguredError, match="Track 1 mode"):
        get_neo4j_driver()


@pytest.mark.asyncio
async def test_k11_2_init_with_unreachable_uri_raises_startup_error(monkeypatch):
    """K11.2 spec: 'Startup fails if Neo4j unreachable.' Set a
    URI pointing nowhere and assert the typed Neo4jStartupError
    propagates so the lifespan hook can fail uvicorn cleanly."""
    monkeypatch.setattr(settings, "neo4j_uri", "bolt://127.0.0.1:65535")
    monkeypatch.setattr(settings, "neo4j_connection_timeout_s", 1.0)
    with pytest.raises(Neo4jStartupError, match="Neo4j unreachable"):
        await init_neo4j_driver()
    # Driver state is cleaned up on failure — no partial state leaks.
    assert neo4j_module._driver is None


@pytest.mark.asyncio
async def test_k11_2_close_is_idempotent_when_unconfigured():
    """close_neo4j_driver must be safe to call from the FastAPI
    lifespan shutdown hook even when init was a no-op (Track 1)."""
    await close_neo4j_driver()  # Should not raise.
    assert neo4j_module._driver is None


@pytest.mark.asyncio
async def test_k11_2_close_resets_init_attempted_flag():
    """Closing the driver also resets `_init_attempted` so a
    subsequent get_neo4j_driver call gets the 'lifespan didn't
    run' error rather than the misleading 'Track 1' one."""
    neo4j_module._init_attempted = True
    await close_neo4j_driver()
    assert neo4j_module._init_attempted is False
