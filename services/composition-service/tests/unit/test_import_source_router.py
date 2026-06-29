"""W9 — import_source router tests (TestClient + dependency overrides).

CRUD + owner-only IDOR (§12.6): a foreign id is the uniform H13 404 (no oracle); there is
NO public/visibility path. House style mirrors tests/unit/test_references_router.py.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import ImportSource

USER = uuid.uuid4()


def _src(**kw) -> ImportSource:
    return ImportSource(
        id=kw.get("id", uuid.uuid4()),
        owner_user_id=kw.get("owner_user_id", USER),
        project_id=kw.get("project_id", None),
        title=kw.get("title", "Admired Work"),
        content=kw.get("content", "chapter one ..."),
    )


class StubImportRepo:
    """Owner-scoped fake: a foreign id is simply not found (the repo's owner filter)."""

    def __init__(self, *, rows=None, get_hit=True, delete_ok=True):
        self._rows = rows if rows is not None else [_src()]
        self._get_hit = get_hit
        self._delete_ok = delete_ok
        self.created: list[dict] = []

    async def create(self, user_id, *, content, title="", project_id=None):
        self.created.append({"content": content, "title": title, "project_id": project_id,
                             "user_id": user_id})
        return _src(owner_user_id=user_id, content=content, title=title, project_id=project_id)

    async def list_for_owner(self, user_id, *, project_id=None, limit=100):
        return list(self._rows)

    async def get_for_owner(self, user_id, import_source_id):
        return _src(id=import_source_id) if self._get_hit else None

    async def delete_for_owner(self, user_id, import_source_id):
        return self._delete_ok


@pytest.fixture()
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import get_import_source_repo
    from app.middleware.jwt_auth import get_current_user

    state = SimpleNamespace(repo=StubImportRepo())
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_import_source_repo] = lambda: state.repo
    with TestClient(app) as c:
        yield c, state
    app.dependency_overrides.clear()


def test_create_import_source(ctx):
    client, st = ctx
    r = client.post("/v1/composition/import-sources",
                    json={"content": "raw imported chapters", "title": "Admired"})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Admired"
    assert str(body["owner_user_id"]) == str(USER)
    assert st.repo.created[0]["content"] == "raw imported chapters"


def test_create_rejects_empty_content(ctx):
    client, _ = ctx
    r = client.post("/v1/composition/import-sources", json={"content": "", "title": "X"})
    assert r.status_code == 422  # min_length=1


def test_create_rejects_visibility_field_silently_ignored(ctx):
    # there is no visibility field on the model — extra keys are ignored by pydantic,
    # so a caller can never set a public/unlisted import_source (§12.6).
    client, _ = ctx
    r = client.post("/v1/composition/import-sources",
                    json={"content": "x", "visibility": "public"})
    assert r.status_code == 201
    assert "visibility" not in r.json()


def test_list_import_sources(ctx):
    client, _ = ctx
    r = client.get("/v1/composition/import-sources")
    assert r.status_code == 200
    assert len(r.json()["import_sources"]) == 1


def test_get_one_owned(ctx):
    client, _ = ctx
    sid = uuid.uuid4()
    r = client.get(f"/v1/composition/import-sources/{sid}")
    assert r.status_code == 200
    assert r.json()["id"] == str(sid)


def test_get_foreign_id_is_uniform_404(ctx):
    client, st = ctx
    st.repo._get_hit = False  # the owner filter found nothing (foreign/missing)
    r = client.get(f"/v1/composition/import-sources/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "IMPORT_SOURCE_NOT_FOUND"


def test_delete_owned(ctx):
    client, _ = ctx
    sid = uuid.uuid4()
    r = client.delete(f"/v1/composition/import-sources/{sid}")
    assert r.status_code == 200
    assert r.json() == {"id": str(sid), "deleted": True}


def test_delete_foreign_id_is_uniform_404(ctx):
    client, st = ctx
    st.repo._delete_ok = False  # nothing deleted (foreign/missing) → H13
    r = client.delete(f"/v1/composition/import-sources/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "IMPORT_SOURCE_NOT_FOUND"
