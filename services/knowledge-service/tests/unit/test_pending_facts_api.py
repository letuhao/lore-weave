"""K21-C (design D7) — unit tests for the public pending-facts router.

The PendingFactsRepo is mocked + `neo4j_session` / `merge_fact` are
patched, so these are pure router tests: JWT scoping, the list /
confirm / reject contracts, and the cross-user → 404 anti-oracle.
Mirrors the mock-the-repo-layer pattern of `test_logs_api.py`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import PendingFact

_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _patch_neo4j_session(monkeypatch):
    """The confirm endpoint opens `async with neo4j_session()`; the
    merge_fact call inside is itself patched per-test, so the session
    is just a stand-in."""

    @asynccontextmanager
    async def _fake():
        yield MagicMock()

    monkeypatch.setattr(
        "app.routers.public.pending_facts.neo4j_session", _fake
    )


def _pending_fact(
    *, pending_fact_id=None, fact_type="preference",
    fact_text="Kai prefers fire magic", project_id=_TEST_PROJECT,
) -> PendingFact:
    return PendingFact(
        pending_fact_id=pending_fact_id or uuid4(),
        user_id=_TEST_USER,
        project_id=project_id,
        session_id="sess-1",
        fact_type=fact_type,
        fact_text=fact_text,
        created_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
    )


def _fact_stub(content: str = "Kai prefers fire magic"):
    """A merge_fact return value — only the fields the Fact response
    model marks required need to be real."""
    return SimpleNamespace(
        id="fact-1",
        user_id=str(_TEST_USER),
        project_id=str(_TEST_PROJECT),
        type="preference",
        content=content,
        canonical_content=content.lower(),
        confidence=0.7,
        pending_validation=False,
        valid_from=None,
        valid_until=None,
        source_types=["llm_tool_call"],
        source_chapter=None,
        evidence_count=0,
        archived_at=None,
        created_at=None,
        updated_at=None,
    )


def _make_client(repo: object):
    from app.deps import get_pending_facts_repo
    from app.main import app
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_pending_facts_repo] = lambda: repo
    return TestClient(app, raise_server_exceptions=False)


# ── GET /v1/knowledge/pending-facts ──────────────────────────────────


def test_list_pending_facts_returns_callers_queue():
    rows = [_pending_fact(fact_text="a"), _pending_fact(fact_text="b")]
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=rows)
    client = _make_client(repo)

    resp = client.get("/v1/knowledge/pending-facts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["fact_text"] == "a"
    # JWT-scoped: the caller's id reaches the repo, no session/diary filter.
    repo.list_for_user.assert_awaited_once_with(_TEST_USER, session_id=None, diary_only=False)


def test_list_pending_facts_forwards_session_id():
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[])
    client = _make_client(repo)

    resp = client.get("/v1/knowledge/pending-facts?session_id=sess-42")
    assert resp.status_code == 200
    repo.list_for_user.assert_awaited_once_with(
        _TEST_USER, session_id="sess-42", diary_only=False
    )


def test_list_pending_facts_forwards_diary_only():
    # WS-2.5 (audit MED): the assistant fact inbox passes diary_only=true so chat-memory facts from
    # other projects don't leak into it.
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[])
    client = _make_client(repo)

    resp = client.get("/v1/knowledge/pending-facts?diary_only=true")
    assert resp.status_code == 200
    repo.list_for_user.assert_awaited_once_with(_TEST_USER, session_id=None, diary_only=True)


def test_list_pending_facts_empty():
    repo = AsyncMock()
    repo.list_for_user = AsyncMock(return_value=[])
    client = _make_client(repo)
    resp = client.get("/v1/knowledge/pending-facts")
    assert resp.status_code == 200
    assert resp.json() == []


# ── POST /v1/knowledge/pending-facts/{id}/confirm ────────────────────


def test_confirm_merges_fact_and_deletes_row(monkeypatch):
    """Confirm writes the queued fact to the graph then drops the
    pending row; the created Fact is returned."""
    pf = _pending_fact(fact_text="Kai prefers fire magic")
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=pf)
    repo.delete = AsyncMock(return_value=True)
    merge = AsyncMock(return_value=_fact_stub("Kai prefers fire magic"))
    monkeypatch.setattr(
        "app.routers.public.pending_facts.merge_fact", merge
    )
    client = _make_client(repo)

    resp = client.post(
        f"/v1/knowledge/pending-facts/{pf.pending_fact_id}/confirm"
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "fact-1"

    # merge_fact got the stored (already-neutralized) text + the
    # guardrail confidence/source_type a direct memory_remember uses.
    kwargs = merge.await_args.kwargs
    assert kwargs["content"] == "Kai prefers fire magic"
    assert kwargs["confidence"] == 0.7
    assert kwargs["source_type"] == "llm_tool_call"
    assert kwargs["pending_validation"] is False
    assert kwargs["type"] == "preference"
    # The pending row is drained after the write.
    repo.delete.assert_awaited_once_with(_TEST_USER, pf.pending_fact_id)


def test_confirm_passes_null_project_id_through(monkeypatch):
    """A no-project pending fact confirms with project_id=None."""
    pf = _pending_fact(project_id=None)
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=pf)
    repo.delete = AsyncMock(return_value=True)
    merge = AsyncMock(return_value=_fact_stub())
    monkeypatch.setattr(
        "app.routers.public.pending_facts.merge_fact", merge
    )
    client = _make_client(repo)

    resp = client.post(
        f"/v1/knowledge/pending-facts/{pf.pending_fact_id}/confirm"
    )
    assert resp.status_code == 200
    assert merge.await_args.kwargs["project_id"] is None


def test_confirm_cross_user_or_missing_returns_404(monkeypatch):
    """repo.get returns None for a cross-user / missing id → 404, and
    merge_fact is never called."""
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.delete = AsyncMock()
    merge = AsyncMock()
    monkeypatch.setattr(
        "app.routers.public.pending_facts.merge_fact", merge
    )
    client = _make_client(repo)

    resp = client.post(f"/v1/knowledge/pending-facts/{uuid4()}/confirm")
    assert resp.status_code == 404
    merge.assert_not_awaited()
    repo.delete.assert_not_awaited()


# ── POST /v1/knowledge/pending-facts/{id}/reject ─────────────────────


def test_reject_deletes_row_returns_204():
    # WS-2.2 (audit): the FE reject goes through repo.reject (delete + tombstone), NOT a plain delete,
    # so a dismissed diary fact is not re-proposed on the next distill.
    pf = _pending_fact()
    repo = AsyncMock()
    repo.reject = AsyncMock(return_value=True)
    client = _make_client(repo)

    resp = client.post(
        f"/v1/knowledge/pending-facts/{pf.pending_fact_id}/reject"
    )
    assert resp.status_code == 204
    repo.reject.assert_awaited_once_with(_TEST_USER, pf.pending_fact_id)


def test_reject_cross_user_or_missing_returns_404():
    """repo.reject returns False for a cross-user / missing id → 404."""
    repo = AsyncMock()
    repo.reject = AsyncMock(return_value=False)
    client = _make_client(repo)

    resp = client.post(f"/v1/knowledge/pending-facts/{uuid4()}/reject")
    assert resp.status_code == 404


# ── auth ─────────────────────────────────────────────────────────────


def test_pending_facts_requires_jwt():
    """The router-level get_current_user dep means an unauthenticated
    request is rejected before any route logic runs."""
    from app.main import app

    # No get_current_user override — the real JWT dependency runs.
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/v1/knowledge/pending-facts")
    assert resp.status_code == 401
