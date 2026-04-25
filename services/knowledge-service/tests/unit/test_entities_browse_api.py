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
    from app.deps import get_entity_alias_map_repo

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    # C17: stub the alias-map repo so get_knowledge_pool() isn't hit
    # in unit tests. Tests that need real-call assertion override
    # this with a sentinel after _make_client() returns.
    app.dependency_overrides[get_entity_alias_map_repo] = lambda: AsyncMock()
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
        headers={"If-Match": 'W/"1"'},
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["name"] == "Kai the Brave"
    # C9: ETag header handed back so the client can PATCH again
    # without a second GET.
    assert resp.headers["ETag"] == f'W/"{stub.version}"'
    kwargs = mock_update.await_args.kwargs
    assert kwargs["entity_id"] == _ENTITY_ID
    assert kwargs["name"] == "Kai the Brave"
    assert kwargs["kind"] is None
    assert kwargs["aliases"] is None
    # C9: expected_version parsed from the If-Match header.
    assert kwargs["expected_version"] == 1


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_rejects_empty_body(mock_update):
    mock_update.return_value = None
    client = _make_client()
    resp = client.patch(
        f"/v1/knowledge/entities/{_ENTITY_ID}",
        json={},
        headers={"If-Match": 'W/"1"'},
    )
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
        headers={"If-Match": 'W/"1"'},
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
        headers={"If-Match": 'W/"1"'},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "entity not found"


# ── C9 — If-Match contract + /unlock endpoint ─────────────────────


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_missing_if_match_428(mock_update):
    """D-K19d-γa-01: any PATCH without If-Match is almost certainly a
    stale client. Strict: 428 Precondition Required."""
    client = _make_client()
    resp = client.patch(
        f"/v1/knowledge/entities/{_ENTITY_ID}",
        json={"name": "new"},
    )
    assert resp.status_code == 428
    mock_update.assert_not_awaited()


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_bad_if_match_422(mock_update):
    """Malformed If-Match (not a weak ETag with integer version)
    returns 422. Matches projects.py/_parse_if_match contract."""
    client = _make_client()
    resp = client.patch(
        f"/v1/knowledge/entities/{_ENTITY_ID}",
        json={"name": "new"},
        headers={"If-Match": "not-an-etag"},
    )
    assert resp.status_code == 422
    mock_update.assert_not_awaited()


@patch(
    "app.routers.public.entities.update_entity_fields",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_patch_entity_version_mismatch_412_with_current_body(mock_update):
    """D-K19d-γa-01: mismatch returns 412 with the CURRENT entity as
    body + refreshed ETag header, so the FE can reset its baseline
    without a second GET."""
    from app.db.repositories import VersionMismatchError
    current = _entity_stub(name="Other Edit Won")
    # Simulate newer version at the DB.
    current = current.model_copy(update={"version": 5})
    mock_update.side_effect = VersionMismatchError(current)
    client = _make_client()
    resp = client.patch(
        f"/v1/knowledge/entities/{_ENTITY_ID}",
        json={"name": "my stale edit"},
        headers={"If-Match": 'W/"3"'},
    )
    assert resp.status_code == 412
    body = resp.json()
    assert body["name"] == "Other Edit Won"
    assert body["version"] == 5
    assert resp.headers["ETag"] == 'W/"5"'


@patch(
    "app.routers.public.entities.get_entity_with_relations",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_get_entity_detail_sets_etag_header(mock_detail):
    """D-K19d-γa-01: GET detail hands out an ETag the FE can send back
    on the next PATCH."""
    stub = _entity_stub()
    stub = stub.model_copy(update={"version": 7})
    mock_detail.return_value = EntityDetail(
        entity=stub,
        relations=[],
        relations_truncated=False,
        total_relations=0,
    )
    client = _make_client()
    resp = client.get(f"/v1/knowledge/entities/{_ENTITY_ID}")
    assert resp.status_code == 200
    assert resp.headers["ETag"] == 'W/"7"'


@patch(
    "app.routers.public.entities.unlock_entity_user_edited",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_unlock_entity_happy(mock_unlock):
    """D-K19d-γa-02: POST /unlock flips user_edited=false, bumps
    version, returns 200 with fresh ETag."""
    unlocked = _entity_stub().model_copy(update={"version": 4})
    mock_unlock.return_value = unlocked
    client = _make_client()
    resp = client.post(f"/v1/knowledge/entities/{_ENTITY_ID}/unlock")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["version"] == 4
    assert resp.headers["ETag"] == 'W/"4"'
    kwargs = mock_unlock.await_args.kwargs
    assert kwargs["entity_id"] == _ENTITY_ID


@patch(
    "app.routers.public.entities.unlock_entity_user_edited",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_unlock_entity_not_found(mock_unlock):
    """Cross-user / missing id — 404 via None return from repo."""
    mock_unlock.return_value = None
    client = _make_client()
    resp = client.post(f"/v1/knowledge/entities/{_ENTITY_ID}/unlock")
    assert resp.status_code == 404


@patch(
    "app.routers.public.entities.unlock_entity_user_edited",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_unlock_entity_does_not_require_if_match(mock_unlock):
    """/unlock matches /archive pattern — idempotent flag flip, no
    baseline-refresh dance required. A request without If-Match must
    not 428."""
    unlocked = _entity_stub()
    mock_unlock.return_value = unlocked
    client = _make_client()
    resp = client.post(f"/v1/knowledge/entities/{_ENTITY_ID}/unlock")
    assert resp.status_code == 200


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
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
    return_value=None,  # C17: skip collision pre-check + alias-map writes
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_happy(mock_merge, mock_get_entity):
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
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
    return_value=None,  # C17: skip collision pre-check + alias-map writes
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_same_entity_400(mock_merge, mock_get_entity):
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
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
    return_value=None,  # C17: skip collision pre-check + alias-map writes
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_not_found_404(mock_merge, mock_get_entity):
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
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
    return_value=None,  # C17: skip collision pre-check + alias-map writes
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_archived_409(mock_merge, mock_get_entity):
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
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
    return_value=None,  # C17: skip collision pre-check + alias-map writes
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_glossary_conflict_409(mock_merge, mock_get_entity):
    mock_merge.side_effect = MergeEntitiesError(
        "glossary_conflict", "distinct glossary anchors"
    )
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "glossary_conflict"


# ── C17 alias-map writes + collision pre-check ─────────────────────


def _source_stub_with_aliases(aliases: list[str], canonical_name: str = "kai") -> Entity:
    """Source entity stub for C17 tests — has aliases populated so the
    router's post-merge alias-map writes have something to record."""
    return Entity(
        id=_ENTITY_ID,
        user_id=str(_TEST_USER),
        project_id=None,
        name=aliases[0] if aliases else "Kai",
        canonical_name=canonical_name,
        kind="character",
        aliases=aliases,
        canonical_version=1,
        source_types=["chat_turn"],
        confidence=0.9,
        mention_count=5,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@patch(
    "app.routers.public.entities.run_read",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_writes_alias_map_rows_post_merge(
    mock_merge, mock_get_entity, mock_run_read,
):
    """C17 happy path: source entity has aliases ["Kai", "Master Kai"];
    after surgery, alias-map should record entries for the canonical
    forms PLUS source.canonical_name. Router calls record_merge per
    distinct canonical and repoint_target afterward."""
    from app.deps import get_entity_alias_map_repo
    from app.main import app

    mock_get_entity.return_value = _source_stub_with_aliases(
        aliases=["Kai", "Master Kai"], canonical_name="kai",
    )
    # Collision precheck Cypher returns no row.
    collision_result_mock = MagicMock()
    collision_result_mock.single = AsyncMock(return_value=None)
    mock_run_read.return_value = collision_result_mock

    mock_merge.return_value = _entity_stub(name="Kai (merged)")

    spending_repo = AsyncMock()
    spending_repo.record_merge = AsyncMock()
    spending_repo.repoint_target = AsyncMock(return_value=0)
    app.dependency_overrides[get_entity_alias_map_repo] = lambda: spending_repo

    client = _make_client()
    # _make_client overrides with a generic stub; re-override AFTER.
    app.dependency_overrides[get_entity_alias_map_repo] = lambda: spending_repo

    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    # "Kai" + "Master Kai" both canonicalize to "kai"; canonical_name
    # is also "kai" → set has 1 element.
    assert body["aliases_redirected"] == 1
    spending_repo.record_merge.assert_awaited()
    args = spending_repo.record_merge.await_args.kwargs
    assert args["target_entity_id"] == _OTHER_ENTITY_ID
    assert args["source_entity_id"] == _ENTITY_ID
    assert args["canonical_alias"] == "kai"
    assert args["kind"] == "character"
    # Chain re-point also called (idempotent if no chain).
    spending_repo.repoint_target.assert_awaited_once()


@patch(
    "app.routers.public.entities.run_read",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_collision_precheck_returns_409(
    mock_merge, mock_get_entity, mock_run_read,
):
    """C17: if a source alias names a third live entity in the same
    scope+kind, the router returns 409 alias_collision and does NOT
    call merge_entities (surgery refused)."""
    mock_get_entity.return_value = _source_stub_with_aliases(
        aliases=["Alice"], canonical_name="alice",
    )
    # Collision precheck finds a hit.
    collision_row = MagicMock()
    collision_row.__getitem__.side_effect = lambda k: {
        "id": "third-entity-id",
        "name": "Alice (other)",
        "conflicting_alias": "alice",
    }[k]
    collision_result_mock = MagicMock()
    collision_result_mock.single = AsyncMock(return_value=collision_row)
    mock_run_read.return_value = collision_result_mock

    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 409, resp.json()
    detail = resp.json()["detail"]
    assert detail["error_code"] == "alias_collision"
    assert detail["colliding_entity_id"] == "third-entity-id"
    assert detail["colliding_entity_name"] == "Alice (other)"
    # Surgery NOT attempted.
    mock_merge.assert_not_awaited()


@patch(
    "app.routers.public.entities.run_read",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_forwards_alias_map_repo_dep(
    mock_merge, mock_get_entity, mock_run_read,
):
    """C17 audit-all-callsites lesson: regression-lock that the merge
    endpoint actually receives a SummaryAliasMapRepo via DI. Without
    the dep, post-merge alias-map writes are silently no-ops."""
    from app.deps import get_entity_alias_map_repo
    from app.main import app

    sentinel = AsyncMock(name="EntityAliasMapRepoSentinel")
    sentinel.record_merge = AsyncMock()
    sentinel.repoint_target = AsyncMock(return_value=0)

    mock_get_entity.return_value = _source_stub_with_aliases(
        aliases=["Alice"], canonical_name="alice",
    )
    collision_result_mock = MagicMock()
    collision_result_mock.single = AsyncMock(return_value=None)
    mock_run_read.return_value = collision_result_mock
    mock_merge.return_value = _entity_stub(name="Captain Brave")

    client = _make_client()
    # Override AFTER _make_client (last write wins).
    app.dependency_overrides[get_entity_alias_map_repo] = lambda: sentinel

    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 200
    sentinel.record_merge.assert_awaited()
    sentinel.repoint_target.assert_awaited_once()


# ── C17 review-impl regression locks ───────────────────────────────


@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_self_merge_returns_400_same_entity_pre_precheck():
    """C17 review-impl HIGH-1: /entities/X/merge-into/X must surface
    400 same_entity, NOT 409 alias_collision. The collision precheck
    excludes only ``e.id <> source AND e.id <> target`` which
    collapses to a single exclusion under self-merge — sibling
    entities sharing canonical_name would falsely trip the precheck.
    Early-exit on entity_id == other_id is the fix."""
    client = _make_client()
    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_ENTITY_ID}",
    )
    assert resp.status_code == 400, resp.json()
    assert resp.json()["detail"]["error_code"] == "same_entity"


@patch(
    "app.routers.public.entities.run_read",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_postgres_writes_failure_returns_200_with_partial_count(
    mock_merge, mock_get_entity, mock_run_read,
):
    """C17 review-impl HIGH-2: a transient Postgres failure during
    alias-map writes must NOT surface as 500 — the Neo4j merge is
    committed, source is gone, the user retrying would 404. Wrap
    in try/except per ADR §5.4 best-effort: log + return 200 with
    partial aliases_redirected count. Ops can backfill via the
    one-shot script."""
    from app.deps import get_entity_alias_map_repo
    from app.main import app

    mock_get_entity.return_value = _source_stub_with_aliases(
        aliases=["Alice", "Lex"], canonical_name="alice",
    )
    collision_result_mock = MagicMock()
    collision_result_mock.single = AsyncMock(return_value=None)
    mock_run_read.return_value = collision_result_mock
    mock_merge.return_value = _entity_stub(name="Captain Brave")

    failing_repo = AsyncMock()
    failing_repo.record_merge = AsyncMock(side_effect=[
        None,
        RuntimeError("pool exhausted"),
    ])
    failing_repo.repoint_target = AsyncMock(return_value=0)

    client = _make_client()
    app.dependency_overrides[get_entity_alias_map_repo] = lambda: failing_repo

    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["aliases_redirected"] == 1
    assert failing_repo.record_merge.await_count == 2


@patch(
    "app.routers.public.entities.run_read",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.get_entity",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.entities.merge_entities",
    new_callable=AsyncMock,
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_merge_entity_repoint_target_failure_swallowed(
    mock_merge, mock_get_entity, mock_run_read,
):
    """C17 review-impl HIGH-2 sibling: repoint_target failure is
    also best-effort — chain consistency is recoverable via backfill,
    but the user-facing merge response stays 200."""
    from app.deps import get_entity_alias_map_repo
    from app.main import app

    mock_get_entity.return_value = _source_stub_with_aliases(
        aliases=["Alice"], canonical_name="alice",
    )
    collision_result_mock = MagicMock()
    collision_result_mock.single = AsyncMock(return_value=None)
    mock_run_read.return_value = collision_result_mock
    mock_merge.return_value = _entity_stub(name="Captain Brave")

    repo = AsyncMock()
    repo.record_merge = AsyncMock()
    repo.repoint_target = AsyncMock(side_effect=RuntimeError("pool gone"))

    client = _make_client()
    app.dependency_overrides[get_entity_alias_map_repo] = lambda: repo

    resp = client.post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/merge-into/{_OTHER_ENTITY_ID}",
    )
    assert resp.status_code == 200, resp.json()
    repo.repoint_target.assert_awaited_once()
