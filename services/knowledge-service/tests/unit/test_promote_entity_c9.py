"""C9 — unit tests for POST /v1/knowledge/entities/{id}/promote.

The promote endpoint orchestrates the two-call curation flow server-side
(the FE cannot reach glossary's /internal/extract-entities, and partial-
failure handling is safest in one request):

  1. create a glossary DRAFT (status='draft', tag 'ai-suggested') from the
     discovered entity's name/kind/aliases via the GlossaryClient
     (→ POST /internal/books/{book_id}/extract-entities), and
  2. anchor the knowledge entity (glossary_entity_id + anchor_score=1.0)
     via link_to_glossary.

Locks under test (C9-promote-flow):
  - draft, NOT active — default_tags=['ai-suggested'] is sent.
  - ordering: draft-create THEN anchor.
  - anchor sets glossary_entity_id + anchor_score=1.0 → status flips to
    canonical.
  - promote only a DISCOVERED entity — already-anchored ⇒ 409 (no double
    draft); no book ⇒ 422; cross-user/missing ⇒ 404.
  - partial failure: propose fails ⇒ no anchor (502); anchor fails after
    a draft was created ⇒ 502, but a retry is safe (propose dedups by
    name; link_to_glossary is idempotent).

Neo4j + glossary-service + project repo are mocked; the live cross-service
proof is the VERIFY-phase live-smoke on a built graph.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.entities import Entity

_TEST_USER = uuid4()
_PROJECT_ID = uuid4()
_BOOK_ID = uuid4()
_GLOSSARY_ID = str(uuid4())


def _entity(
    *,
    id: str = "ent-zhang",
    name: str = "Zhang Ruochen",
    kind: str = "person",
    glossary_entity_id: str | None = None,
    anchor_score: float = 0.0,
    aliases: list[str] | None = None,
) -> Entity:
    return Entity(
        id=id,
        user_id=str(_TEST_USER),
        project_id=str(_PROJECT_ID),
        name=name,
        canonical_name=name.lower(),
        kind=kind,
        aliases=aliases if aliases is not None else [name],
        glossary_entity_id=glossary_entity_id,
        anchor_score=anchor_score,
        mention_count=42,
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


def _project_meta(book_id):
    """Shape returned by ProjectsRepo.get — only book_id is read here."""
    proj = MagicMock()
    proj.book_id = book_id
    proj.project_id = _PROJECT_ID
    return proj


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app

    yield
    app.dependency_overrides.clear()


def _make_client(
    *,
    project=None,
    propose_return=None,
):
    """Wire a TestClient with get_current_user + glossary client + project
    repo overridden. ``propose_return`` is the dict the GlossaryClient's
    propose_entities resolves to (None ⇒ glossary failure)."""
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import get_glossary_client, get_projects_repo

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER

    repo = MagicMock()
    repo.get = AsyncMock(
        return_value=project if project is not None else _project_meta(_BOOK_ID)
    )
    app.dependency_overrides[get_projects_repo] = lambda: repo

    gclient = MagicMock()
    gclient.propose_entities = AsyncMock(return_value=propose_return)
    app.dependency_overrides[get_glossary_client] = lambda: gclient

    client = TestClient(app, raise_server_exceptions=False)
    return client, repo, gclient


def _propose_ok(entity_id: str = _GLOSSARY_ID, status: str = "created") -> dict:
    return {
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "entities": [
            {
                "entity_id": entity_id,
                "name": "zhang ruochen",
                "kind_code": "character",
                "status": status,
                "attributes_written": [],
                "attributes_skipped": [],
            }
        ],
    }


# ── happy path: draft-create THEN anchor ─────────────────────────────


def test_promote_creates_draft_then_anchors():
    """A discovered entity is proposed to glossary as an ai-suggested
    draft, then anchored — response is the canonical entity."""
    discovered = _entity()
    anchored = _entity(
        glossary_entity_id=_GLOSSARY_ID,
        anchor_score=1.0,
        kind="character",
    )

    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.link_to_glossary",
        new_callable=AsyncMock,
        return_value=anchored,
    ) as mock_link, patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, gclient = _make_client(propose_return=_propose_ok())
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")

    assert resp.status_code == 200, resp.json()
    body = resp.json()
    # anchored ⇒ status canonical + anchor_score 1.0 + glossary_entity_id set
    assert body["status"] == "canonical"
    assert body["anchor_score"] == 1.0
    assert body["glossary_entity_id"] == _GLOSSARY_ID

    # draft-create call carried the ai-suggested tag (draft, NOT active).
    assert gclient.propose_entities.await_count == 1
    _args, kwargs = gclient.propose_entities.await_args
    assert kwargs["default_tags"] == ["ai-suggested"]
    assert kwargs["park_unknown_kinds"] is False

    # anchor used the glossary_entity_id read back from the draft-create.
    assert mock_link.await_count == 1
    link_kwargs = mock_link.await_args.kwargs
    assert link_kwargs["glossary_entity_id"] == _GLOSSARY_ID
    assert link_kwargs["canonical_id"] == discovered.id


def test_promote_normalizes_extractor_kind_to_glossary_kind_code():
    """The discovered entity's extractor kind (person) is normalized to a
    glossary kind_code (character) in the draft-create payload."""
    discovered = _entity(kind="person")
    anchored = _entity(glossary_entity_id=_GLOSSARY_ID, anchor_score=1.0)

    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.link_to_glossary",
        new_callable=AsyncMock,
        return_value=anchored,
    ), patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, gclient = _make_client(propose_return=_propose_ok())
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")

    assert resp.status_code == 200, resp.json()
    _args, kwargs = gclient.propose_entities.await_args
    proposed = kwargs["entities"][0]
    assert proposed["kind_code"] == "character"
    assert proposed["name"] == discovered.canonical_name


# ── guards ───────────────────────────────────────────────────────────


def test_promote_404_when_entity_missing_or_cross_user():
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, gclient = _make_client()
        resp = client.post("/v1/knowledge/entities/ghost/promote")
    assert resp.status_code == 404
    # no glossary write attempted
    assert gclient.propose_entities.await_count == 0


def test_promote_409_when_already_anchored():
    """Already-canonical (glossary_entity_id set) ⇒ 409, no double-draft."""
    already = _entity(glossary_entity_id=_GLOSSARY_ID, anchor_score=1.0)
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=already,
    ), patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, gclient = _make_client()
        resp = client.post(f"/v1/knowledge/entities/{already.id}/promote")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error_code"] == "already_anchored"
    assert gclient.propose_entities.await_count == 0


def test_promote_422_when_project_has_no_book():
    """No book_id on the project ⇒ nowhere to write the glossary draft."""
    discovered = _entity()
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, gclient = _make_client(project=_project_meta(None))
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")
    assert resp.status_code == 422
    assert resp.json()["detail"]["error_code"] == "no_book"
    assert gclient.propose_entities.await_count == 0


# ── partial failure ──────────────────────────────────────────────────


def test_promote_502_when_glossary_draft_fails_no_anchor():
    """propose_entities returns None (glossary down/4xx) ⇒ 502 and the
    entity is NOT anchored (link_to_glossary never called)."""
    discovered = _entity()
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.link_to_glossary",
        new_callable=AsyncMock,
    ) as mock_link, patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, _gclient = _make_client(propose_return=None)
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error_code"] == "glossary_draft_failed"
    assert mock_link.await_count == 0


def test_promote_502_when_anchor_fails_after_draft_created():
    """Draft created but link_to_glossary returns None (stale id / race) ⇒
    502. The draft persists; a retry is safe because propose dedups by
    name and link_to_glossary is idempotent."""
    discovered = _entity()
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.link_to_glossary",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, _gclient = _make_client(propose_return=_propose_ok())
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error_code"] == "anchor_failed"


def test_promote_502_when_draft_response_tombstoned():
    """A tombstoned (user-rejected, ai-rejected) name ⇒ 502; the user
    explicitly refused this suggestion, so it is NOT anchorable."""
    discovered = _entity()
    skipped = {
        "created": 0,
        "updated": 0,
        "skipped": 1,
        "entities": [
            {"entity_id": str(uuid4()), "name": "x", "status": "skipped",
             "skip_reason": "tombstoned"}
        ],
    }
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.link_to_glossary",
        new_callable=AsyncMock,
    ) as mock_link, patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, _gclient = _make_client(propose_return=skipped)
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error_code"] == "glossary_draft_failed"
    assert mock_link.await_count == 0


def test_promote_anchors_when_draft_skipped_as_existing_noop_merge():
    """A `skipped` row that carries a valid entity_id (the name already
    named an existing glossary entry → no-op merge, NOT a tombstone) is
    anchorable — promote anchors the discovered entity to that entry."""
    discovered = _entity()
    anchored = _entity(glossary_entity_id=_GLOSSARY_ID, anchor_score=1.0)
    existing = {
        "created": 0,
        "updated": 0,
        "skipped": 1,
        "entities": [
            {"entity_id": _GLOSSARY_ID, "name": "zhang ruochen",
             "status": "skipped"}  # no skip_reason ⇒ existing no-op merge
        ],
    }
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.link_to_glossary",
        new_callable=AsyncMock,
        return_value=anchored,
    ) as mock_link, patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, _gclient = _make_client(propose_return=existing)
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "canonical"
    assert mock_link.await_count == 1
    assert mock_link.await_args.kwargs["glossary_entity_id"] == _GLOSSARY_ID


def test_promote_502_when_draft_response_has_empty_entity_id():
    """A propose response whose only row has an empty entity_id ⇒ 502;
    nothing to anchor to."""
    discovered = _entity()
    empty = {
        "created": 0, "updated": 0, "skipped": 1,
        "entities": [{"entity_id": "", "name": "x", "status": "skipped"}],
    }
    with patch(
        "app.routers.public.entities.get_entity",
        new_callable=AsyncMock,
        return_value=discovered,
    ), patch(
        "app.routers.public.entities.link_to_glossary",
        new_callable=AsyncMock,
    ) as mock_link, patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client, _repo, _gclient = _make_client(propose_return=empty)
        resp = client.post(f"/v1/knowledge/entities/{discovered.id}/promote")
    assert resp.status_code == 502
    assert resp.json()["detail"]["error_code"] == "glossary_draft_failed"
    assert mock_link.await_count == 0
