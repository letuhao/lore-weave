"""K19e.2 — unit tests for the timeline list endpoint and helper.

Covers the router + Query-validation layer and the helper's
defensive clamp. Live-Neo4j integration tests live at
``tests/integration/db/test_timeline_repo.py``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.db.neo4j_repos.events import EVENTS_MAX_LIMIT, Event, list_events_filtered


_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _event_stub(
    title: str = "Kai duels Zhao",
    event_order: int | None = 10,
    project_id: str | None = None,
) -> Event:
    return Event(
        id=f"ev-{title.lower().replace(' ', '-')}",
        user_id=str(_TEST_USER),
        project_id=project_id,
        title=title,
        canonical_title=title.lower(),
        summary=None,
        chapter_id="ch-12",
        event_order=event_order,
        chronological_order=None,
        participants=["Kai", "Zhao"],
        confidence=0.9,
        source_types=["book_content"],
        evidence_count=3,
        mention_count=5,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _stub_book_client(chapter_titles: dict | None = None):
    """C6 /review-impl L3 — BookClient override for timeline router
    tests. Default {} matches the "book-service unreachable"
    degrade path; happy-path tests pass a real UUID→title dict."""
    stub = AsyncMock()
    stub.get_chapter_titles = AsyncMock(return_value=chapter_titles or {})
    return stub


def _make_client(book_client=None):
    from app.main import app
    from app.deps import get_book_client
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    # /review-impl L3 — default override so the enricher never
    # attempts a real book-service call during unit tests. Prevents
    # latent network-dependent test behavior.
    app.dependency_overrides[get_book_client] = (
        lambda: book_client if book_client is not None else _stub_book_client()
    )
    return TestClient(app, raise_server_exceptions=False)


# ── happy path + param forwarding ────────────────────────────────────


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_happy(mock_list):
    mock_list.return_value = (
        [_event_stub("Kai duels Zhao", 10), _event_stub("Phoenix rises", 20)],
        42,
    )
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert len(body["events"]) == 2
    assert body["total"] == 42
    assert body["events"][0]["title"] == "Kai duels Zhao"
    # Defaults threaded through.
    kwargs = mock_list.await_args.kwargs
    assert kwargs["limit"] == 50
    assert kwargs["offset"] == 0
    assert kwargs["project_id"] is None
    assert kwargs["after_order"] is None
    assert kwargs["before_order"] is None
    assert kwargs["user_id"] == str(_TEST_USER)


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_project_filter_cast_to_str(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get(f"/v1/knowledge/timeline?project_id={_PROJECT_ID}")
    assert resp.status_code == 200
    # Router casts UUID back to str for Neo4j.
    assert mock_list.await_args.kwargs["project_id"] == str(_PROJECT_ID)


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_after_before_order_forwarded(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline?after_order=5&before_order=50")
    assert resp.status_code == 200
    kwargs = mock_list.await_args.kwargs
    assert kwargs["after_order"] == 5
    assert kwargs["before_order"] == 50


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_pagination_params(mock_list):
    mock_list.return_value = ([], 100)
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline?limit=25&offset=50")
    assert resp.status_code == 200
    kwargs = mock_list.await_args.kwargs
    assert kwargs["limit"] == 25
    assert kwargs["offset"] == 50


# ── 422 validation ───────────────────────────────────────────────────


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_pagination_out_of_range_rejected(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    # limit le=200
    assert client.get("/v1/knowledge/timeline?limit=500").status_code == 422
    # limit ge=1
    assert client.get("/v1/knowledge/timeline?limit=0").status_code == 422
    # offset ge=0
    assert client.get("/v1/knowledge/timeline?offset=-1").status_code == 422
    # after_order ge=0
    assert (
        client.get("/v1/knowledge/timeline?after_order=-1").status_code == 422
    )
    # before_order ge=0
    assert (
        client.get("/v1/knowledge/timeline?before_order=-5").status_code == 422
    )
    # Repo never called on 422.
    mock_list.assert_not_awaited()


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_reversed_range_rejected(mock_list):
    """after_order >= before_order collapses to 422 with a readable
    detail instead of silently returning an empty page."""
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get(
        "/v1/knowledge/timeline?after_order=50&before_order=50"
    )
    assert resp.status_code == 422
    assert "after_order" in resp.json()["detail"]
    assert "before_order" in resp.json()["detail"]
    mock_list.assert_not_awaited()

    resp = client.get(
        "/v1/knowledge/timeline?after_order=100&before_order=10"
    )
    assert resp.status_code == 422
    mock_list.assert_not_awaited()


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_boundary_after_less_than_before_ok(mock_list):
    """after_order=0, before_order=1 is the smallest valid range and
    should NOT trip the reversed-range guard."""
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline?after_order=0&before_order=1")
    assert resp.status_code == 200
    mock_list.assert_awaited_once()


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_bad_project_id_rejected(mock_list):
    """UUID param validation."""
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline?project_id=not-a-uuid")
    assert resp.status_code == 422
    mock_list.assert_not_awaited()


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_user_id_from_jwt(mock_list):
    """Handler must pass the JWT user_id down to the helper; a caller
    cannot spoof another user's timeline."""
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline")
    assert resp.status_code == 200
    assert mock_list.await_args.kwargs["user_id"] == str(_TEST_USER)


# ── helper-layer defensive clamp ─────────────────────────────────────


def _make_result_stub(single_value=None, records=None):
    """Minimal stand-in for the async neo4j Result that run_read
    returns. ``single()`` / async iteration are the only surfaces the
    helper touches."""
    stub = MagicMock()
    stub.single = AsyncMock(return_value=single_value)

    async def _aiter():
        for record in records or []:
            yield record

    stub.__aiter__ = lambda self=stub: _aiter()
    return stub


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.events.run_read", new_callable=AsyncMock)
async def test_list_events_filtered_clamps_limit(mock_run_read):
    """Defence-in-depth: if the router's ``Query(le=EVENTS_MAX_LIMIT)``
    ever regresses, the repo still clamps so the worst case is one
    page of ``EVENTS_MAX_LIMIT`` rows, not an arbitrary scan.

    Patching ``run_read`` lets us inspect the ``$limit`` kwarg the
    helper forwards to Cypher — the only place the clamp has an
    observable effect without seeding hundreds of events."""
    count_stub = _make_result_stub(single_value={"total": 1})
    page_stub = _make_result_stub(records=[])
    mock_run_read.side_effect = [count_stub, page_stub]
    await list_events_filtered(
        session=MagicMock(),
        user_id="u-1",
        project_id=None,
        after_order=None,
        before_order=None,
        limit=EVENTS_MAX_LIMIT + 300,
        offset=0,
    )
    # Second run_read is the page query; assert its limit kwarg was
    # clamped to EVENTS_MAX_LIMIT.
    page_call = mock_run_read.await_args_list[1]
    assert page_call.kwargs["limit"] == EVENTS_MAX_LIMIT


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.events.run_read", new_callable=AsyncMock)
async def test_list_events_filtered_passes_limit_below_cap(mock_run_read):
    """Counterpart to the clamp test — when ``limit`` is below the
    cap, the helper forwards it verbatim. Prevents a regression that
    silently forces every page to ``EVENTS_MAX_LIMIT``."""
    count_stub = _make_result_stub(single_value={"total": 1})
    page_stub = _make_result_stub(records=[])
    mock_run_read.side_effect = [count_stub, page_stub]
    await list_events_filtered(
        session=MagicMock(),
        user_id="u-1",
        project_id=None,
        after_order=None,
        before_order=None,
        limit=25,
        offset=0,
    )
    page_call = mock_run_read.await_args_list[1]
    assert page_call.kwargs["limit"] == 25


# ── C6 /review-impl L3 — router-level enricher integration ────────


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_response_contains_enriched_chapter_title(mock_list):
    """C6 lock: valid-UUID chapter_id on an event → router calls
    enricher → enricher calls BookClient → response contains the
    resolved chapter_title. Previous tests used ``chapter_id="ch-12"``
    (invalid UUID) which silently bypassed the enricher path."""
    cid = uuid4()
    event = _event_stub("Kai duels Zhao", 10)
    # Override the stub's default chapter_id with a real UUID so the
    # enricher resolves it.
    event.chapter_id = str(cid)
    mock_list.return_value = ([event], 1)

    book_client = _stub_book_client(
        chapter_titles={cid: "Chapter 12 — The Bridge Duel"},
    )
    client = _make_client(book_client=book_client)
    resp = client.get("/v1/knowledge/timeline")
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["events"][0]["chapter_title"] == "Chapter 12 — The Bridge Duel"
    # Enricher batched exactly one call with the single id.
    book_client.get_chapter_titles.assert_awaited_once()
    call_ids = book_client.get_chapter_titles.await_args.args[0]
    assert call_ids == [cid]


# ── C10 — entity_id filter + chronological range ──────────────────


def _entity_stub(name: str = "Kai", aliases: list[str] | None = None):
    from app.db.neo4j_repos.entities import Entity
    from decimal import Decimal  # noqa: F401 (match original import style)

    return Entity(
        id="ent-kai",
        user_id=str(_TEST_USER),
        project_id=None,
        name=name,
        canonical_name=name.lower(),
        kind="character",
        aliases=aliases or ["Master Kai"],
        canonical_version=1,
        source_types=["chapter"],
        confidence=0.9,
        archived_at=None,
        archive_reason=None,
        evidence_count=0,
        mention_count=0,
        user_edited=False,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.get_entity", new_callable=AsyncMock)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_entity_id_resolves_to_participant_candidates(
    mock_get_entity, mock_list,
):
    """C10 (D-K19e-α-01) happy: router looks up the entity, passes
    [name, canonical_name, *aliases] deduped to the repo."""
    mock_get_entity.return_value = _entity_stub(
        name="Kai", aliases=["Master Kai", "The Bridge-Breaker"],
    )
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline?entity_id=ent-kai")
    assert resp.status_code == 200
    mock_get_entity.assert_awaited_once()
    get_kwargs = mock_get_entity.await_args.kwargs
    assert get_kwargs["user_id"] == str(_TEST_USER)
    assert get_kwargs["canonical_id"] == "ent-kai"
    # list_events_filtered received the deduped candidate set.
    call = mock_list.await_args.kwargs
    candidates = set(call["participant_candidates"])
    assert candidates == {"Kai", "kai", "Master Kai", "The Bridge-Breaker"}


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.get_entity", new_callable=AsyncMock)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_entity_id_not_found_collapses_to_empty_list(
    mock_get_entity, mock_list,
):
    """C10: missing / cross-user entity → participant_candidates=[]
    so the Cypher IN predicate matches nothing. No 404 leak — the
    response looks identical to 'valid entity with zero events'."""
    mock_get_entity.return_value = None
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get(f"/v1/knowledge/timeline?entity_id={'x' * 40}")
    assert resp.status_code == 200
    assert resp.json() == {"events": [], "total": 0}
    call = mock_list.await_args.kwargs
    assert call["participant_candidates"] == []


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_chronological_range_threaded(mock_list):
    """C10 (D-K19e-α-03): after_chronological / before_chronological
    are passed through to the repo."""
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get(
        "/v1/knowledge/timeline?after_chronological=5&before_chronological=50"
    )
    assert resp.status_code == 200
    call = mock_list.await_args.kwargs
    assert call["after_chronological"] == 5
    assert call["before_chronological"] == 50


def test_timeline_reversed_chronological_range_422():
    """C10: reversed chronological range → 422, mirroring the
    existing after_order/before_order validation."""
    client = _make_client()
    resp = client.get(
        "/v1/knowledge/timeline?after_chronological=50&before_chronological=10"
    )
    assert resp.status_code == 422
    assert "chronological" in resp.json()["detail"]


def test_timeline_entity_id_rejected_when_empty_string():
    """min_length=1 — empty entity_id param is a malformed filter,
    better to 422 than silently ignore."""
    client = _make_client()
    resp = client.get("/v1/knowledge/timeline?entity_id=")
    assert resp.status_code == 422


@patch(
    "app.routers.public.timeline.list_events_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.timeline.get_entity", new_callable=AsyncMock)
@patch("app.routers.public.timeline.neo4j_session", new=lambda: _noop_session())
def test_timeline_all_three_filters_combined(mock_get_entity, mock_list):
    """C10: entity_id + chronological range + project_id all apply
    together — each gets forwarded to the repo."""
    mock_get_entity.return_value = _entity_stub()
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get(
        f"/v1/knowledge/timeline?project_id={_PROJECT_ID}"
        f"&entity_id=ent-kai"
        f"&after_chronological=1&before_chronological=100"
    )
    assert resp.status_code == 200
    call = mock_list.await_args.kwargs
    assert call["project_id"] == str(_PROJECT_ID)
    assert call["after_chronological"] == 1
    assert call["before_chronological"] == 100
    assert call["participant_candidates"] is not None
    assert len(call["participant_candidates"]) >= 2  # name + canonical_name at minimum
