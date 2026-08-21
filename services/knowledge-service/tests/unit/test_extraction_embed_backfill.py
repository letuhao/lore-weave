"""K17 cycle-12b — /internal/extraction/embed-entities-backfill route.

Covers the drain loop + its terminators, the degrade branches, and 404,
without a live DB: get_projects_repo is overridden and the producer
(embed_project_entities) is patched.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_projects_repo
from app.extraction.entity_embedder import EmbedEntitiesResult
from app.middleware.internal_auth import require_internal_token
from app.routers.internal_extraction import router

USER = str(uuid4())
PROJECT = str(uuid4())
BOOK = uuid4()
_PRODUCER = "app.extraction.entity_embedder.embed_project_entities"


@asynccontextmanager
async def _fake_session():
    """Stand-in for neo4j_session() — the producer is mocked so the session
    object is never actually used."""
    yield MagicMock()


def _project(model="model-uuid", dim=1024, book_id=BOOK):
    return SimpleNamespace(
        embedding_model=model, embedding_dimension=dim, book_id=book_id,
    )


def _repo(project):
    repo = SimpleNamespace()
    repo.get = AsyncMock(return_value=project)
    return repo


def _client(project):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_internal_token] = lambda: None
    app.dependency_overrides[get_projects_repo] = lambda: _repo(project)
    return TestClient(app)


def _post(client):
    return client.post(
        "/internal/extraction/embed-entities-backfill",
        json={"user_id": USER, "project_id": PROJECT},
    )


def test_drains_across_multiple_batches():
    client = _client(_project())
    # two full batches then a short one → drained.
    side = [
        EmbedEntitiesResult(embedded=200, skipped=0, candidates=200),
        EmbedEntitiesResult(embedded=200, skipped=0, candidates=200),
        EmbedEntitiesResult(embedded=50, skipped=0, candidates=50),
    ]
    with patch(_PRODUCER, new_callable=AsyncMock, side_effect=side), \
            patch("app.routers.internal_extraction.get_glossary_client"), \
            patch("app.routers.internal_extraction.neo4j_session", _fake_session), \
            patch("app.clients.embedding_client.get_embedding_client"):
        resp = _post(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["embedded"] == 450
    assert body["iterations"] == 3
    assert body["drained"] is True


def test_max_entities_cap_exits_the_loop():
    """The per-request cap (`max_entities`) stops the drain even when more
    candidates remain. Soft cap: the check is at the top of the loop, so a batch
    can overshoot by < BATCH (here cap=350, two 200-batches → 400, drained=False
    because the queue is NOT empty)."""
    client = _client(_project())
    side = [EmbedEntitiesResult(embedded=200, skipped=0, candidates=200)] * 10
    with patch(_PRODUCER, new_callable=AsyncMock, side_effect=side) as mock_prod, \
            patch("app.routers.internal_extraction.get_glossary_client"), \
            patch("app.routers.internal_extraction.neo4j_session", _fake_session), \
            patch("app.clients.embedding_client.get_embedding_client"):
        resp = client.post(
            "/internal/extraction/embed-entities-backfill",
            json={"user_id": USER, "project_id": PROJECT, "max_entities": 350},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["embedded"] == 400  # soft cap: overshoots by < BATCH
    assert body["iterations"] == 2
    assert body["drained"] is False  # cap hit, not drained
    assert mock_prod.await_count == 2


def test_no_progress_terminator_stops_the_loop():
    """A FULL batch of candidates but 0 embedded (all un-embeddable) must NOT
    loop forever — the find query would keep returning the same rows."""
    client = _client(_project())
    side = [EmbedEntitiesResult(embedded=0, skipped=200, candidates=200)] * 500
    with patch(_PRODUCER, new_callable=AsyncMock, side_effect=side) as mock_prod, \
            patch("app.routers.internal_extraction.get_glossary_client"), \
            patch("app.routers.internal_extraction.neo4j_session", _fake_session), \
            patch("app.clients.embedding_client.get_embedding_client"):
        resp = _post(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["embedded"] == 0
    assert body["iterations"] == 1  # stopped after the no-progress batch
    assert body["drained"] is False
    assert mock_prod.await_count == 1


def test_no_embedding_model_degrades_cleanly():
    client = _client(_project(model=None))
    with patch(_PRODUCER, new_callable=AsyncMock) as mock_prod:
        resp = _post(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["embedded"] == 0
    assert "embedding model" in body["reason"]
    mock_prod.assert_not_awaited()


def test_no_book_degrades_cleanly():
    client = _client(_project(book_id=None))
    with patch(_PRODUCER, new_callable=AsyncMock) as mock_prod:
        resp = _post(client)
    assert resp.status_code == 200
    assert resp.json()["reason"] == "project has no book"
    mock_prod.assert_not_awaited()


def test_project_not_found_404():
    client = _client(None)
    resp = _post(client)
    assert resp.status_code == 404


# ── D-K17-EMBED-FAILURE-REPORTED-AS-A-CLEAN-DRAIN ────────────────────────────
# Measured live 2026-08-21 while feeding the T25 vector soak: the embedding provider
# answered 502 with an HTML body, 25 anchored entities were left with no vector, and this
# endpoint returned {"embedded":0,"skipped":0,"iterations":1,"drained":true,"reason":null}.
# `EmbedEntitiesResult.embed_failed` was already set by the producer and simply never read,
# so the outage fell into the short-batch branch and was rendered as a finished drain. The
# soak it was meant to feed stayed at zero, and the zero looked healthy — which is the exact
# shape `soak-armed-gate` exists to refuse.


def test_a_provider_failure_is_NOT_reported_as_a_clean_drain():
    """The live shape: fewer candidates than a batch AND the provider failed.

    The short-batch terminator is what makes this dangerous — it is the branch that sets
    `drained=True`, so the smaller the leftover queue, the more convincing the false
    success. A caller polling `drained` to decide "the queue is empty" would stop here
    forever while every candidate still needs a vector.
    """
    client = _client(_project())
    side = [EmbedEntitiesResult(embedded=0, skipped=0, candidates=25, embed_failed=True)]
    with patch(_PRODUCER, new_callable=AsyncMock, side_effect=side), \
            patch("app.routers.internal_extraction.get_glossary_client"), \
            patch("app.routers.internal_extraction.neo4j_session", _fake_session), \
            patch("app.clients.embedding_client.get_embedding_client"):
        resp = _post(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["embedded"] == 0
    assert body["drained"] is False, (
        "a provider failure was reported as a drained queue — 25 candidates still need "
        "a vector and the caller has been told there is nothing left to do"
    )
    assert body["reason"], "the failure reached the caller with no reason attached"
    assert "provider" in body["reason"]


def test_a_GENUINE_short_batch_still_drains_so_the_fix_is_not_a_blanket_never_drained():
    """The control. `drained` must still be True when the batch was short for the ordinary
    reason — the queue really is empty. Without this, setting `drained=False` unconditionally
    would pass the test above and break every caller that polls to completion.
    """
    client = _client(_project())
    side = [EmbedEntitiesResult(embedded=25, skipped=0, candidates=25)]
    with patch(_PRODUCER, new_callable=AsyncMock, side_effect=side), \
            patch("app.routers.internal_extraction.get_glossary_client"), \
            patch("app.routers.internal_extraction.neo4j_session", _fake_session), \
            patch("app.clients.embedding_client.get_embedding_client"):
        resp = _post(client)
    body = resp.json()
    assert body["drained"] is True
    assert body["reason"] is None
