"""Phase B sub-session C — relation correction repo + router unit tests.

recreate_relation (F5 resurrect) is mocked at run_write; the router endpoints
are exercised via TestClient with the relation repo mocked. emit_correction is
a best-effort no-op here (no pool in unit tests)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.relations import Relation, recreate_relation

_TEST_USER = uuid4()
_SUBJ = "ent-subj-1"
_OBJ = "ent-obj-1"


def _relation(predicate="ally_of", valid_until=None, rid="rel-1") -> Relation:
    return Relation(
        id=rid,
        user_id=str(_TEST_USER),
        subject_id=_SUBJ,
        object_id=_OBJ,
        predicate=predicate,
        confidence=1.0,
        valid_from=datetime.now(timezone.utc),
        valid_until=valid_until,
        pending_validation=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        subject_name="A", subject_kind="character",
        object_name="B", object_kind="character",
    )


def _make_result(record):
    r = MagicMock()
    r.single = AsyncMock(return_value=record)
    return r


# ── recreate_relation (F5) ──────────────────────────────────────────

def test_recreate_cypher_resurrects_valid_until():
    """F5 regression-lock: the recreate Cypher MUST clear valid_until on ON
    MATCH (resurrect), and it MUST be a DIFFERENT query than create_relation
    (whose ON MATCH never touches valid_until — so extraction can't resurrect)."""
    from app.db.neo4j_repos import relations as m
    assert "r.valid_until = NULL" in m._RECREATE_RELATION_CYPHER
    assert "ON MATCH SET" in m._RECREATE_RELATION_CYPHER
    # create_relation's ON MATCH must NOT clear valid_until (the invariant F5 protects).
    create_on_match = m._CREATE_RELATION_CYPHER.split("ON MATCH SET")[1]
    assert "valid_until" not in create_on_match


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_recreate_relation_builds_edge(mock_run):
    mock_run.return_value = _make_result({
        "rel": {"id": "rel-1", "user_id": str(_TEST_USER), "subject_id": _SUBJ,
                "object_id": _OBJ, "predicate": "enemy_of", "confidence": 1.0,
                "valid_until": None, "pending_validation": False},
        "subj": {"name": "A", "kind": "character"},
        "obj": {"name": "B", "kind": "character"},
    })
    rel = await recreate_relation(
        session=MagicMock(), user_id=str(_TEST_USER),
        subject_id=_SUBJ, predicate="enemy_of", object_id=_OBJ,
    )
    assert rel is not None and rel.predicate == "enemy_of"
    assert rel.valid_until is None


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_recreate_relation_none_when_endpoint_missing(mock_run):
    mock_run.return_value = _make_result(None)
    rel = await recreate_relation(
        session=MagicMock(), user_id=str(_TEST_USER),
        subject_id=_SUBJ, predicate="enemy_of", object_id="missing",
    )
    assert rel is None


# ── router ──────────────────────────────────────────────────────────

@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app, raise_server_exceptions=False)


@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.relations.get_relation", new_callable=AsyncMock)
def test_get_relation_404(mock_get):
    mock_get.return_value = None
    assert _client().get("/v1/knowledge/relations/rel-x").status_code == 404


@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.relations.invalidate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.get_relation", new_callable=AsyncMock)
def test_invalidate_relation_happy(mock_get, mock_invalidate):
    mock_get.return_value = _relation()
    mock_invalidate.return_value = _relation(valid_until=datetime.now(timezone.utc))
    resp = _client().post("/v1/knowledge/relations/rel-1/invalidate")
    assert resp.status_code == 200, resp.json()
    mock_invalidate.assert_awaited_once()


@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.relations.invalidate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.get_relation", new_callable=AsyncMock)
def test_invalidate_relation_404(mock_get, mock_invalidate):
    mock_get.return_value = None
    mock_invalidate.return_value = None
    resp = _client().post("/v1/knowledge/relations/missing/invalidate")
    assert resp.status_code == 404


@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.relations.recreate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.invalidate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.get_relation", new_callable=AsyncMock)
def test_correct_relation_happy(mock_get, mock_invalidate, mock_recreate):
    old = _relation(predicate="ally_of", rid="rel-old")
    new = _relation(predicate="enemy_of", rid="rel-new")
    # get_relation: 1st = before (old), 2nd = after (re-read new)
    mock_get.side_effect = [old, new]
    mock_invalidate.return_value = old
    mock_recreate.return_value = new
    resp = _client().post("/v1/knowledge/relations/correct", json={
        "old_relation_id": "rel-old", "subject_id": _SUBJ,
        "predicate": "enemy_of", "object_id": _OBJ,
    })
    assert resp.status_code == 200, resp.json()
    assert resp.json()["predicate"] == "enemy_of"
    mock_invalidate.assert_awaited_once()
    mock_recreate.assert_awaited_once()


@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.relations.recreate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.invalidate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.get_relation", new_callable=AsyncMock)
def test_correct_relation_old_missing_404(mock_get, mock_invalidate, mock_recreate):
    mock_get.return_value = None  # old not found
    resp = _client().post("/v1/knowledge/relations/correct", json={
        "old_relation_id": "missing", "subject_id": _SUBJ,
        "predicate": "enemy_of", "object_id": _OBJ,
    })
    assert resp.status_code == 404
    mock_recreate.assert_not_awaited()


@patch("app.routers.public.relations.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.relations.recreate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.invalidate_relation", new_callable=AsyncMock)
@patch("app.routers.public.relations.get_relation", new_callable=AsyncMock)
def test_correct_relation_recreate_endpoint_missing_409(mock_get, mock_invalidate, mock_recreate):
    mock_get.return_value = _relation(rid="rel-old")  # old exists
    mock_invalidate.return_value = _relation(rid="rel-old")
    mock_recreate.return_value = None  # endpoint entity missing
    resp = _client().post("/v1/knowledge/relations/correct", json={
        "old_relation_id": "rel-old", "subject_id": _SUBJ,
        "predicate": "enemy_of", "object_id": "missing",
    })
    assert resp.status_code == 409
