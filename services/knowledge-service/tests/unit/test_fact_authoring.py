"""S-05 — human fact authoring / invalidation + the curation read-fix.

Router endpoints exercised via TestClient with the fact repo mocked (the same
pattern as `test_relation_correction`). `emit_correction` is a best-effort no-op
here (no pool in unit tests). These are the correctness gates the spec §B.3 names
for Part A: author appears (curation read shows it), a bad `fact_type` 422s (never
500), cross-user entity 404s before any write, invalidate flips + is 404-on-missing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.facts import Fact

_TEST_USER = uuid4()
_ENTITY_ID = "ent-aria-1"


def _fact(fact_id="fact-1", type="decision", content="Aria distrusts the Council",
          valid_until=None, confidence=1.0, source_types=None) -> Fact:
    return Fact(
        id=fact_id,
        user_id=str(_TEST_USER),
        project_id="proj-1",
        type=type,
        content=content,
        canonical_content=content.lower(),
        confidence=confidence,
        pending_validation=False,
        valid_until=valid_until,
        source_types=source_types if source_types is not None else ["manual"],
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _client() -> TestClient:
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app, raise_server_exceptions=False)


# ── author: POST /entities/{id}/facts ────────────────────────────────────────

@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.entities.merge_fact", new_callable=AsyncMock)
@patch("app.routers.public.entities.get_entity", new_callable=AsyncMock)
def test_author_fact_happy(mock_get_entity, mock_merge):
    mock_get_entity.return_value = MagicMock(project_id="proj-1")
    mock_merge.return_value = _fact()
    resp = _client().post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/facts",
        json={"fact_type": "decision", "content": "Aria distrusts the Council"},
    )
    assert resp.status_code == 201, resp.json()
    assert resp.json()["content"] == "Aria distrusts the Council"
    # The write MUST be a committed, high-confidence, ABOUT-linked, manual fact —
    # the whole point of direct-write is that it clears the ≥0.8 curation floor and
    # links to the entity (else it never shows in the panel that authored it).
    _, kwargs = mock_merge.call_args
    assert kwargs["confidence"] == 1.0
    assert kwargs["pending_validation"] is False
    assert kwargs["source_type"] == "manual"
    assert kwargs["provenance"] == "human_authored"
    assert kwargs["subject_id"] == _ENTITY_ID


@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.entities.merge_fact", new_callable=AsyncMock)
@patch("app.routers.public.entities.get_entity", new_callable=AsyncMock)
def test_author_fact_bad_type_422_not_500(mock_get_entity, mock_merge):
    """A value outside the closed 6-value FactType must 422 at the schema, never
    reach merge_fact (whose ValueError would surface as 500)."""
    mock_get_entity.return_value = MagicMock(project_id="proj-1")
    resp = _client().post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/facts",
        json={"fact_type": "gossip", "content": "not a real type"},
    )
    assert resp.status_code == 422
    mock_merge.assert_not_awaited()


@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.entities.merge_fact", new_callable=AsyncMock)
@patch("app.routers.public.entities.get_entity", new_callable=AsyncMock)
def test_author_fact_cross_user_entity_404_no_write(mock_get_entity, mock_merge):
    """A fact can only attach to the caller's OWN entity — an unknown/cross-user
    entity 404s BEFORE any write, so no orphan fact lands on a foreign subject."""
    mock_get_entity.return_value = None
    resp = _client().post(
        f"/v1/knowledge/entities/{_ENTITY_ID}/facts",
        json={"fact_type": "decision", "content": "x"},
    )
    assert resp.status_code == 404
    mock_merge.assert_not_awaited()


@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.entities.merge_fact", new_callable=AsyncMock)
@patch("app.routers.public.entities.get_entity", new_callable=AsyncMock)
def test_author_fact_all_six_types_accepted(mock_get_entity, mock_merge):
    """All 6 FactType values author successfully (the FE offers all 6 — a form that
    422'd statement/commitment would be the 4-vs-6 label drift shipped as a bug)."""
    mock_get_entity.return_value = MagicMock(project_id="proj-1")
    for t in ("decision", "preference", "milestone", "negation", "statement", "commitment"):
        mock_merge.return_value = _fact(type=t)
        resp = _client().post(
            f"/v1/knowledge/entities/{_ENTITY_ID}/facts",
            json={"fact_type": t, "content": f"a {t} fact"},
        )
        assert resp.status_code == 201, (t, resp.json())


# ── curation read: GET /entities/{id}/facts?curation=true ────────────────────

@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.entities.list_facts_for_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.resolve_before_order", new_callable=AsyncMock)
def test_curation_read_skips_spoiler_window(mock_resolve, mock_list):
    """curation=true → NO spoiler resolution, before_order=None (whole-book) so the
    authored fact (NULL from_order) is visible. Without it the fail-closed window
    (-1) hides every fact — the pre-existing empty-shell bug this fixes."""
    mock_list.return_value = [_fact()]
    resp = _client().get(
        f"/v1/knowledge/entities/{_ENTITY_ID}/facts?curation=true"
    )
    assert resp.status_code == 200, resp.json()
    assert len(resp.json()["facts"]) == 1
    mock_resolve.assert_not_awaited()  # spoiler resolution is skipped entirely
    _, kwargs = mock_list.call_args
    assert kwargs["before_order"] is None  # whole-book, no window


@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.entities.list_facts_for_entity", new_callable=AsyncMock)
@patch("app.routers.public.entities.resolve_before_order", new_callable=AsyncMock)
def test_reader_read_still_fail_closed(mock_resolve, mock_list):
    """Default (reader) mode is UNCHANGED: no chapter → fail-closed window (-1),
    so future reveals never leak. curation must be an explicit opt-in, not the default."""
    mock_resolve.return_value = (-1, False)
    mock_list.return_value = []
    resp = _client().get(f"/v1/knowledge/entities/{_ENTITY_ID}/facts")
    assert resp.status_code == 200
    mock_resolve.assert_awaited_once()
    _, kwargs = mock_list.call_args
    assert kwargs["before_order"] == -1


# ── invalidate: POST /facts/{id}/invalidate ──────────────────────────────────

@patch("app.routers.public.facts.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.facts.invalidate_fact", new_callable=AsyncMock)
@patch("app.routers.public.facts.get_fact", new_callable=AsyncMock)
def test_invalidate_fact_happy(mock_get, mock_invalidate):
    mock_get.return_value = _fact()
    mock_invalidate.return_value = _fact(valid_until=datetime.now(timezone.utc))
    resp = _client().post("/v1/knowledge/facts/fact-1/invalidate")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["valid_until"] is not None
    mock_invalidate.assert_awaited_once()


@patch("app.routers.public.facts.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.facts.invalidate_fact", new_callable=AsyncMock)
@patch("app.routers.public.facts.get_fact", new_callable=AsyncMock)
def test_invalidate_fact_404_cross_user(mock_get, mock_invalidate):
    """A fact that isn't the caller's returns None from the owner-filtered repo →
    404 (no existence oracle)."""
    mock_get.return_value = None
    mock_invalidate.return_value = None
    resp = _client().post("/v1/knowledge/facts/missing/invalidate")
    assert resp.status_code == 404


@patch("app.routers.public.facts.emit_correction", new_callable=AsyncMock)
@patch("app.routers.public.facts.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.facts.invalidate_fact", new_callable=AsyncMock)
@patch("app.routers.public.facts.get_fact", new_callable=AsyncMock)
def test_invalidate_extraction_fact_emits_correction(mock_get, mock_invalidate, mock_emit):
    """An EXTRACTION-derived fact (source_types has a non-manual origin) retraction
    IS a learning signal → emit the fact_corrected correction."""
    f = _fact(source_types=["book_content"], valid_until=datetime.now(timezone.utc))
    mock_get.return_value = _fact(source_types=["book_content"])
    mock_invalidate.return_value = f
    resp = _client().post("/v1/knowledge/facts/fact-1/invalidate")
    assert resp.status_code == 200, resp.json()
    mock_emit.assert_awaited_once()


@patch("app.routers.public.facts.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.facts.revalidate_fact", new_callable=AsyncMock)
def test_revalidate_fact_happy(mock_revalidate):
    """S-05b — undo a mark-wrong: revalidate clears valid_until (fact re-appears)."""
    mock_revalidate.return_value = _fact(valid_until=None)
    resp = _client().post("/v1/knowledge/facts/fact-1/revalidate")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["valid_until"] is None
    mock_revalidate.assert_awaited_once()


@patch("app.routers.public.facts.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.facts.revalidate_fact", new_callable=AsyncMock)
def test_revalidate_fact_404_cross_user(mock_revalidate):
    mock_revalidate.return_value = None
    resp = _client().post("/v1/knowledge/facts/missing/revalidate")
    assert resp.status_code == 404


@patch("app.routers.public.facts.emit_correction", new_callable=AsyncMock)
@patch("app.routers.public.facts.neo4j_session", new=lambda: _noop_session())
@patch("app.routers.public.facts.invalidate_fact", new_callable=AsyncMock)
@patch("app.routers.public.facts.get_fact", new_callable=AsyncMock)
def test_invalidate_human_authored_fact_skips_correction(mock_get, mock_invalidate, mock_emit):
    """A PURELY human-authored fact (source_types == ['manual']) retraction is the
    user editing their OWN assertion — NOT an extraction correction. The invalidate
    still happens (200) but NO learning event is emitted (no false-degrade)."""
    f = _fact(source_types=["manual"], valid_until=datetime.now(timezone.utc))
    mock_get.return_value = _fact(source_types=["manual"])
    mock_invalidate.return_value = f
    resp = _client().post("/v1/knowledge/facts/fact-1/invalidate")
    assert resp.status_code == 200, resp.json()
    mock_emit.assert_not_awaited()
