"""D-CHATAI-M1B — the Book-tier model-settings internal route.

Grant-gated cross-tenant read of the OWNER's work.settings, dual-reading the new
model_roles map or the legacy default_model_ref/critic_model_ref scalars. No grant
→ 404 (no oracle); internal-token gated.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import CompositionWork

OWNER, BOOK, CALLER = uuid4(), uuid4(), uuid4()
TOK = {"X-Internal-Token": "test_token"}


class _Grant:
    def __init__(self, owner):
        self._owner = owner

    async def resolve_owner(self, book_id, user_id):
        return self._owner


def _client(owner, settings):
    from app.deps import get_grant_client_dep, get_works_repo
    from app.main import app

    works = AsyncMock()
    rows = (
        [CompositionWork(project_id=uuid4(), created_by=OWNER, book_id=BOOK, version=1, settings=settings)]
        if settings is not None else []
    )
    works.resolve_by_book = AsyncMock(return_value=rows)
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(owner)
    return TestClient(app)


def _teardown():
    from app.main import app
    app.dependency_overrides.clear()


def _url():
    return f"/internal/composition/books/{BOOK}/model-settings?caller_user_id={CALLER}"


def test_requires_internal_token():
    c = _client(OWNER, {})
    try:
        assert c.get(_url()).status_code == 401
    finally:
        _teardown()


def test_no_grant_is_404():
    c = _client(None, {"default_model_ref": "m"})  # resolve_owner → None
    try:
        assert c.get(_url(), headers=TOK).status_code == 404
    finally:
        _teardown()


def test_dual_reads_legacy_scalars():
    c = _client(OWNER, {"default_model_ref": "m-chat", "critic_model_ref": "m-critic"})
    try:
        r = c.get(_url(), headers=TOK)
        assert r.status_code == 200
        roles = r.json()["model_roles"]
        assert roles["chat"] == {"model_ref": "m-chat", "model_source": "user_model"}
        assert roles["critic"] == {"model_ref": "m-critic", "model_source": "user_model"}
    finally:
        _teardown()


def test_new_model_roles_map_wins_over_legacy():
    c = _client(OWNER, {
        "model_roles": {"chat": {"model_ref": "new-chat", "model_source": "user_model"}},
        "default_model_ref": "legacy-chat",
    })
    try:
        roles = c.get(_url(), headers=TOK).json()["model_roles"]
        assert roles["chat"]["model_ref"] == "new-chat"  # map wins, legacy ignored for chat
    finally:
        _teardown()


def test_no_work_rows_yields_empty_roles():
    c = _client(OWNER, None)  # resolve_by_book → []
    try:
        r = c.get(_url(), headers=TOK)
        assert r.status_code == 200 and r.json()["model_roles"] == {}
    finally:
        _teardown()
