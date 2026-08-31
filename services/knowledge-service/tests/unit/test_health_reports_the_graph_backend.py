"""T90 — `/health` must report which graph engine the process is actually on.

`knowledge-graph-backend-live-smoke.py` takes an `--expect-backend` and refuses to run
unless `/health` confirms it. That refusal is the only thing stopping the smoke from passing
against a stack running the OTHER engine and attributing the result to the one it was asked
about — a green naming the wrong thing, which is worse than a red.

So the field is a CONTRACT with that script, not a diagnostic nicety, and removing it breaks
a check whose failure would otherwise only appear at deploy time.

⚠️ Asserting the key EXISTS is not enough, and that is the whole design of this file. A
health route that returned a hardcoded `"age"` would satisfy a presence check while making
the smoke's verification vacuous — it would confirm whatever it was asked. Both cases below
are therefore parametrised over the two engines and assert the value FOLLOWS the
configuration, which is the only property the smoke actually relies on.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import health as health_router


def _pool_that_answers():
    """A pool whose `fetchval` returns 1, so `_ping` reports healthy."""
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=1)
    acq = MagicMock()
    acq.__aenter__ = AsyncMock(return_value=conn)
    acq.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acq)
    return pool


def _body(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["age", "neo4j"])
async def test_health_reports_the_configured_graph_backend(monkeypatch, backend):
    """The value tracks the configuration — it is not a constant.

    Parametrised over BOTH engines on purpose: a single case pinned to whichever engine the
    tree currently defaults to would pass against a hardcoded literal, which is exactly the
    failure that would make the live smoke's `--expect-backend` confirm anything it is told.
    """
    monkeypatch.setenv("KNOWLEDGE_GRAPH_BACKEND", backend)
    with patch.object(health_router, "get_knowledge_pool", return_value=_pool_that_answers()), \
            patch.object(health_router, "get_glossary_pool", return_value=_pool_that_answers()):
        resp = await health_router.health()

    body = _body(resp)
    assert body["graph_backend"] == backend, (
        f"/health reported {body.get('graph_backend')!r} while KNOWLEDGE_GRAPH_BACKEND was "
        f"{backend!r}. `knowledge-graph-backend-live-smoke.py` trusts this field to decide "
        f"whether it is proving the engine it was asked about."
    )
    assert body["status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["age", "neo4j"])
async def test_the_backend_is_still_reported_when_a_database_is_DOWN(monkeypatch, backend):
    """Degraded is when you most need to know which engine you are on.

    A field that appears only on the healthy path is absent exactly when someone is
    diagnosing a cutover, and the smoke would fail with "does not report `graph_backend`"
    rather than with the real problem.
    """
    monkeypatch.setenv("KNOWLEDGE_GRAPH_BACKEND", backend)
    dead = MagicMock()
    dead.acquire = MagicMock(side_effect=OSError("no route to host"))
    with patch.object(health_router, "get_knowledge_pool", return_value=_pool_that_answers()), \
            patch.object(health_router, "get_glossary_pool", return_value=dead):
        resp = await health_router.health()

    body = _body(resp)
    assert resp.status_code == 503 and body["status"] == "degraded"
    assert body["graph_backend"] == backend, (
        "the graph backend vanished from /health the moment a database went down")
