"""Phase B C2 — event correction repo (update/archive) + router unit tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.events import Event, archive_event, update_event_fields
from app.db.repositories import VersionMismatchError

_USER = uuid4()
_EID = "evt-1"


def _event_node(*, title="The Oath", version=3, archived_at=None) -> dict:
    return {
        "id": _EID, "user_id": str(_USER), "project_id": "p-1",
        "title": title, "canonical_title": title.lower(),
        "summary": "...", "chapter_id": "ch-1", "event_date_iso": "0184",
        "time_cue": "dawn", "participants": ["Liu"], "confidence": 0.9,
        "source_types": ["book_content"], "evidence_count": 1, "mention_count": 1,
        "archived_at": archived_at, "version": version,
        "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
    }


def _result(record):
    r = MagicMock()
    r.single = AsyncMock(return_value=record)
    return r


# ── repo ────────────────────────────────────────────────────────────

def test_update_event_cypher_captures_before_and_bumps_version():
    from app.db.neo4j_repos import events as m
    # T80 split the OCC path into two statements in one transaction (the FOREACH form was
    # not atomic — see the measurement on `entities._LOCK_AND_READ_ENTITY_CYPHER`). The
    # `before` snapshot still comes from the LOCKED READ, and the new version still comes
    # from the version read under that lock, not from the caller's expected_version.
    assert "AS before" in m._LOCK_AND_READ_EVENT_CYPHER
    assert "SET e.version = coalesce(e.version, 1)" in m._LOCK_AND_READ_EVENT_CYPHER, (
        "the locked read lost its lock-taking write — the transaction alone leaves the race "
        "exactly as it was (measured: 39 of 40 concurrent pairs both apply)"
    )
    assert "e.version = $next_version" in m._APPLY_EVENT_FIELDS_CYPHER
    # merge_event ON CREATE seeds version=1; ON MATCH must NOT bump it (so a
    # user's If-Match baseline survives extraction re-mentions).
    # RESTATED (T73): the branches merged into one SET (§10.1), so "ON MATCH must not touch
    # version" is now "the ONLY assignment to version is a coalesce" — which keeps the
    # stored value on every re-merge and sets 1 only on create. OCC still belongs solely to
    # update_event_fields; a bare `e.version = ...` here would let extraction bump it and
    # silently invalidate an author edit in flight.
    # Assert on the SHAPE without a regex: every `e.version` occurrence must be part of the
    # single coalesce assignment. Two earlier attempts died on escaping (a `[^,]+` that
    # stopped inside coalesce, then a character class whose escape collapsed) — string
    # containment says the same thing and cannot be mis-escaped.
    cy = m._MERGE_EVENT_CYPHER
    assert "coalesce(e.version, 1)" in cy, (
        "merge_event must seed version via coalesce(e.version, 1) — that sets 1 on create "
        "and keeps the stored value on every re-merge"
    )
    assert "current_version" not in cy, (
        "merge_event references the OCC bump — version belongs solely to update_event_fields; "
        "extraction moving it would silently invalidate an author edit in flight"
    )
    assert "e.version          = coalesce(e.version, 1)" in cy or (
        "e.version = coalesce(e.version, 1)" in cy
    ), (
        "merge_event must assign version only as coalesce(e.version, 1); a bare assignment "
        "would let extraction bump it and silently invalidate an author edit in flight"
    )


def _tx_session(records: list):
    """A session whose transaction hands back `records` in order, one per `run`.

    These stay MOCK tests of the control flow. A mock has no lock, which is exactly why the
    race the two-statement form fixes was invisible at this level for as long as it was — the
    property itself is pinned live in `tests/integration/db/test_occ_is_actually_atomic.py`.
    """
    tx = MagicMock()
    tx.run = AsyncMock(side_effect=[_result(r) for r in records])
    tx.commit = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.begin_transaction = AsyncMock(return_value=tx)
    return session, tx


@pytest.mark.asyncio
async def test_update_event_applies_and_returns_before():
    before = {"title": "The Oath", "summary": "...", "time_cue": "dawn",
              "event_date_iso": "0184", "participants": ["Liu"]}
    locked = {"e": _event_node(title="The Oath", version=3), "current_version": 3,
              "before": before}
    post = {"e": _event_node(title="The Sworn Oath", version=4)}
    session, tx = _tx_session([locked, post])
    ev, got = await update_event_fields(
        session=session, user_id=str(_USER), event_id=_EID,
        title="The Sworn Oath", summary=None, time_cue=None, event_date_iso=None,
        expected_version=3,
    )
    assert ev is not None and ev.version == 4
    assert got["title"] == "The Oath"
    assert tx.run.await_args_list[1].kwargs["next_version"] == 4, (
        "the new version must be derived from the version read UNDER THE LOCK"
    )
    tx.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_event_raises_on_version_mismatch():
    locked = {"e": _event_node(version=5), "current_version": 5, "before": None}
    session, tx = _tx_session([locked])
    with pytest.raises(VersionMismatchError):
        await update_event_fields(
            session=session, user_id=str(_USER), event_id=_EID,
            title="X", summary=None, time_cue=None, event_date_iso=None,
            expected_version=3,
        )
    assert tx.run.await_count == 1, "a mismatched version still ran the write"


@pytest.mark.asyncio
async def test_update_event_none_on_missing():
    session, tx = _tx_session([None])
    ev, before = await update_event_fields(
        session=session, user_id=str(_USER), event_id="missing",
        title="X", summary=None, time_cue=None, event_date_iso=None, expected_version=1,
    )
    assert ev is None and before is None
    assert tx.run.await_count == 1


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.events.run_write", new_callable=AsyncMock)
async def test_archive_event(mock_run):
    mock_run.return_value = _result({"e": _event_node(archived_at=datetime.now(timezone.utc))})
    ev = await archive_event(session=MagicMock(), user_id=str(_USER), event_id=_EID)
    assert ev is not None
    mock_run.return_value = _result(None)
    assert await archive_event(session=MagicMock(), user_id=str(_USER), event_id="x") is None


# ── router ──────────────────────────────────────────────────────────

@asynccontextmanager
async def _noop_session():
    yield MagicMock()


# ── create route (D-KG-EVENT-CREATE-ROUTE) ──────────────────────────

@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.events.emit_correction", new_callable=AsyncMock)
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.merge_event", new_callable=AsyncMock)
def test_create_event_happy(mock_merge, mock_emit):
    created = Event(
        id="new-evt", user_id=str(_USER), project_id="p-1", title="The Duel",
        canonical_title="the duel", chapter_id="ch-9", participants=["Liu"],
        version=1, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    mock_merge.return_value = created
    resp = _client().post(
        "/v1/knowledge/events",
        json={"project_id": str(uuid4()), "title": "The Duel",
              "chapter_id": "ch-9", "participants": ["Liu"]},
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["id"] == "new-evt"
    # user-authored provenance + tenancy: written under the JWT user_id.
    kwargs = mock_merge.call_args.kwargs
    assert kwargs["user_id"] == str(_USER)
    assert kwargs["source_type"] == "manual"
    assert kwargs["provenance"] == "human_authored"
    assert kwargs["participants"] == ["Liu"]
    # emits a create correction (op=create, before=null) — no silent write.
    emit_kwargs = mock_emit.call_args.kwargs
    assert emit_kwargs["payload"]["op"] == "create"
    assert emit_kwargs["payload"]["before"] is None


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.merge_event", new_callable=AsyncMock)
def test_create_event_blank_title_422(mock_merge):
    resp = _client().post(
        "/v1/knowledge/events",
        json={"project_id": str(uuid4()), "title": "   "},
    )
    assert resp.status_code == 422
    mock_merge.assert_not_awaited()


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.merge_event", new_callable=AsyncMock)
def test_create_event_missing_project_422(mock_merge):
    resp = _client().post("/v1/knowledge/events", json={"title": "The Duel"})
    assert resp.status_code == 422
    mock_merge.assert_not_awaited()


@pytest.fixture(autouse=True)
def _clear():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _USER
    return TestClient(app, raise_server_exceptions=False)


def _event_model(version=3):
    return Event(
        id=_EID, user_id=str(_USER), title="The Oath", canonical_title="the oath",
        summary="...", event_date_iso="0184", time_cue="dawn", participants=["Liu"],
        version=version, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.update_event_fields", new_callable=AsyncMock)
def test_patch_event_happy(mock_update):
    mock_update.return_value = (_event_model(version=4), {
        "title": "Old", "summary": "...", "time_cue": "dawn",
        "event_date_iso": "0184", "participants": ["Liu"]})
    resp = _client().patch(f"/v1/knowledge/events/{_EID}",
                           json={"title": "The Oath"}, headers={"If-Match": 'W/"3"'})
    assert resp.status_code == 200, resp.json()
    assert resp.headers["ETag"] == 'W/"4"'


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.update_event_fields", new_callable=AsyncMock)
def test_patch_event_missing_if_match_428(mock_update):
    resp = _client().patch(f"/v1/knowledge/events/{_EID}", json={"title": "X"})
    assert resp.status_code == 428
    mock_update.assert_not_awaited()


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.update_event_fields", new_callable=AsyncMock)
def test_patch_event_version_mismatch_412(mock_update):
    mock_update.side_effect = VersionMismatchError(_event_model(version=9))
    resp = _client().patch(f"/v1/knowledge/events/{_EID}",
                           json={"title": "X"}, headers={"If-Match": 'W/"3"'})
    assert resp.status_code == 412
    assert resp.headers["ETag"] == 'W/"9"'


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.update_event_fields", new_callable=AsyncMock)
def test_patch_event_404(mock_update):
    mock_update.return_value = (None, None)
    resp = _client().patch(f"/v1/knowledge/events/{_EID}",
                           json={"title": "X"}, headers={"If-Match": 'W/"3"'})
    assert resp.status_code == 404


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.update_event_fields", new_callable=AsyncMock)
def test_patch_event_empty_body_422(mock_update):
    resp = _client().patch(f"/v1/knowledge/events/{_EID}", json={}, headers={"If-Match": 'W/"3"'})
    assert resp.status_code == 422


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.archive_event", new_callable=AsyncMock)
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.get_event", new_callable=AsyncMock)
def test_archive_event_happy(mock_get, mock_archive):
    mock_get.return_value = _event_model()
    mock_archive.return_value = _event_model()
    resp = _client().delete(f"/v1/knowledge/events/{_EID}")
    assert resp.status_code == 204
    mock_archive.assert_awaited_once()


@patch("app.routers.public.events.neo4j_session", new=lambda: _noop_session())
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.archive_event", new_callable=AsyncMock)
@patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.get_event", new_callable=AsyncMock)
def test_archive_event_404(mock_get, mock_archive):
    mock_get.return_value = None
    mock_archive.return_value = None
    resp = _client().delete(f"/v1/knowledge/events/{_EID}")
    assert resp.status_code == 404
