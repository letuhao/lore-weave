"""LOOM T3.5 — style & voice router tests (TestClient + overrides)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CompositionWork, StyleProfile, VoiceProfile

USER = uuid.uuid4()
BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
SCENE = uuid.uuid4()
ENTITY = uuid.uuid4()


def _work() -> CompositionWork:
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK,
                           id=uuid.uuid4(), version=1, status="active")


class StubWorks:
    def __init__(self, work=None):
        self.work = work

    async def get(self, project_id):
        return self.work


class StubStyle:
    def __init__(self):
        self.upserted = []
        self.deleted = []

    async def list_all(self, project_id):
        return [StyleProfile(created_by=USER, project_id=PROJECT, scope_type="work",
                             scope_id=PROJECT, density=40, pace=60)]

    async def upsert(self, project_id, scope_type, scope_id, density, pace, *, created_by=None):
        self.upserted.append((scope_type, scope_id, density, pace))
        return StyleProfile(created_by=USER, project_id=PROJECT, scope_type=scope_type,
                            scope_id=scope_id, density=density, pace=pace)

    async def delete(self, project_id, scope_type, scope_id):
        self.deleted.append((scope_type, scope_id))
        return True


class StubVoice:
    def __init__(self):
        self.upserted = []
        self.deleted = []

    async def list_all(self, project_id):
        return [VoiceProfile(created_by=USER, project_id=PROJECT, entity_id=ENTITY,
                             entity_name="Kael", tags=["terse"])]

    async def upsert(self, project_id, entity_id, entity_name, tags, *, created_by=None):
        self.upserted.append((entity_id, entity_name, tags))
        return VoiceProfile(created_by=USER, project_id=PROJECT, entity_id=entity_id,
                            entity_name=entity_name, tags=tags)

    async def delete(self, project_id, entity_id):
        self.deleted.append(entity_id)
        return True


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import (
        get_grant_client_dep,
        get_style_profile_repo,
        get_voice_profile_repo,
        get_works_repo,
    )
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # E0 book-grant authority stubbed at OWNER; _gate_work resolves the Work's
    # book then gates VIEW/EDIT (deny paths covered in test_grant_gate).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, style, voice = StubWorks(_work()), StubStyle(), StubVoice()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_style_profile_repo] = lambda: style
    app.dependency_overrides[get_voice_profile_repo] = lambda: voice
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, works, style, voice
    app.dependency_overrides.clear()


# ── style ──

def test_list_style_profiles(ctx):
    client, _, _, _ = ctx
    r = client.get(f"/v1/composition/works/{PROJECT}/style-profiles")
    assert r.status_code == 200
    assert r.json()["items"][0]["density"] == 40


def test_put_style_profile(ctx):
    client, _, style, _ = ctx
    r = client.put(
        f"/v1/composition/works/{PROJECT}/style-profile",
        json={"scope_type": "scene", "scope_id": str(SCENE), "density": 80, "pace": 20},
    )
    assert r.status_code == 200
    assert style.upserted == [("scene", SCENE, 80, 20)]


def test_put_style_rejects_out_of_range(ctx):
    client, _, style, _ = ctx
    r = client.put(
        f"/v1/composition/works/{PROJECT}/style-profile",
        json={"scope_type": "scene", "scope_id": str(SCENE), "density": 200, "pace": 20},
    )
    assert r.status_code == 422
    assert style.upserted == []


def test_put_style_rejects_bad_scope(ctx):
    client, _, _, _ = ctx
    r = client.put(
        f"/v1/composition/works/{PROJECT}/style-profile",
        json={"scope_type": "galaxy", "scope_id": str(SCENE), "density": 50, "pace": 20},
    )
    assert r.status_code == 422


def test_delete_style_profile(ctx):
    client, _, style, _ = ctx
    r = client.delete(
        f"/v1/composition/works/{PROJECT}/style-profile",
        params={"scope_type": "scene", "scope_id": str(SCENE)},
    )
    assert r.status_code == 200 and r.json() == {"removed": True}
    assert style.deleted == [("scene", SCENE)]


def test_style_404_on_unknown_work(ctx):
    client, works, style, _ = ctx
    works.work = None
    r = client.put(
        f"/v1/composition/works/{PROJECT}/style-profile",
        json={"scope_type": "work", "scope_id": str(PROJECT), "density": 50, "pace": 50},
    )
    assert r.status_code == 404
    assert style.upserted == []


# ── voice ──

def test_list_voice_profiles(ctx):
    client, _, _, _ = ctx
    r = client.get(f"/v1/composition/works/{PROJECT}/voice-profiles")
    assert r.status_code == 200
    assert r.json()["items"][0]["entity_name"] == "Kael"


def test_put_voice_profile(ctx):
    client, _, _, voice = ctx
    r = client.put(
        f"/v1/composition/works/{PROJECT}/voice-profiles",
        json={"entity_id": str(ENTITY), "entity_name": "Kael",
              "tags": ["terse", "understatement"]},
    )
    assert r.status_code == 200
    assert voice.upserted == [(ENTITY, "Kael", ["terse", "understatement"])]


def test_put_voice_rejects_too_many_tags(ctx):
    client, _, _, voice = ctx
    r = client.put(
        f"/v1/composition/works/{PROJECT}/voice-profiles",
        json={"entity_id": str(ENTITY), "entity_name": "Kael",
              "tags": [f"t{i}" for i in range(21)]},
    )
    assert r.status_code == 422
    assert voice.upserted == []


def test_delete_voice_profile(ctx):
    client, _, _, voice = ctx
    r = client.delete(f"/v1/composition/works/{PROJECT}/voice-profiles/{ENTITY}")
    assert r.status_code == 200 and r.json() == {"removed": True}
    assert voice.deleted == [ENTITY]


def test_voice_404_on_unknown_work(ctx):
    client, works, _, voice = ctx
    works.work = None
    r = client.put(
        f"/v1/composition/works/{PROJECT}/voice-profiles",
        json={"entity_id": str(ENTITY), "entity_name": "Kael", "tags": []},
    )
    assert r.status_code == 404
    assert voice.upserted == []
