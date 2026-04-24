"""K16.2 — Unit tests for extraction cost estimation endpoint.

Uses FastAPI test client with dependency overrides for repos and
clients. No real HTTP calls or database queries.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.book_client import BookClient
from app.clients.glossary_client import GlossaryClient

# Sentinel for "repo should return None" — avoids the `None or default`
# trap where `_make_client(project=None)` would silently create a stub.
_NO_PROJECT = object()


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_overrides():
    """Clear FastAPI dependency overrides after each test so stale
    overrides from one test never leak into the next."""
    from app.main import app
    yield
    app.dependency_overrides.clear()


# ── Helpers ──────────────────────────────────────────────────────────

_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()
_TEST_BOOK = uuid4()


def _project_stub(book_id: UUID | None = _TEST_BOOK):
    """Minimal object with the fields the estimate endpoint reads."""
    from app.db.models import Project
    from datetime import datetime, timezone

    return Project(
        project_id=_TEST_PROJECT,
        user_id=_TEST_USER,
        name="Test",
        description="",
        project_type="translation",
        book_id=book_id,
        instructions="",
        extraction_enabled=False,
        extraction_status="disabled",
        extraction_config={},
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_client(
    *,
    project=None,
    pending_count: int = 0,
    chapter_count: int | None = 10,
    entity_count: int | None = 50,
) -> TestClient:
    """Build a TestClient with all deps overridden.

    Pass ``project=_NO_PROJECT`` for a repo that returns None (404 path).
    Pass ``project=None`` (default) for the standard stub.
    """
    from app.main import app
    from app.deps import (
        get_book_client,
        get_extraction_pending_repo,
        get_glossary_client,
        get_projects_repo,
    )
    from app.middleware.jwt_auth import get_current_user

    # Projects repo — resolve the sentinel
    if project is _NO_PROJECT:
        repo_return = None
    else:
        repo_return = project if project is not None else _project_stub()
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=repo_return)

    # Extraction pending repo
    pending_repo = AsyncMock()
    pending_repo.count_pending = AsyncMock(return_value=pending_count)

    # Book client
    book_client = AsyncMock(spec=BookClient)
    book_client.count_chapters = AsyncMock(return_value=chapter_count)

    # Glossary client
    glossary_client = AsyncMock(spec=GlossaryClient)
    glossary_client.count_entities = AsyncMock(return_value=entity_count)

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_extraction_pending_repo] = lambda: pending_repo
    app.dependency_overrides[get_book_client] = lambda: book_client
    app.dependency_overrides[get_glossary_client] = lambda: glossary_client

    client = TestClient(app, raise_server_exceptions=False)
    return client


def _post_estimate(client: TestClient, scope: str = "all", **extra):
    body = {"scope": scope, "llm_model": "test-model", **extra}
    return client.post(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/estimate",
        json=body,
    )


# ── Tests ────────────────────────────────────────────────────────────


def test_estimate_all_scope_returns_counts():
    client = _make_client(
        chapter_count=45, pending_count=423, entity_count=1650,
    )
    resp = _post_estimate(client, "all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"]["chapters"] == 45
    assert data["items"]["chat_turns"] == 423
    assert data["items"]["glossary_entities"] == 1650
    assert data["items_total"] == 45 + 423 + 1650
    assert data["estimated_tokens"] == (
        45 * 2000 + 423 * 800 + 1650 * 300
    )
    assert float(data["estimated_cost_usd_low"]) > 0
    assert float(data["estimated_cost_usd_high"]) > float(data["estimated_cost_usd_low"])
    assert data["estimated_duration_seconds"] == (45 + 423 + 1650) * 2


def test_estimate_chapters_only_scope():
    client = _make_client(chapter_count=10, pending_count=99, entity_count=200)
    resp = _post_estimate(client, "chapters")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"]["chapters"] == 10
    assert data["items"]["chat_turns"] == 0
    assert data["items"]["glossary_entities"] == 0
    assert data["items_total"] == 10


def test_estimate_chat_only_scope():
    client = _make_client(chapter_count=10, pending_count=50, entity_count=200)
    resp = _post_estimate(client, "chat")
    data = resp.json()
    assert data["items"]["chapters"] == 0
    assert data["items"]["chat_turns"] == 50
    assert data["items"]["glossary_entities"] == 0


def test_estimate_glossary_sync_only_scope():
    client = _make_client(chapter_count=10, pending_count=50, entity_count=200)
    resp = _post_estimate(client, "glossary_sync")
    data = resp.json()
    assert data["items"]["chapters"] == 0
    assert data["items"]["chat_turns"] == 0
    assert data["items"]["glossary_entities"] == 200


def test_estimate_project_not_found_returns_404():
    client = _make_client(project=_NO_PROJECT)
    resp = _post_estimate(client)
    assert resp.status_code == 404


def test_estimate_book_client_degraded_returns_zero_chapters():
    """When book-service is unreachable, chapters count falls to 0."""
    client = _make_client(chapter_count=None, pending_count=5)
    resp = _post_estimate(client, "all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"]["chapters"] == 0
    assert data["items"]["chat_turns"] == 5


def test_estimate_glossary_client_degraded_returns_zero_entities():
    """When glossary-service is unreachable, glossary count falls to 0."""
    client = _make_client(entity_count=None, pending_count=5)
    resp = _post_estimate(client, "all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"]["glossary_entities"] == 0


def test_estimate_no_book_id_skips_chapters_and_glossary():
    """Project with no book_id → chapters and glossary are 0."""
    client = _make_client(
        project=_project_stub(book_id=None),
        chapter_count=99,
        entity_count=99,
        pending_count=10,
    )
    resp = _post_estimate(client, "all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"]["chapters"] == 0
    assert data["items"]["glossary_entities"] == 0
    assert data["items"]["chat_turns"] == 10


def test_estimate_empty_model_rejected():
    client = _make_client()
    body = {"scope": "all", "llm_model": ""}
    resp = client.post(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/extraction/estimate",
        json=body,
    )
    assert resp.status_code == 422


def test_estimate_zero_items_returns_zero_cost():
    client = _make_client(chapter_count=0, pending_count=0, entity_count=0)
    resp = _post_estimate(client, "all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items_total"] == 0
    assert float(data["estimated_cost_usd_low"]) == 0
    assert float(data["estimated_cost_usd_high"]) == 0
    assert data["estimated_duration_seconds"] == 0


def _install_capturing_book_client(chapter_count: int = 10) -> dict:
    """Install a book_client override that records kwargs of the most
    recent ``count_chapters`` call into the returned ``captured`` dict.

    Shared by the scope_range tests so the stub-plumbing boilerplate
    lives in one place. Returns the dict; the caller asserts on its
    keys after posting the estimate.
    """
    from app.main import app
    from app.deps import get_book_client

    captured: dict = {}

    async def _count_chapters(book_id, *, from_sort=None, to_sort=None):
        captured["book_id"] = book_id
        captured["from_sort"] = from_sort
        captured["to_sort"] = to_sort
        return chapter_count

    class _Stub:
        count_chapters = staticmethod(_count_chapters)

    app.dependency_overrides[get_book_client] = lambda: _Stub()
    return captured


def test_estimate_scope_range_forwards_chapter_range_to_book_client():
    """D-K16.2-02 — scope_range.chapter_range is parsed and forwarded
    to book-service as from_sort/to_sort query params, so the preview
    count reflects the range the job will actually process."""
    client = _make_client(chapter_count=11, pending_count=0, entity_count=0)
    captured = _install_capturing_book_client(chapter_count=11)

    resp = _post_estimate(
        client, "chapters", scope_range={"chapter_range": [10, 20]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"]["chapters"] == 11
    assert captured["from_sort"] == 10
    assert captured["to_sort"] == 20


def test_estimate_scope_range_all_scope_also_forwards():
    """Range forwarding must also fire under scope='all', not only
    scope='chapters' — otherwise the 'all' preview silently ignores
    the range while the eventual job honours it."""
    client = _make_client(
        chapter_count=5, pending_count=3, entity_count=2,
    )
    captured = _install_capturing_book_client(chapter_count=5)

    resp = _post_estimate(
        client, "all", scope_range={"chapter_range": [3, 7]},
    )
    assert resp.status_code == 200
    assert captured["from_sort"] == 3
    assert captured["to_sort"] == 7


def test_estimate_scope_range_malformed_rejected():
    """Malformed chapter_range → 422 so the frontend can surface the
    problem instead of the user approving a bogus estimate."""
    client = _make_client(chapter_count=10, pending_count=0, entity_count=0)
    for bad in (
        {"chapter_range": [10]},           # wrong length
        {"chapter_range": [10, 20, 30]},    # wrong length
        {"chapter_range": ["a", "b"]},      # wrong types
        {"chapter_range": [1.5, 2.5]},      # float not int
        {"chapter_range": [-1, 5]},         # negative
        {"chapter_range": "10-20"},         # not a list
        {"chapter_range": [True, False]},   # bool is int-ish but rejected
        # C12a /review-impl MED#1 — reversed range. Previously passed
        # router validation, persisted to DB, then silently skipped
        # every chapter at the runner gate. Now 422s at ingress.
        {"chapter_range": [50, 10]},
    ):
        resp = _post_estimate(client, "chapters", scope_range=bad)
        assert resp.status_code == 422, f"expected 422 for {bad}, got {resp.status_code}"


def test_estimate_scope_range_omitted_leaves_range_unset():
    """No scope_range → both from_sort/to_sort stay None so book-service
    returns the full unfiltered count. Regression guard: we don't want
    the estimate endpoint to accidentally pin from_sort=0 (which would
    still be correct today but silently breaks if sort_order ever
    allows negative values)."""
    client = _make_client(chapter_count=45, pending_count=0, entity_count=0)
    captured = _install_capturing_book_client(chapter_count=45)

    resp = _post_estimate(client, "chapters")
    assert resp.status_code == 200
    assert captured["from_sort"] is None
    assert captured["to_sort"] is None


def test_estimate_local_model_returns_zero_cost():
    """T2-close-5 wiring proof: local / self-hosted models (bge,
    llama, qwen, etc.) have $0 marginal cost, so the estimate
    dialog should show zero instead of the legacy ~$2/M fallback.
    Without `cost_per_token` on the hot path, this would fail — the
    existing >0 assertions in the other tests don't catch a missed
    wiring since the fallback happens to produce >0 too."""
    client = _make_client(chapter_count=10, pending_count=0, entity_count=0)
    resp = _post_estimate(client, "chapters", llm_model="bge-m3")
    assert resp.status_code == 200
    data = resp.json()
    # Non-zero token count but zero cost — proves cost_per_token
    # was consulted with the actual llm_model.
    assert data["estimated_tokens"] > 0
    assert float(data["estimated_cost_usd_low"]) == 0
    assert float(data["estimated_cost_usd_high"]) == 0


def test_estimate_paid_model_produces_known_magnitude():
    """Sanity-check that `gpt-4o` (0.000005 per token) produces a
    cost in the expected magnitude. Exact value would be brittle
    (estimate bands swing ±30 %), but a floor/ceiling is safe."""
    client = _make_client(chapter_count=10, pending_count=0, entity_count=0)
    resp = _post_estimate(client, "chapters", llm_model="gpt-4o")
    assert resp.status_code == 200
    data = resp.json()
    tokens = data["estimated_tokens"]  # 10 chapters × 2000 = 20,000
    # base_cost = 20_000 * 0.000005 = 0.10; bands are 0.7x–1.3x.
    low = float(data["estimated_cost_usd_low"])
    high = float(data["estimated_cost_usd_high"])
    assert 0.05 < low < 0.10
    assert 0.10 < high < 0.15
    assert tokens == 10 * 2000
