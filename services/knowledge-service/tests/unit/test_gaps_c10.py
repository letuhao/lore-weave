"""C10 — unit tests for GET /v1/knowledge/projects/{project_id}/gaps.

The Gap Report endpoint is a THIN pass-through over the existing
``find_gap_candidates()`` repo function (KSA §3.4.E). It surfaces
ENTITY gaps: discovered (unanchored) entities with a high mention
count that the user hasn't added to the glossary yet.

LOCKED (C10-gap-report / Two-distinct-gap-concepts):
  - this is ENTITY gaps via ``find_gap_candidates()`` — NOT
    lore-enrichment's attribute-dimension ``detect-gaps`` (an entity
    missing a ``history`` field). Different query, different service.
  - thin pass-through: ``min_mentions`` + ``limit`` flow straight to
    the repo call. No new gap engine / scoring in the router.
  - JWT user scoping: the caller's ``user_id`` is threaded to the
    repo; the route never accepts a user_id body/query (no spoofing).

Neo4j is mocked; the live proof is the VERIFY-phase Playwright smoke
on the built graph (project 019eb683).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.neo4j_repos.entities import Entity

_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _gap_entity(*, id: str, name: str, mention_count: int) -> Entity:
    """A discovered (unanchored) entity — what find_gap_candidates returns."""
    return Entity(
        id=id,
        user_id=str(_TEST_USER),
        project_id=str(_PROJECT_ID),
        name=name,
        canonical_name=name.lower(),
        kind="character",
        aliases=[name],
        glossary_entity_id=None,  # unanchored ⇒ discovered ⇒ a gap
        anchor_score=0.0,
        mention_count=mention_count,
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _make_client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    client = TestClient(app, raise_server_exceptions=False)
    return client


def _teardown():
    from app.main import app

    app.dependency_overrides.clear()


# ── happy path: returns high-mention/no-glossary candidates ──────────


def test_gaps_returns_candidates():
    """The endpoint returns the discovered, unanchored, high-mention
    entities find_gap_candidates surfaces — each carries status
    `discovered` (the derived gap status)."""
    gaps = [
        _gap_entity(id="e1", name="张若尘", mention_count=420),
        _gap_entity(id="e2", name="林妃", mention_count=88),
    ]
    try:
        with patch(
            "app.routers.public.entities.find_gap_candidates",
            new_callable=AsyncMock,
            return_value=gaps,
        ), patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/gaps")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["total"] == 2
        assert [g["name"] for g in body["gaps"]] == ["张若尘", "林妃"]
        # every gap is a discovered (unanchored) entity
        assert all(g["status"] == "discovered" for g in body["gaps"])
        assert all(g["glossary_entity_id"] is None for g in body["gaps"])
    finally:
        _teardown()


def test_gaps_empty():
    """No candidates ⇒ empty list + total 0 (not a 404)."""
    try:
        with patch(
            "app.routers.public.entities.find_gap_candidates",
            new_callable=AsyncMock,
            return_value=[],
        ), patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/gaps")
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["gaps"] == []
        assert body["total"] == 0
    finally:
        _teardown()


# ── min_mentions + limit pass straight through to the repo ───────────


def test_min_mentions_and_limit_pass_through():
    """`min_mentions` + `limit` query params flow straight to the
    find_gap_candidates call — the THIN pass-through lock. No
    re-filtering in the router."""
    try:
        with patch(
            "app.routers.public.entities.find_gap_candidates",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_find, patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{_PROJECT_ID}/gaps"
                "?min_mentions=120&limit=25"
            )
        assert resp.status_code == 200, resp.json()
        assert mock_find.await_count == 1
        kwargs = mock_find.await_args.kwargs
        assert kwargs["min_mentions"] == 120
        assert kwargs["limit"] == 25
        # user + project scoping threaded from JWT + path (no spoofing)
        assert kwargs["user_id"] == str(_TEST_USER)
        assert kwargs["project_id"] == str(_PROJECT_ID)
        # echoed back so the FE can show the active threshold
        assert resp.json()["min_mentions"] == 120
    finally:
        _teardown()


def test_default_min_mentions_and_limit():
    """Omitting the params uses the documented defaults (50 / 100)."""
    try:
        with patch(
            "app.routers.public.entities.find_gap_candidates",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_find, patch(
            "app.routers.public.entities.neo4j_session",
            new=lambda: _noop_session(),
        ):
            client = _make_client()
            resp = client.get(f"/v1/knowledge/projects/{_PROJECT_ID}/gaps")
        assert resp.status_code == 200
        kwargs = mock_find.await_args.kwargs
        assert kwargs["min_mentions"] == 50
        assert kwargs["limit"] == 100
        assert resp.json()["min_mentions"] == 50
    finally:
        _teardown()


# ── validation: bad params 422 (FastAPI Query bounds) ────────────────


def test_negative_min_mentions_rejected():
    """min_mentions < 0 ⇒ 422 (Query ge=0) — find_gap_candidates is
    never called with a bad value."""
    try:
        with patch(
            "app.routers.public.entities.find_gap_candidates",
            new_callable=AsyncMock,
        ) as mock_find:
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{_PROJECT_ID}/gaps?min_mentions=-1"
            )
        assert resp.status_code == 422
        assert mock_find.await_count == 0
    finally:
        _teardown()


def test_zero_limit_rejected():
    """limit must be >= 1 (Query ge=1) ⇒ 422."""
    try:
        with patch(
            "app.routers.public.entities.find_gap_candidates",
            new_callable=AsyncMock,
        ) as mock_find:
            client = _make_client()
            resp = client.get(
                f"/v1/knowledge/projects/{_PROJECT_ID}/gaps?limit=0"
            )
        assert resp.status_code == 422
        assert mock_find.await_count == 0
    finally:
        _teardown()
