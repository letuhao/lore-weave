"""Unit tests for the KG-neighbourhood hash endpoint (D-WIKI-P2-KG-SWEEP).

POST /internal/knowledge/books/{id}/wiki/kg-hashes — recomputes the CURRENT
kg_neighborhood_hash per entity for the glossary KG-drift sweep. The parity
invariant (same render+hash as generation) and the Neo4j-down OMIT guard are the
load-bearing behaviours pinned here. gather_kg_facts + ProjectsRepo are mocked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.internal_auth import require_internal_token
from app.routers import internal_wiki
from app.wiki.fingerprint import stable_hash


def _client(projects, kg_side_effect) -> TestClient:
    app = FastAPI()
    app.include_router(internal_wiki.router)
    app.dependency_overrides[require_internal_token] = lambda: None
    pr = MagicMock()
    pr.list = AsyncMock(return_value=projects)
    app.dependency_overrides[internal_wiki.get_projects_repo] = lambda: pr
    internal_wiki.gather_kg_facts = kg_side_effect  # type: ignore[assignment]
    return TestClient(app)


def _post(client, entity_ids):
    return client.post(
        f"/internal/knowledge/books/{uuid4()}/wiki/kg-hashes",
        json={"user_id": str(uuid4()), "entity_ids": entity_ids},
    )


def test_hash_matches_canonical_stable_hash_of_facts():
    facts = ["Bob — knows → Alice", "Alice — rules → Land"]

    async def kg(**_kwargs):
        return list(facts)

    resp = _post(_client([MagicMock(project_id=uuid4())], kg), ["e1"])
    assert resp.status_code == 200
    # parity: the endpoint applies exactly stable_hash(sorted(facts)) — the same
    # computation generation stores as build_inputs.kg_neighborhood_hash.
    assert resp.json()["hashes"]["e1"] == stable_hash(sorted(facts))


def test_empty_neighbourhood_hashes_the_empty_list():
    async def kg(**_kwargs):
        return []

    resp = _post(_client([MagicMock(project_id=uuid4())], kg), ["e1"])
    assert resp.status_code == 200
    # an entity with no relations still gets a (stable, empty-list) hash — matches a
    # generation that had no KG facts, so it does NOT read as drift.
    assert resp.json()["hashes"]["e1"] == stable_hash(sorted([]))


def test_neo4j_unavailable_entity_is_omitted_not_empty_hashed():
    async def kg(**kwargs):
        kwargs["degraded"]["kg"] = "unavailable"
        return []

    resp = _post(_client([MagicMock(project_id=uuid4())], kg), ["e1", "e2"])
    assert resp.status_code == 200
    # a transient Neo4j outage must NOT surface as an empty-list hash (that would
    # false-flag every article whose stored neighbourhood was non-empty).
    assert resp.json()["hashes"] == {}


def test_no_project_returns_empty_map():
    async def kg(**_kwargs):
        return ["x"]

    resp = _post(_client([], kg), ["e1"])
    assert resp.status_code == 200
    assert resp.json()["hashes"] == {}


def test_no_entities_returns_empty_map():
    async def kg(**_kwargs):
        return ["x"]

    resp = _post(_client([MagicMock(project_id=uuid4())], kg), [])
    assert resp.status_code == 200
    assert resp.json()["hashes"] == {}
