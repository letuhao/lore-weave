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
import time
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
    # spec 25: CompositionWork renamed user_id -> created_by (a plain actor stamp).
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK, id=PROJECT)


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


def _decompile_token(user=USER, *, ttl=600, now=None) -> str:
    # close-21-28 P-O2a — the arc-decompiler confirm token (book-scoped, deterministic effect).
    payload = {"book_id": str(BOOK), "chapters_per_arc": 10}
    return mint_confirm_token(
        settings.confirm_token_signing_secret, user, BOOK, "composition.decompile",
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
        # spec 25: WorksRepo.get is bare project-id (get(project_id), no owner arg);
        # access is decided at the confirm route's grant gate, not by an owner filter.
        works.get = AsyncMock(side_effect=lambda p: _work() if p == PROJECT else None)

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
    internal token (the BFF never injects one for /v1/composition/*).

    `exp`/`iat` are REQUIRED: the shared verifier (loreweave_authn) enforces a
    present, unexpired `exp` — a token without it reads as invalid (→ None on
    the optional dependency), so the JWT identity path would silently drop."""
    now = int(time.time())
    tok = jwt.encode(
        {"sub": str(user), "iat": now, "exp": now + 3600},
        settings.jwt_secret,
        algorithm="HS256",
    )
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


def test_confirm_executes_decompile(client, monkeypatch):
    """close-21-28 P-O2a — a confirmed decompile token re-checks the book EDIT grant, then runs the
    deterministic engine and returns its counts. The engine is patched (its DB effect has its own
    integration test); this pins the confirm-spine wiring: descriptor → grant re-check → engine."""
    fake = AsyncMock(return_value={"arcs": 3, "chapters_assigned": 28, "arc_ids": ["a", "b", "c"]})
    monkeypatch.setattr("app.engine.arc_decompile.decompile_arcs", fake)

    resp = _confirm(client, _decompile_token())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"] == "action_accepted"
    assert body["descriptor"] == "composition.decompile"
    assert body["arcs"] == 3 and body["chapters_assigned"] == 28
    fake.assert_awaited_once()
    # the engine was called with the book_id from the token payload + EDIT-scoped caller
    assert fake.await_args.args[1] == BOOK  # decompile_arcs(pool, book_id, ...)


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


# ── D-AGENT-MODE §20 authoring-run confirm effects (book-scoped, no Work) ──────
# Unlike publish/generate (Work/project_id-scoped), these 5 descriptors are
# BOOK-scoped — the dispatch resolves `book_id` directly from the payload and
# re-checks EDIT there (the `client` fixture's `grant.resolve_grant` already
# stubs EDIT unconditionally). `get_authoring_run_service` is a plain function
# the effects import with a DEFERRED `from app.deps import ...` — not a
# FastAPI Depends — so it's exercised via `patch("app.deps.get_authoring_run_service", ...)`
# rather than `app.dependency_overrides`.

RUN = uuid.uuid4()
PLAN_RUN = uuid.uuid4()


def _authoring_token(descriptor, payload, resource_id, user=USER, ttl=600, now=None) -> str:
    return mint_confirm_token(
        settings.confirm_token_signing_secret, user, resource_id, descriptor, payload,
        ttl=ttl, now=now,
    )


def _authoring_svc(svc):
    """Patch the deferred `from app.deps import get_authoring_run_service`
    import inside each `_execute_authoring_run_*` effect (NOT a FastAPI
    Depends — `app.dependency_overrides` cannot reach it)."""
    return patch("app.deps.get_authoring_run_service", AsyncMock(return_value=svc))


@pytest.fixture
def authoring_svc():
    from decimal import Decimal

    from app.db.models import AuthoringRun

    svc = AsyncMock()
    # spec 25: the run-scoped confirm effects (gate/start/resume/revert_all) now
    # re-resolve the run BARE-ID and fence it against the confirm-gated book +
    # creator (`_authoring_run_in_book` → `svc.get`). Default `get` to the
    # caller's OWN run in BOOK so those effects proceed; the cross-book/foreign-
    # creator IDOR refusals are covered in test_authoring_run_tenancy.py. (create
    # has no run_id, so it never calls `get`.)
    svc.get = AsyncMock(return_value=AuthoringRun(
        run_id=RUN, created_by=USER, book_id=BOOK, plan_run_id=PLAN_RUN, level=3,
        scope=[str(CHAPTER)], budget_usd=Decimal("2.00"),
        tool_allowlist=["composition_write_prose"], status="gated",
    ))
    yield svc


def test_confirm_executes_authoring_run_create(client, authoring_svc):
    from app.db.models import AuthoringRun
    from decimal import Decimal

    run = AuthoringRun(
        run_id=RUN, created_by=USER, book_id=BOOK, plan_run_id=PLAN_RUN,
        level=3, scope=[str(CHAPTER)], budget_usd=Decimal("2.00"),
        tool_allowlist=["composition_write_prose"], pause_after_each_unit=True,
    )
    authoring_svc.create = AsyncMock(return_value=run)
    token = _authoring_token(
        "composition.authoring_run_create",
        {
            "book_id": str(BOOK), "plan_run_id": str(PLAN_RUN), "scope": [str(CHAPTER)],
            "level": 3, "budget_usd": "2.00", "tool_allowlist": ["composition_write_prose"],
            "pause_after_each_unit": True, "params": {},
        },
        BOOK,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"] == "action_done"
    assert body["run"]["run_id"] == str(RUN)
    assert body["run"]["pause_after_each_unit"] is True
    authoring_svc.create.assert_awaited_once()
    _, kwargs = authoring_svc.create.await_args
    assert kwargs["pause_after_each_unit"] is True
    assert kwargs["budget_usd"] == Decimal("2.00")


def test_confirm_authoring_run_create_does_not_itself_validate_tool_allowlist(client, authoring_svc):
    """Characterization test (/review-impl, 2026-07-05): the confirm-effect's
    `tool_allowlist` handling is `isinstance(..., list)` only — NOT a re-check
    against `ALLOWLISTABLE_TOOLS`. This is intentional, not a gap: `create()`
    itself has always been "deliberately permissive — ALL semantic validation
    happens at gate()" (authoring_run_service.py), and gate() DOES enforce the
    closed set (test_gate_rejects_non_allowlistable_tool_name in
    test_authoring_runs_service.py). The schema-level Literal[] on both
    `_AuthoringRunCreateArgs` and `AuthoringRunCreate` is the front-line guard
    for the two REAL entry points; this test locks in that the confirm-effect's
    permissiveness is a deliberate belt via a proven backstop, not a bypass —
    if `create()` ever starts validating here too, this test should be updated,
    not deleted (a second validation site is fine; a REMOVED one isn't)."""
    from app.db.models import AuthoringRun
    from decimal import Decimal

    run = AuthoringRun(
        run_id=RUN, created_by=USER, book_id=BOOK, plan_run_id=PLAN_RUN,
        level=3, scope=[str(CHAPTER)], budget_usd=Decimal("2.00"),
        tool_allowlist=["not_a_real_tool"], pause_after_each_unit=True,
    )
    authoring_svc.create = AsyncMock(return_value=run)
    token = _authoring_token(
        "composition.authoring_run_create",
        {
            "book_id": str(BOOK), "plan_run_id": str(PLAN_RUN), "scope": [str(CHAPTER)],
            "level": 3, "budget_usd": "2.00", "tool_allowlist": ["not_a_real_tool"],
            "pause_after_each_unit": True, "params": {},
        },
        BOOK,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 200, resp.text
    authoring_svc.create.assert_awaited_once()
    _, kwargs = authoring_svc.create.await_args
    assert kwargs["tool_allowlist"] == ["not_a_real_tool"]


def test_confirm_authoring_run_create_missing_budget_usd_400(client, authoring_svc):
    token = _authoring_token(
        "composition.authoring_run_create",
        {"book_id": str(BOOK), "plan_run_id": str(PLAN_RUN),
         "pause_after_each_unit": True},  # no budget_usd
        BOOK,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 400
    authoring_svc.create.assert_not_awaited()


def test_confirm_executes_authoring_run_gate(client, authoring_svc):
    from app.db.models import AuthoringRun
    from decimal import Decimal

    gated = AuthoringRun(
        run_id=RUN, created_by=USER, book_id=BOOK, plan_run_id=PLAN_RUN,
        level=3, scope=[str(CHAPTER)], budget_usd=Decimal("2.00"),
        tool_allowlist=["composition_write_prose"], status="gated",
    )
    authoring_svc.gate = AsyncMock(return_value=gated)
    client._book.list_chapters = AsyncMock(
        return_value=[{"chapter_id": str(CHAPTER), "title": "", "sort_order": 1}],
    )
    token = _authoring_token(
        "composition.authoring_run_gate", {"book_id": str(BOOK), "run_id": str(RUN)}, RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 200, resp.text
    assert resp.json()["run"]["status"] == "gated"
    authoring_svc.gate.assert_awaited_once()
    _, kwargs = authoring_svc.gate.await_args
    assert kwargs["book_chapter_ids"] == {str(CHAPTER)}


def test_confirm_authoring_run_gate_active_run_overlap_409(client, authoring_svc):
    from app.services.authoring_run_service import ActiveRunOverlapError

    authoring_svc.gate = AsyncMock(side_effect=ActiveRunOverlapError("active"))
    client._book.list_chapters = AsyncMock(return_value=[])
    token = _authoring_token(
        "composition.authoring_run_gate", {"book_id": str(BOOK), "run_id": str(RUN)}, RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 409
    assert resp.json()["detail"]["reason"] == "active_run_overlap"


def test_confirm_executes_authoring_run_start_with_pause_override(client, authoring_svc):
    from app.db.models import AuthoringRun
    from decimal import Decimal

    running = AuthoringRun(
        run_id=RUN, created_by=USER, book_id=BOOK, plan_run_id=PLAN_RUN,
        level=3, scope=[str(CHAPTER)], budget_usd=Decimal("2.00"),
        tool_allowlist=["composition_write_prose"], status="running",
    )
    authoring_svc.set_pause_policy = AsyncMock(return_value=running)
    authoring_svc.start = AsyncMock(return_value=running)
    token = _authoring_token(
        "composition.authoring_run_start",
        {"book_id": str(BOOK), "run_id": str(RUN), "pause_after_each_unit": False},
        RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 200, resp.text
    assert resp.json()["run"]["status"] == "running"
    authoring_svc.set_pause_policy.assert_awaited_once_with(RUN, False)  # spec 25: bare-id
    authoring_svc.start.assert_awaited_once_with(RUN)


def test_confirm_executes_authoring_run_start_without_override_skips_policy_call(client, authoring_svc):
    from app.db.models import AuthoringRun
    from decimal import Decimal

    running = AuthoringRun(
        run_id=RUN, created_by=USER, book_id=BOOK, plan_run_id=PLAN_RUN,
        level=3, scope=[str(CHAPTER)], budget_usd=Decimal("2.00"), tool_allowlist=["composition_write_prose"],
        status="running",
    )
    authoring_svc.start = AsyncMock(return_value=running)
    token = _authoring_token(
        "composition.authoring_run_start", {"book_id": str(BOOK), "run_id": str(RUN)}, RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 200, resp.text
    authoring_svc.set_pause_policy.assert_not_awaited()
    authoring_svc.start.assert_awaited_once_with(RUN)


def test_confirm_executes_authoring_run_resume(client, authoring_svc):
    from app.db.models import AuthoringRun
    from decimal import Decimal

    running = AuthoringRun(
        run_id=RUN, created_by=USER, book_id=BOOK, plan_run_id=PLAN_RUN,
        level=3, scope=[str(CHAPTER)], budget_usd=Decimal("2.00"), tool_allowlist=["composition_write_prose"],
        status="running",
    )
    authoring_svc.resume = AsyncMock(return_value=running)
    token = _authoring_token(
        "composition.authoring_run_resume", {"book_id": str(BOOK), "run_id": str(RUN)}, RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 200, resp.text
    authoring_svc.resume.assert_awaited_once_with(RUN)


def test_confirm_executes_authoring_run_revert_all_full_success(client, authoring_svc):
    authoring_svc.revert_all = AsyncMock(return_value={
        "reverted_unit_indexes": [1, 0], "failed_unit_index": None,
        "error": None, "run_status": "closed", "closed": True,
    })
    token = _authoring_token(
        "composition.authoring_run_revert_all", {"book_id": str(BOOK), "run_id": str(RUN)}, RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcome"] == "action_done"
    assert body["reverted_unit_indexes"] == [1, 0]
    assert body["closed"] is True


def test_confirm_authoring_run_revert_all_partial_failure_502(client, authoring_svc):
    authoring_svc.revert_all = AsyncMock(return_value={
        "reverted_unit_indexes": [1], "failed_unit_index": 0,
        "error": "book-service 502", "run_status": "report_ready", "closed": False,
    })
    token = _authoring_token(
        "composition.authoring_run_revert_all", {"book_id": str(BOOK), "run_id": str(RUN)}, RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["reason"] == "revert_all_partial"
    assert detail["failed_unit_index"] == 0


def test_confirm_authoring_run_denied_without_edit_grant(client, authoring_svc):
    """A grant revoked between propose and confirm stops the write (re-checked
    at confirm time, same as the Work-scoped descriptors)."""
    from app.grant_client import GrantLevel as _GL
    from app.main import app
    from app import deps

    client_grant = AsyncMock()
    client_grant.resolve_grant = AsyncMock(return_value=_GL.VIEW)
    app.dependency_overrides[deps.get_grant_client_dep] = lambda: client_grant
    token = _authoring_token(
        "composition.authoring_run_gate", {"book_id": str(BOOK), "run_id": str(RUN)}, RUN,
    )
    with _authoring_svc(authoring_svc):
        resp = _confirm(client, token)
    assert resp.status_code == 403
    authoring_svc.gate.assert_not_awaited()
