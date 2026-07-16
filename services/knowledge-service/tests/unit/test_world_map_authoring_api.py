"""T2.5 World Map — unit tests for the manual entity/relation create endpoints.

Covers the router + request validation layer. The Neo4j repo functions
(``merge_entity`` / ``recreate_relation``) are mocked — they have their own
live-Neo4j coverage under tests/integration/db/. Mirrors the
``test_entities_browse_api`` TestClient + dependency-override pattern.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.entities import Entity
from app.db.neo4j_repos.relations import Relation

_TEST_USER = uuid4()
_PROJECT_ID = uuid4()
_SUBJ = "ent-keep"
_OBJ = "ent-ash"


def _entity_stub(name: str = "Hollow Keep", kind: str = "location") -> Entity:
    return Entity(
        id="ent-keep",
        user_id=str(_TEST_USER),
        project_id=str(_PROJECT_ID),
        name=name,
        canonical_name=name.lower(),
        kind=kind,
        aliases=[name],
        canonical_version=1,
        source_types=["manual"],
        confidence=1.0,
        mention_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _relation_stub(predicate: str = "borders") -> Relation:
    return Relation(
        id=f"rel-{_SUBJ}-{predicate}-{_OBJ}",
        user_id=str(_TEST_USER),
        subject_id=_SUBJ,
        object_id=_OBJ,
        predicate=predicate,
        confidence=1.0,
        valid_from=datetime.now(timezone.utc),
        valid_until=None,
        pending_validation=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        subject_name="Hollow Keep",
        subject_kind="location",
        object_name="The Ashlands",
        object_kind="location",
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _make_client() -> TestClient:
    from app.main import app
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    from app.main import app
    app.dependency_overrides.clear()


# ── POST /v1/knowledge/entities ──────────────────────────────────────


@patch("app.routers.public.entities.merge_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_create_entity_happy(mock_merge):
    mock_merge.return_value = _entity_stub()
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/entities",
            json={"project_id": str(_PROJECT_ID), "name": "  Hollow Keep  ", "kind": "location"},
        )
        assert resp.status_code == 201, resp.json()
        assert resp.json()["name"] == "Hollow Keep"
        # user-asserted manual create: trimmed name, source_type=manual, conf 1.0.
        kwargs = mock_merge.await_args.kwargs
        assert kwargs["name"] == "Hollow Keep"
        assert kwargs["kind"] == "location"
        assert kwargs["source_type"] == "manual"
        assert kwargs["confidence"] == 1.0
        assert kwargs["user_id"] == str(_TEST_USER)
        assert kwargs["project_id"] == str(_PROJECT_ID)
    finally:
        _teardown()


@patch("app.routers.public.entities.merge_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_create_entity_rejects_unknown_kind(mock_merge):
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/entities",
            json={"project_id": str(_PROJECT_ID), "name": "Doohickey", "kind": "gadget"},
        )
        assert resp.status_code == 422
        mock_merge.assert_not_awaited()
    finally:
        _teardown()


# S7-1 — the 5-kind authorable set (create == agent), faction renamed out.
@pytest.mark.parametrize(
    "kind", ["character", "location", "organization", "concept", "item"]
)
@patch("app.routers.public.entities.merge_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_create_entity_accepts_all_five_authorable_kinds(mock_merge, kind):
    mock_merge.return_value = _entity_stub(name="Thing", kind=kind)
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/entities",
            json={"project_id": str(_PROJECT_ID), "name": "Thing", "kind": kind},
        )
        assert resp.status_code == 201, resp.json()
        assert mock_merge.await_args.kwargs["kind"] == kind
    finally:
        _teardown()


@patch("app.routers.public.entities.merge_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_create_entity_rejects_legacy_faction_misnomer(mock_merge):
    # ``faction`` was the old create-gate misnomer; it is now renamed to
    # ``organization`` and must 422 (proving the rename, not a widen-only).
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/entities",
            json={"project_id": str(_PROJECT_ID), "name": "The Guild", "kind": "faction"},
        )
        assert resp.status_code == 422
        mock_merge.assert_not_awaited()
    finally:
        _teardown()


@patch("app.routers.public.entities.merge_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_create_entity_rejects_blank_name(mock_merge):
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/entities",
            json={"project_id": str(_PROJECT_ID), "name": "   ", "kind": "location"},
        )
        assert resp.status_code == 422
        mock_merge.assert_not_awaited()
    finally:
        _teardown()


# ── POST /v1/knowledge/relations ─────────────────────────────────────


@patch("app.routers.public.relations.recreate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
def test_create_relation_happy(mock_recreate):
    mock_recreate.return_value = _relation_stub("borders")
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/relations",
            json={"subject_id": _SUBJ, "object_id": _OBJ, "predicate": "borders"},
        )
        assert resp.status_code == 201, resp.json()
        assert resp.json()["predicate"] == "borders"
        kwargs = mock_recreate.await_args.kwargs
        assert kwargs["subject_id"] == _SUBJ
        assert kwargs["object_id"] == _OBJ
        assert kwargs["predicate"] == "borders"
        assert kwargs["user_id"] == str(_TEST_USER)
    finally:
        _teardown()


@patch("app.routers.public.relations.recreate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
def test_create_relation_missing_endpoint_409(mock_recreate):
    mock_recreate.return_value = None  # an endpoint entity isn't this user's
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/relations",
            json={"subject_id": _SUBJ, "object_id": _OBJ, "predicate": "route_to"},
        )
        assert resp.status_code == 409
    finally:
        _teardown()


@patch("app.routers.public.relations.recreate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
def test_create_relation_rejects_self_loop(mock_recreate):
    client = _make_client()
    try:
        resp = client.post(
            "/v1/knowledge/relations",
            json={"subject_id": _SUBJ, "object_id": _SUBJ, "predicate": "borders"},
        )
        assert resp.status_code == 422
        mock_recreate.assert_not_awaited()
    finally:
        _teardown()
