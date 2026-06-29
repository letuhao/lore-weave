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

import json
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
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
MODEL_REF = uuid.uuid4()
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


class _FakeResp:
    """Stand-in for the engine's JSONResponse — the generate effect reads `.body`."""
    def __init__(self, data: dict):
        self.body = json.dumps(data).encode()


def _generate_token(user=USER, *, target_kind="chapter", target_id=None, ttl=600, now=None) -> str:
    tid = target_id or CHAPTER
    payload = {
        "project_id": str(PROJECT), "book_id": str(BOOK), "target_kind": target_kind,
        "target_id": str(tid), "model_source": "user_model", "model_ref": str(MODEL_REF),
        "operation": None, "guide": "", "max_output_tokens": None, "reasoning": "auto",
    }
    return mint_confirm_token(
        settings.confirm_token_signing_secret, user, tid, "composition.generate",
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
        # D-W2-MCP-SESSION-ISOLATION: app.main does `from app.db.pool import create_pool`,
        # so the lifespan's create_pool is a SEPARATE binding the app.db.pool patch misses —
        # unpatched it connects to the real DB host in a batch (getaddrinfo). Patch app.main.* too.
        patch("app.main.create_pool", new_callable=AsyncMock),
        patch("app.main.close_pool", new_callable=AsyncMock),
        patch("app.main.get_pool", return_value=spy_pool),
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


def _bearer(user=USER) -> dict[str, str]:
    """A valid FE-style Bearer JWT (HS256, `sub`) — the FE path identity, NO
    internal token (the BFF never injects one for /v1/composition/*)."""
    tok = jwt.encode({"sub": str(user)}, settings.jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_billing_job_id_is_a_valid_uuid_deterministic_per_token():
    """Regression: usage-billing's guardrail reserve unmarshals `job_id` as a UUID,
    so the precheck MUST send a UUID — sending `_jti` (a 64-char SHA-256 hex) made
    the reserve 400 → the fail-closed precheck denied EVERY Tier-W spend (402). The
    billing job-id must be a parseable UUID, deterministic per token, distinct across
    tokens — and NOT the raw 64-char jti."""
    from app.routers.actions import _billing_job_id, _jti

    a = _billing_job_id("token-A")
    # a valid UUID (would raise otherwise) + 36-char canonical form
    assert str(uuid.UUID(a)) == a
    # deterministic per token, distinct across tokens
    assert a == _billing_job_id("token-A")
    assert a != _billing_job_id("token-B")
    # the bug: it must NOT be the 64-char hex jti (which is not a UUID)
    assert a != _jti("token-A")
    assert len(_jti("token-A")) == 64


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


# ── FE path: a Bearer JWT is sufficient identity (mirrors glossary) ─────────────


def test_confirm_executes_publish_via_jwt(client):
    """The FE drives confirm with ONLY its user JWT (no internal token / X-User-Id) —
    the confirm token is the capability, the JWT proves who wields it."""
    resp = client.post(
        "/v1/composition/actions/confirm",
        params={"token": _publish_token()},
        headers=_bearer(USER),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["outcome"] == "action_done"
    client._book.publish_chapter.assert_awaited_once()


def test_confirm_jwt_for_other_user_refused(client):
    """A token minted for USER cannot be confirmed by OTHER's JWT (INV-9)."""
    resp = client.post(
        "/v1/composition/actions/confirm",
        params={"token": _publish_token(user=USER)},
        headers=_bearer(OTHER),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "action_error"
    client._book.publish_chapter.assert_not_awaited()


def test_preview_via_jwt(client):
    resp = client.get(
        "/v1/composition/actions/preview",
        params={"token": _publish_token()},
        headers=_bearer(USER),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["descriptor"] == "composition.publish"


def test_preview_jwt_for_other_user_refused(client):
    """A user can't preview someone else's proposal (anti-oracle on the JWT path)."""
    resp = client.get(
        "/v1/composition/actions/preview",
        params={"token": _publish_token(user=USER)},
        headers=_bearer(OTHER),
    )
    assert resp.status_code == 400


def test_confirm_no_jwt_and_no_internal_token_refused(client):
    """Neither identity path → 401 (the internal-token requirement still bites when
    no JWT is present)."""
    resp = client.post(
        "/v1/composition/actions/confirm",
        params={"token": _publish_token()},
        headers={"X-User-Id": str(USER)},  # no JWT, no internal token
    )
    assert resp.status_code == 401


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


# ── composition.generate confirm effect (runs the cowrite engine in-process) ───


def test_confirm_executes_generate_chapter(client):
    """A composition.generate token (chapter) runs the engine's generate_chapter in
    auto/persist mode and surfaces its JSON result under `generation`."""
    fake = {"job_id": str(uuid.uuid4()), "text": "It was a dark night.",
            "persisted": True, "status": "completed", "assembly_mode": "chapter"}
    gen = AsyncMock(return_value=_FakeResp(fake))
    with (
        patch("app.routers.engine.generate_chapter", new=gen),
        patch("app.clients.book_client.get_book_client", MagicMock()),
        patch("app.clients.glossary_client.get_glossary_client", MagicMock()),
        patch("app.clients.knowledge_client.get_knowledge_client", MagicMock()),
        patch("app.clients.llm_client.get_llm_client", MagicMock()),
    ):
        resp = _confirm(client, _generate_token(target_kind="chapter"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"] == "action_done"
    assert body["descriptor"] == "composition.generate"
    assert body["target_kind"] == "chapter"
    assert body["generation"]["text"] == "It was a dark night."
    gen.assert_awaited_once()
    # Persisted single-pass (the chapter target writes the book draft).
    # Signature: generate_chapter(project_id, chapter_id, body, ...) → body is args[2].
    args, kwargs = gen.await_args
    assert args[2].persist is True
    # Regression (HIGH-1): the chapter path reuses this bearer to PERSIST the draft
    # AFTER a multi-minute generation, so it must outlive the 60s immediate-call
    # default — else the draft write 401s on an expired token (silent best-effort loss).
    import jwt as _jwt
    claims = _jwt.decode(kwargs["bearer"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] >= 600


def test_confirm_executes_generate_scene(client):
    """A scene target runs the engine's `generate` in auto mode."""
    scene_id = uuid.uuid4()
    fake = {"job_id": str(uuid.uuid4()), "text": "She turned.", "mode": "auto", "status": "completed"}
    gen = AsyncMock(return_value=_FakeResp(fake))
    with (
        patch("app.routers.engine.generate", new=gen),
        patch("app.clients.book_client.get_book_client", MagicMock()),
        patch("app.clients.glossary_client.get_glossary_client", MagicMock()),
        patch("app.clients.knowledge_client.get_knowledge_client", MagicMock()),
        patch("app.clients.llm_client.get_llm_client", MagicMock()),
    ):
        resp = _confirm(client, _generate_token(target_kind="scene", target_id=scene_id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_kind"] == "scene"
    assert body["generation"]["text"] == "She turned."
    gen.assert_awaited_once()
    # Signature: generate(project_id, body, ...) → body is args[1].
    args, _ = gen.await_args
    assert args[1].mode == "auto"


def test_generate_token_for_other_user_refused(client):
    """A generate token minted for USER cannot be confirmed by OTHER — no engine call."""
    gen = AsyncMock()
    with patch("app.routers.engine.generate_chapter", new=gen):
        resp = _confirm(client, _generate_token(user=USER), user=OTHER)
    assert resp.status_code == 400
    gen.assert_not_awaited()
