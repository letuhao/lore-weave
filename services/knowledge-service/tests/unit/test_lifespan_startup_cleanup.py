"""D-K11.3-01 — unit test for partial-startup resource cleanup.

If any pre-yield step raises, the lifespan should run every
close_* before re-raising so pools / drivers / clients don't leak
across a restart loop.

Phase 4a-δ: ``close_provider_client`` is gone (legacy module
deleted); the lifespan now closes ``llm_client`` (loreweave_llm SDK
wrapper) instead, and adds ``cooldown_client`` to the head of the
teardown list.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import app.main as main_mod


@pytest.mark.asyncio
async def test_startup_failure_closes_everything(monkeypatch):
    """Simulate a failure after pools + clients are up but before yield.

    Verify: every close_* ran, lifespan re-raised the original exception,
    and no resource was left dangling.
    """
    closed: list[str] = []

    async def mk_close(name: str):
        async def _close():
            closed.append(name)
        return _close

    # Patch all close_* entries so we can observe order + invocation.
    monkeypatch.setattr(main_mod, "close_cooldown_client",
                        await mk_close("cooldown_client"))
    monkeypatch.setattr(main_mod, "close_llm_client",
                        await mk_close("llm_client"))
    monkeypatch.setattr(main_mod, "close_embedding_client",
                        await mk_close("embedding_client"))
    monkeypatch.setattr(main_mod, "close_book_client",
                        await mk_close("book_client"))
    monkeypatch.setattr(main_mod, "close_glossary_client",
                        await mk_close("glossary_client"))
    monkeypatch.setattr(main_mod, "close_neo4j_driver",
                        await mk_close("neo4j_driver"))
    monkeypatch.setattr(main_mod, "close_pools", await mk_close("pools"))

    # Stub out the happy-path init steps so we can reach run_neo4j_schema
    # and make IT fail.
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

    # Force settings.neo4j_uri to truthy so run_neo4j_schema fires.
    with patch.object(main_mod.settings, "neo4j_uri", "bolt://fake"):
        async def boom(*a, **kw):
            raise RuntimeError("schema init blew up")
        monkeypatch.setattr(main_mod, "run_neo4j_schema", boom)

        with pytest.raises(RuntimeError, match="schema init blew up"):
            async with main_mod.lifespan(main_mod.app):
                pass  # pragma: no cover — shouldn't reach yield

    # Reverse-dependency teardown order is preserved (matches the tuple
    # in `_close_all_startup_resources`).
    assert closed == [
        "cooldown_client",
        "llm_client",
        "embedding_client",
        "book_client",
        "glossary_client",
        "neo4j_driver",
        "pools",
    ]


@pytest.mark.asyncio
async def test_startup_failure_close_exceptions_dont_mask_original(monkeypatch):
    """If a close_* itself raises during cleanup, the original startup
    exception is what propagates — cleanup errors just log."""
    async def ok_close():
        pass

    async def failing_close():
        raise RuntimeError("close also blew up")

    monkeypatch.setattr(main_mod, "close_cooldown_client", ok_close)
    monkeypatch.setattr(main_mod, "close_llm_client", ok_close)
    monkeypatch.setattr(main_mod, "close_embedding_client", failing_close)
    monkeypatch.setattr(main_mod, "close_book_client", ok_close)
    monkeypatch.setattr(main_mod, "close_glossary_client", ok_close)
    monkeypatch.setattr(main_mod, "close_neo4j_driver", ok_close)
    monkeypatch.setattr(main_mod, "close_pools", ok_close)

    monkeypatch.setattr(main_mod, "setup_logging", lambda *_a, **_k: None)
    monkeypatch.setattr(
        main_mod, "create_pools",
        AsyncMock(side_effect=RuntimeError("pools init failed")),
    )

    with pytest.raises(RuntimeError, match="pools init failed"):
        async with main_mod.lifespan(main_mod.app):
            pass  # pragma: no cover
