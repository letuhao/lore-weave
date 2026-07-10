"""LOOM T3.6 — references router tests (TestClient + dependency overrides)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from app.db.models import CompositionWork, ReferenceSource

USER = uuid.uuid4()
BOOK = uuid.uuid4()
PROJECT = uuid.uuid4()
SCENE = uuid.uuid4()
MODEL_REF = str(uuid.uuid4())


def _work(settings: dict | None = None) -> CompositionWork:
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK,
                           id=uuid.uuid4(), version=1, status="active",
                           settings=settings or {})


def _ref(content="ref body", title="Influence", **kw) -> ReferenceSource:
    return ReferenceSource(id=kw.get("id", uuid.uuid4()), created_by=USER, project_id=PROJECT,
                           title=title, author=kw.get("author", ""), source_url="",
                           content=content, embedding_model="bge-m3", embedding_dim=3)


class StubWorks:
    def __init__(self, work):
        self.work = work
        self.updates = []

    async def get(self, project_id):
        return self.work

    async def update(self, project_id, patch, *, created_by=None, expected_version=None):
        self.updates.append(patch)
        # reflect the settings write-through onto the in-memory work
        if "settings" in patch and self.work is not None:
            self.work = _work(patch["settings"])
        return self.work


class StubRefs:
    def __init__(self, hits=None):
        self.created = []
        self.deleted = []
        self._hits = hits or []
        self.delete_ok = True

    async def create(self, project_id, *, created_by=None, content, embedding, title="",
                     author="", source_url="", embedding_model="", embedding_dim=None):
        self.created.append({"content": content, "embedding": embedding, "title": title,
                             "embedding_model": embedding_model})
        return _ref(content=content, title=title, author=author)

    async def list(self, project_id):
        return [_ref()]

    async def delete(self, project_id, reference_id):
        self.deleted.append(reference_id)
        return self.delete_ok

    async def search(self, project_id, vector, *, limit=8):
        return list(self._hits)


class StubOutline:
    def __init__(self, node=None):
        self.node = node if node is not None else SimpleNamespace(
            project_id=PROJECT, goal="duel on the bridge", synopsis="", beat_role="climax",
            title="The Bridge")

    async def get_node(self, node_id):
        return self.node


class StubPins:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def list_for_scene(self, project_id, node_id):
        return self.rows


class StubEmbedder:
    def __init__(self, result=None, error=None):
        self.result = result or EmbeddingResult(embeddings=[[1.0, 0.0, 0.0]], dimension=3,
                                                model="bge-m3", prompt_tokens=5)
        self.error = error
        self.calls = []

    async def embed(self, *, user_id, model_source, model_ref, texts):
        self.calls.append((model_source, model_ref, texts))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    # The by-id DELETE resolves the reference's scope from the row itself via
    # get_pool().fetchrow (PM-8 scope-bootstrap) before gating — give it a fake
    # pool that returns this project's row.
    class _FakePool:
        async def fetchrow(self, query, *args):
            return {"project_id": PROJECT}
    monkeypatch.setattr("app.routers.references.get_pool", lambda: _FakePool())

    from app.main import app
    from app.deps import (get_embedding_client_dep, get_grant_client_dep,
                          get_grounding_pins_repo, get_outline_repo,
                          get_references_repo, get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # E0 book-grant authority stubbed at OWNER; the references router resolves
    # the Work's book then gates VIEW/EDIT (deny paths in test_grant_gate).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    state = SimpleNamespace(
        works=StubWorks(_work()), refs=StubRefs(), outline=StubOutline(),
        pins=StubPins(), embedder=StubEmbedder())
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: state.works
    app.dependency_overrides[get_references_repo] = lambda: state.refs
    app.dependency_overrides[get_outline_repo] = lambda: state.outline
    app.dependency_overrides[get_grounding_pins_repo] = lambda: state.pins
    app.dependency_overrides[get_embedding_client_dep] = lambda: state.embedder
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, state
    app.dependency_overrides.clear()


def test_list_references_reports_model_unset(ctx):
    client, st = ctx
    r = client.get(f"/v1/composition/works/{PROJECT}/references")
    assert r.status_code == 200
    body = r.json()
    assert body["embed_model_set"] is False  # empty settings
    assert len(body["references"]) == 1


def test_add_first_reference_sets_model_write_through_and_embeds(ctx):
    client, st = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/references",
        json={"content": "a passage to echo", "title": "Dune", "model_ref": MODEL_REF},
    )
    assert r.status_code == 201
    # the embed model was written through to work.settings
    assert st.works.updates and st.works.updates[0]["settings"]["reference_embed_model_ref"] == MODEL_REF
    # the content was embedded + stored
    assert st.embedder.calls[0][1] == MODEL_REF
    assert st.refs.created[0]["content"] == "a passage to echo"


def test_add_reference_422_when_model_unset_and_none_supplied(ctx):
    client, st = ctx
    r = client.post(
        f"/v1/composition/works/{PROJECT}/references",
        json={"content": "no model configured"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "REFERENCE_EMBED_MODEL_UNSET"
    assert st.refs.created == []  # nothing stored


def test_add_reference_uses_stored_model_ignoring_a_differing_request(ctx):
    client, st = ctx
    st.works.work = _work({"reference_embed_model_ref": MODEL_REF,
                           "reference_embed_model_source": "user_model"})
    other = str(uuid.uuid4())
    r = client.post(
        f"/v1/composition/works/{PROJECT}/references",
        json={"content": "x", "model_ref": other},
    )
    assert r.status_code == 201
    # embedded with the STORED model, not the differing request value
    assert st.embedder.calls[0][1] == MODEL_REF
    # no settings rewrite (model already set)
    assert st.works.updates == []


def test_add_reference_502_on_embed_failure(ctx):
    client, st = ctx
    st.works.work = _work({"reference_embed_model_ref": MODEL_REF})
    st.embedder.error = EmbeddingError("provider down", retryable=True)
    r = client.post(f"/v1/composition/works/{PROJECT}/references", json={"content": "x"})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "REFERENCE_EMBED_FAILED"
    assert st.refs.created == []


def test_first_add_with_failing_model_does_NOT_persist_it(ctx):
    # /review-impl MED — a bad/failing model on the FIRST add must not be written to
    # settings (else every later add reuses it → permanent 502, no UI to change it).
    client, st = ctx  # empty settings → model unset
    st.embedder.error = EmbeddingError("bad model", retryable=False)
    r = client.post(
        f"/v1/composition/works/{PROJECT}/references",
        json={"content": "x", "model_ref": MODEL_REF},
    )
    assert r.status_code == 502
    assert st.works.updates == []   # model NOT persisted — the work stays unset/recoverable
    assert st.refs.created == []


def test_delete_reference(ctx):
    client, st = ctx
    rid = uuid.uuid4()
    r = client.delete(f"/v1/composition/references/{rid}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert st.refs.deleted == [rid]


def test_delete_reference_404_when_missing(ctx):
    client, st = ctx
    st.refs.delete_ok = False
    r = client.delete(f"/v1/composition/references/{uuid.uuid4()}")
    assert r.status_code == 404


def test_search_neutral_empty_when_model_unset(ctx):
    client, st = ctx  # empty settings → model unset
    r = client.get(f"/v1/composition/works/{PROJECT}/scenes/{SCENE}/references")
    assert r.status_code == 200
    assert r.json() == {"hits": [], "embed_model_set": False, "query": ""}
    assert st.embedder.calls == []  # never embedded


def test_search_auto_query_from_scene_with_pin_annotation(ctx):
    client, st = ctx
    rid = uuid.uuid4()
    st.works.work = _work({"reference_embed_model_ref": MODEL_REF})
    st.refs._hits = [{"id": str(rid), "title": "Dune", "content": "spice", "score": 0.9}]
    st.pins.rows = [SimpleNamespace(item_type="reference", item_id=str(rid), action="pin")]
    r = client.get(f"/v1/composition/works/{PROJECT}/scenes/{SCENE}/references")
    assert r.status_code == 200
    body = r.json()
    # auto query was built from the scene (goal/beat/title)
    assert "bridge" in body["query"].lower()
    assert body["hits"][0]["pinned"] is True and body["hits"][0]["excluded"] is False


def test_search_unavailable_on_embed_failure_is_neutral(ctx):
    client, st = ctx
    st.works.work = _work({"reference_embed_model_ref": MODEL_REF})
    st.embedder.error = EmbeddingError("timeout", retryable=True)
    r = client.get(f"/v1/composition/works/{PROJECT}/scenes/{SCENE}/references?q=echo")
    assert r.status_code == 200
    body = r.json()
    assert body["hits"] == [] and body.get("unavailable") is True


def test_search_404_when_work_missing(ctx):
    client, st = ctx
    st.works.work = None
    r = client.get(f"/v1/composition/works/{PROJECT}/scenes/{SCENE}/references")
    assert r.status_code == 404
