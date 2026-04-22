"""K19d.2 + K19d.4 — unit tests for the browse/detail entity endpoints.

Covers the router + Query-validation layer. Neo4j interaction is
mocked; integration tests live at
`tests/integration/db/test_entities_repo_k19d.py`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.entities import Entity, EntityDetail, MergeEntitiesError
from app.db.neo4j_repos.relations import Relation


_TEST_USER = uuid4()
_PROJECT_ID = uuid4()
_ENTITY_ID = "ent-abc123"
_OTHER_ENTITY_ID = "ent-xyz789"


def _entity_stub(
    name: str = "Master Kai",
    canonical_id: str = _ENTITY_ID,
    project_id: str | None = None,
    kind: str = "character",
) -> Entity:
    return Entity(
        id=canonical_id,
        user_id=str(_TEST_USER),
        project_id=project_id,
        name=name,
        canonical_name=name.lower(),
        kind=kind,
        aliases=[name],
        canonical_version=1,
        source_types=["chat_turn"],
        confidence=0.9,
        mention_count=12,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _relation_stub(
    subject_id: str = _ENTITY_ID,
    object_id: str = _OTHER_ENTITY_ID,
    predicate: str = "mentors",
) -> Relation:
    return Relation(
        id=f"rel-{subject_id}-{predicate}-{object_id}",
        user_id=str(_TEST_USER),
        subject_id=subject_id,
        object_id=object_id,
        predicate=predicate,
        confidence=0.8,
        valid_from=datetime.now(timezone.utc),
        valid_until=None,
        pending_validation=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        subject_name="Master Kai",
        subject_kind="character",
        object_name="Phoenix",
        object_kind="character",
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _make_client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app, raise_server_exceptions=False)


# ── K19d.2 — GET /v1/knowledge/entities ──────────────────────────────


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_entities_happy(mock_list):
    mock_list.return_value = ([_entity_stub("Kai"), _entity_stub("Phoenix")], 42)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert len(body["entities"]) == 2
    assert body["total"] == 42
    assert body["entities"][0]["name"] == "Kai"
    # Default params threaded through.
    kwargs = mock_list.await_args.kwargs
    assert kwargs["limit"] == 50
    assert kwargs["offset"] == 0
    assert kwargs["project_id"] is None
    assert kwargs["kind"] is None
    assert kwargs["search"] is None


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_entities_project_filter(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get(
        f"/v1/knowledge/entities?project_id={_PROJECT_ID}&kind=character",
    )
    assert resp.status_code == 200
    kwargs = mock_list.await_args.kwargs
    # Router casts UUID back to str for Neo4j.
    assert kwargs["project_id"] == str(_PROJECT_ID)
    assert kwargs["kind"] == "character"


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_entities_search_param(mock_list):
    mock_list.return_value = ([_entity_stub("Kai")], 1)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities?search=kai")
    assert resp.status_code == 200
    assert mock_list.await_args.kwargs["search"] == "kai"


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_entities_search_min_length_rejected(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    # min_length=2
    resp = client.get("/v1/knowledge/entities?search=k")
    assert resp.status_code == 422
    # Repo should not have been called.
    mock_list.assert_not_awaited()


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_entities_pagination_params(mock_list):
    mock_list.return_value = ([], 100)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities?limit=25&offset=50")
    assert resp.status_code == 200
    kwargs = mock_list.await_args.kwargs
    assert kwargs["limit"] == 25
    assert kwargs["offset"] == 50


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_list_entities_pagination_out_of_range_rejected(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    # limit le=200
    assert client.get("/v1/knowledge/entities?limit=500").status_code == 422
    # limit ge=1
    assert client.get("/v1/knowledge/entities?limit=0").status_code == 422
    # offset ge=0
    assert client.get("/v1/knowledge/entities?offset=-1").status_code == 422


# ── K19d.4 — GET /v1/knowledge/entities/{id} ─────────────────────────


@patch(
    "app.routers.public.entities.get_entity_with_relations",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_entity_detail_happy(mock_detail):
    mock_detail.return_value = EntityDetail(
        entity=_entity_stub(),
        relations=[_relation_stub(), _relation_stub(predicate="trains")],
        relations_truncated=False,
        total_relations=2,
    )
    client = _make_client()
    resp = client.get(f"/v1/knowledge/entities/{_ENTITY_ID}")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["entity"]["id"] == _ENTITY_ID
    assert len(body["relations"]) == 2
    assert body["relations_truncated"] is False
    assert body["total_relations"] == 2
    mock_detail.assert_awaited_once()
    assert mock_detail.await_args.kwargs["entity_id"] == _ENTITY_ID
    assert mock_detail.await_args.kwargs["user_id"] == str(_TEST_USER)


@patch(
    "app.routers.public.entities.get_entity_with_relations",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_entity_detail_not_found_404(mock_detail):
    """Repo returns None for both cross-user AND missing entities —
    router collapses both to 404 per KSA §6.4 anti-leak."""
    mock_detail.return_value = None
    client = _make_client()
    resp = client.get(f"/v1/knowledge/entities/{_ENTITY_ID}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "entity not found"


@patch(
    "app.routers.public.entities.get_entity_with_relations",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_entity_detail_rejects_oversized_id(mock_detail):
    """Review-impl L1: `entity_id` Path has max_length=200. 201-char
    id should 422 before hitting Neo4j."""
    mock_detail.return_value = None
    client = _make_client()
    resp = client.get("/v1/knowledge/entities/" + ("x" * 201))
    assert resp.status_code == 422
    mock_detail.assert_not_awaited()


# ── K19d γ-a — PATCH /entities/{id} ─────────────────────────────────


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_happy(mock_update):
    stub = _entity_stub(name="Kai the Brave")
    mock_update.return_value = stub
    client = _make_client()
    resp = client.patch(
        f"/v1/knowledge/entities/{_ENTITY_ID}",
        json={"name": "Kai the Brave"},
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["name"] == "Kai the Brave"
    kwargs = mock_update.await_args.kwargs
    assert kwargs["entity_id"] == _ENTITY_ID
    assert kwargs["name"] == "Kai the Brave"
    assert kwargs["kind"] is None
    assert kwargs["aliases"] is None


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_rejects_empty_body(mock_update):
    mock_update.return_value = None
    client = _make_client()
    resp = client.patch(f"/v1/knowledge/entities/{_ENTITY_ID}", json={})
    assert resp.status_code == 422
    mock_update.assert_not_awaited()


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_rejects_empty_alias(mock_update):
    mock_update.return_value = None
    client = _make_client()
    resp = client.patch(
        f"/v1/knowledge/entities/{_ENTITY_ID}",
        json={"aliases": ["valid", "   "]},
    )
    assert resp.status_code == 422
    mock_update.assert_not_awaited()


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_not_found(mock_update):
    mock_update.return_value = None
    client = _make_client()
    resp = client.patch(
        f"/v1/knowledge/entities/{_ENTITY_ID}",
        json={"name": "new name"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "entity not found"


@patch(
    "app.routers.public.entities.get_entity_with_relations",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_entity_detail_truncation_flag(mock_detail):
    mock_detail.return_value = EntityDetail(
        entity=_entity_stub(),
        relations=[_relation_stub() for _ in range(200)],
        relations_truncated=True,
        total_relations=457,
    )
    client = _make_client()
    resp = client.get(f"/v1/knowledge/entities/{_ENTITY_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["relations_truncated"] is True
    assert body["total_relations"] == 457
    assert len(body["relations"]) == 200


# ── K19d γ-b — POST /entities/{id}/merge-into/{other_id} ────────────


@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_happy(mock_merge):
    mock_merge.return_value = _entity_stub(name="Kai (merged)")
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["target"]["name"] == "Kai (merged)"
    kwargs = mock_merge.await_args.kwargs
    assert kwargs["source_id"] == _ENTITY_ID
    assert kwargs["target_id"] == _OTHER_ENTITY_ID
    assert kwargs["user_id"] == str(_TEST_USER)


@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_same_entity_400(mock_merge):
    mock_merge.side_effect = MergeEntitiesError(
        "same_entity", "source and target must be distinct"
    )
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_ENTITY_ID}",
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "same_entity"


@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_not_found_404(mock_merge):
    mock_merge.side_effect = MergeEntitiesError(
        "entity_not_found", "entity not found"
    )
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error_code"] == "entity_not_found"


@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_archived_409(mock_merge):
    mock_merge.side_effect = MergeEntitiesError(
        "entity_archived", "cannot merge archived entities"
    )
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "entity_archived"


@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_glossary_conflict_409(mock_merge):
    mock_merge.side_effect = MergeEntitiesError(
        "glossary_conflict", "distinct glossary anchors"
    )
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "glossary_conflict"
