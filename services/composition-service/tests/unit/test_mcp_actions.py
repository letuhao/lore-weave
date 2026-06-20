"""S-COMPOSE — Tier-W confirm-token route tests (MCP fan-out 2026-06-20).

The propose tool (`composition_publish`) mints a confirm token; these routes are
the ONLY write path. Proves the C-CONFIRM / INV-9 spine end-to-end:

  - mint → confirm EXECUTES the bound publish (book-service `publish_chapter` called);
  - an EXPIRED token is refused (410 token_expired);
  - a FORGED / malformed token is refused (400 action_error);
  - a token minted for user A cannot be confirmed as user B (anti-impersonation);
  - confirm re-checks the publish-gate (a no-longer-publishable chapter → 409).

Uses FastAPI TestClient + dependency_overrides — the SAME stub pattern as the
other composition router tests. The MCP `/mcp` mount + its session manager are
stubbed so this REST test does not consume the once-per-instance `.run()`.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from loreweave_mcp import mint_confirm_token
from app.config import settings
from app.db.models import CompositionWork
from app.grant_client import GrantLevel

USER = uuid.uuid4()
OTHER = uuid.uuid4()
BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
CHAPTER = uuid.uuid4()
GOOD_TOKEN = "test_token"  # tests/conftest.py INTERNAL_SERVICE_TOKEN


def _work() -> CompositionWork:
    return CompositionWork(project_id=PROJECT, user_id=USER, book_id=BOOK, id=PROJECT, version=1)


def _publish_token(user=USER, *, ttl=600, now=None) -> str:
    payload = {"project_id": str(PROJECT), "chapter_id": str(CHAPTER), "book_id": str(BOOK)}
    # Key-split: the confirm path verifies with the DEDICATED signing secret.
    return mint_confirm_token(
        settings.confirm_token_signing_secret, user, CHAPTER, "composition.publish",
        payload, ttl=ttl, now=now,
    )


@pytest.fixture
def client():
    """TestClient with DB pool, grant, book client, repos + the /mcp session
    manager stubbed (so the REST lifespan doesn't consume mcp.run())."""
    @asynccontextmanager
    async def _noop_session_manager():
        yield

    _mcp_stub = MagicMock()
    _mcp_stub.session_manager.run = _noop_session_manager

    spy_pool = AsyncMock()

    with (
        patch("app.db.pool.create_pool", new_callable=AsyncMock),
        patch("app.db.pool.close_pool", new_callable=AsyncMock),
        patch("app.db.pool.get_pool", return_value=spy_pool),
        patch("app.main.run_migrations", new_callable=AsyncMock),
        patch("app.main.mcp_server", _mcp_stub),
        patch("app.main.get_grant_client", MagicMock()),
    ):
        # Disable the redis revoke-consumer + reaper paths in lifespan.
        settings.redis_url = ""
        settings.job_reaper_sweep_secs = 0
        from app.main import app
        from app import deps
        from app.routers import actions as actions_router

        # Stub the repos + book client the confirm route depends on.
        works = AsyncMock()
        works.get = AsyncMock(side_effect=lambda u, p: _work() if u == USER else None)

        outline = AsyncMock()
        outline.chapter_scene_gate = AsyncMock(
            return_value={"can_publish": True, "scenes_total": 1, "scenes_done": 1}
        )

        book = AsyncMock()
        book.publish_chapter = AsyncMock(
            return_value={"chapter_id": str(CHAPTER), "editorial_status": "published"}
        )

        grant = AsyncMock()
        grant.resolve_grant = AsyncMock(return_value=GrantLevel.EDIT)

        app.dependency_overrides[deps.get_works_repo] = lambda: works
        app.dependency_overrides[deps.get_outline_repo] = lambda: outline
        app.dependency_overrides[deps.get_book_client_dep] = lambda: book
        app.dependency_overrides[deps.get_grant_client_dep] = lambda: grant

        with TestClient(app, raise_server_exceptions=True) as c:
            c._book = book  # expose for assertions
            c._outline = outline
            yield c
        app.dependency_overrides.clear()


def _confirm(client, token, *, user=USER):
    return client.post(
        "/v1/composition/actions/confirm",
        params={"token": token},
        headers={"X-Internal-Token": GOOD_TOKEN, "X-User-Id": str(user)},
    )


# ── happy path: mint → confirm executes ───────────────────────────────────────


def test_confirm_executes_publish(client):
    resp = _confirm(client, _publish_token())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"] == "action_done"
    assert body["chapter_id"] == str(CHAPTER)
    client._book.publish_chapter.assert_awaited_once()


def test_preview_describes_without_writing(client):
    resp = client.get(
        "/v1/composition/actions/preview",
        params={"token": _publish_token()},
        headers={"X-Internal-Token": GOOD_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["descriptor"] == "composition.publish"
    assert body["resource_id"] == str(CHAPTER)
    client._book.publish_chapter.assert_not_awaited()


# ── refusals ──────────────────────────────────────────────────────────────────


def test_expired_token_refused(client):
    # Minted in the past so exp is already behind us.
    token = _publish_token(now=1_000)
    resp = _confirm(client, token)
    assert resp.status_code == 410
    assert resp.json()["detail"]["code"] == "token_expired"
    client._book.publish_chapter.assert_not_awaited()


def test_forged_token_refused(client):
    # A token signed with the WRONG secret → signature mismatch → invalid.
    forged = mint_confirm_token(
        "WRONG_SECRET", USER, CHAPTER, "composition.publish",
        {"project_id": str(PROJECT), "chapter_id": str(CHAPTER)},
    )
    resp = _confirm(client, forged)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "action_error"
    client._book.publish_chapter.assert_not_awaited()


def test_malformed_token_refused(client):
    resp = _confirm(client, "not.a.real.token")
    assert resp.status_code == 400
    client._book.publish_chapter.assert_not_awaited()


def test_token_for_other_user_refused(client):
    """A token minted for USER cannot be confirmed by OTHER (anti-impersonation)."""
    token = _publish_token(user=USER)
    resp = _confirm(client, token, user=OTHER)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "action_error"
    client._book.publish_chapter.assert_not_awaited()


def test_confirm_requires_internal_token(client):
    resp = client.post(
        "/v1/composition/actions/confirm",
        params={"token": _publish_token()},
        headers={"X-User-Id": str(USER)},  # no X-Internal-Token
    )
    assert resp.status_code == 401


def test_confirm_re_checks_publish_gate(client):
    """A chapter that became un-publishable between propose and confirm → 409."""
    client._outline.chapter_scene_gate = AsyncMock(
        return_value={"can_publish": False, "scenes_total": 2, "scenes_done": 1}
    )
    resp = _confirm(client, _publish_token())
    assert resp.status_code == 409
    client._book.publish_chapter.assert_not_awaited()
