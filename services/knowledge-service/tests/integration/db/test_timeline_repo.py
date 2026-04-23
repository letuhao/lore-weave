"""K19e.2 — integration tests for ``list_events_filtered``.

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id and DETACH DELETEs in finally so concurrent runs don't
clobber each other.

Acceptance:
  - Tenant scope: cross-user events never surface.
  - ``project_id`` filter narrows to one project.
  - ``after_order`` / ``before_order`` are strict inequalities.
  - Range combined.
  - NULL ``event_order`` is included only when both bounds are None.
  - Archived events are excluded.
  - Pagination is stable (no overlap / no drop across pages).
  - Past-end offset returns (``[]``, total).
"""

from __future__ import annotations

import uuid

import pytest

from app.db.neo4j_repos.events import (
    list_events_filtered,
    merge_event,
)


@pytest.fixture
def test_user():
    return f"u-test-{uuid.uuid4().hex[:12]}"


async def _cleanup(neo4j_driver, *user_ids: str) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:Event) WHERE e.user_id IN $uids DETACH DELETE e",
            uids=list(user_ids),
        )


async def _archive_event(neo4j_driver, event_id: str) -> None:
    """Test-only helper — flips ``archived_at`` on a node directly
    via Cypher because events.py has no public archive function."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:Event {id: $id}) SET e.archived_at = datetime()",
            id=event_id,
        )


@pytest.mark.asyncio
async def test_timeline_browse_no_filter_returns_all_for_user(
    neo4j_driver, test_user
):
    try:
        async with neo4j_driver.session() as session:
            await merge_event(
                session, user_id=test_user, project_id="p-1",
                title="First", chapter_id="ch-1", event_order=1,
            )
            await merge_event(
                session, user_id=test_user, project_id="p-1",
                title="Second", chapter_id="ch-1", event_order=2,
            )
            rows, total = await list_events_filtered(
                session,
                user_id=test_user,
                project_id=None,
                after_order=None,
                before_order=None,
                limit=50,
                offset=0,
            )
        assert total == 2
        assert [e.title for e in rows] == ["First", "Second"]
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_cross_user_excluded(neo4j_driver):
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            await merge_event(
                session, user_id=user_a, project_id="p-1",
                title="Alpha event", chapter_id="ch-1", event_order=5,
            )
            await merge_event(
                session, user_id=user_b, project_id="p-1",
                title="Beta event", chapter_id="ch-1", event_order=5,
            )
            rows_a, total_a = await list_events_filtered(
                session, user_id=user_a, project_id=None,
                after_order=None, before_order=None, limit=50, offset=0,
            )
        assert total_a == 1
        assert rows_a[0].title == "Alpha event"
    finally:
        await _cleanup(neo4j_driver, user_a, user_b)


@pytest.mark.asyncio
async def test_timeline_browse_project_filter(neo4j_driver, test_user):
    try:
        async with neo4j_driver.session() as session:
            await merge_event(
                session, user_id=test_user, project_id="p-1",
                title="Proj1 event", chapter_id="ch-1", event_order=1,
            )
            await merge_event(
                session, user_id=test_user, project_id="p-2",
                title="Proj2 event", chapter_id="ch-2", event_order=2,
            )
            rows, total = await list_events_filtered(
                session, user_id=test_user, project_id="p-1",
                after_order=None, before_order=None, limit=50, offset=0,
            )
        assert total == 1
        assert rows[0].title == "Proj1 event"
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_after_order_strict(neo4j_driver, test_user):
    try:
        async with neo4j_driver.session() as session:
            for i, title in enumerate(["A", "B", "C"], start=1):
                await merge_event(
                    session, user_id=test_user, project_id="p-1",
                    title=title, chapter_id="ch-1", event_order=i,
                )
            # after_order=2 → only C (order=3) matches (strict >).
            rows, total = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=2, before_order=None, limit=50, offset=0,
            )
        assert total == 1
        assert rows[0].title == "C"
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_before_order_strict(neo4j_driver, test_user):
    try:
        async with neo4j_driver.session() as session:
            for i, title in enumerate(["A", "B", "C"], start=1):
                await merge_event(
                    session, user_id=test_user, project_id="p-1",
                    title=title, chapter_id="ch-1", event_order=i,
                )
            # before_order=2 → only A (order=1) matches (strict <).
            rows, total = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=2, limit=50, offset=0,
            )
        assert total == 1
        assert rows[0].title == "A"
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_range_combined(neo4j_driver, test_user):
    try:
        async with neo4j_driver.session() as session:
            for i in range(1, 6):
                await merge_event(
                    session, user_id=test_user, project_id="p-1",
                    title=f"E{i}", chapter_id="ch-1", event_order=i,
                )
            # (1, 5) → only 2, 3, 4.
            rows, total = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=1, before_order=5, limit=50, offset=0,
            )
        assert total == 3
        assert [e.title for e in rows] == ["E2", "E3", "E4"]
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_null_order_included_only_when_both_bounds_none(
    neo4j_driver, test_user
):
    """Lock the documented null-order semantics — a null-event_order
    event is included when both bounds are None and excluded whenever
    either bound is set (NULL comparisons evaluate to NULL/false)."""
    try:
        async with neo4j_driver.session() as session:
            await merge_event(
                session, user_id=test_user, project_id="p-1",
                title="No order", chapter_id="ch-1", event_order=None,
            )
            await merge_event(
                session, user_id=test_user, project_id="p-1",
                title="With order", chapter_id="ch-1", event_order=5,
            )
            # Both bounds None → null-order event included.
            rows_all, total_all = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=50, offset=0,
            )
            assert total_all == 2
            assert {e.title for e in rows_all} == {"No order", "With order"}
            # after_order set → null-order event excluded.
            rows_a, total_a = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=0, before_order=None, limit=50, offset=0,
            )
            assert total_a == 1
            assert rows_a[0].title == "With order"
            # before_order set → null-order event excluded.
            rows_b, total_b = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=100, limit=50, offset=0,
            )
            assert total_b == 1
            assert rows_b[0].title == "With order"
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_archived_excluded(neo4j_driver, test_user):
    try:
        async with neo4j_driver.session() as session:
            active = await merge_event(
                session, user_id=test_user, project_id="p-1",
                title="Active", chapter_id="ch-1", event_order=1,
            )
            archived = await merge_event(
                session, user_id=test_user, project_id="p-1",
                title="Archived", chapter_id="ch-1", event_order=2,
            )
        await _archive_event(neo4j_driver, archived.id)
        async with neo4j_driver.session() as session:
            rows, total = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=50, offset=0,
            )
        assert total == 1
        assert rows[0].id == active.id
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_pagination_three_pages_no_overlap(
    neo4j_driver, test_user
):
    try:
        async with neo4j_driver.session() as session:
            for i in range(1, 7):
                await merge_event(
                    session, user_id=test_user, project_id="p-1",
                    title=f"E{i}", chapter_id="ch-1", event_order=i,
                )
        async with neo4j_driver.session() as session:
            page1, total = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=2, offset=0,
            )
            page2, _ = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=2, offset=2,
            )
            page3, _ = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=2, offset=4,
            )
        assert total == 6
        assert [e.title for e in page1] == ["E1", "E2"]
        assert [e.title for e in page2] == ["E3", "E4"]
        assert [e.title for e in page3] == ["E5", "E6"]
        seen = {e.id for e in page1} | {e.id for e in page2} | {e.id for e in page3}
        assert len(seen) == 6
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_past_end_offset_returns_empty_with_total(
    neo4j_driver, test_user
):
    """Mirror K19d α M1 regression — offset beyond total returns empty
    rows but still reports correct total so the FE's "page 999 of 2"
    UI renders sensibly."""
    try:
        async with neo4j_driver.session() as session:
            for i in range(1, 4):
                await merge_event(
                    session, user_id=test_user, project_id="p-1",
                    title=f"E{i}", chapter_id="ch-1", event_order=i,
                )
            rows, total = await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=50, offset=100,
            )
        assert rows == []
        assert total == 3
    finally:
        await _cleanup(neo4j_driver, test_user)


@pytest.mark.asyncio
async def test_timeline_browse_validates_input(neo4j_driver, test_user):
    """Helper-level guards — router enforces these too but the repo
    double-checks so a misbehaving caller can't smuggle an invalid
    offset/limit through a direct import."""
    async with neo4j_driver.session() as session:
        with pytest.raises(ValueError, match="limit must be positive"):
            await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=0, offset=0,
            )
        with pytest.raises(ValueError, match="offset must be >= 0"):
            await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=None, before_order=None, limit=10, offset=-1,
            )
        with pytest.raises(
            ValueError, match="after_order .* must be < before_order"
        ):
            await list_events_filtered(
                session, user_id=test_user, project_id=None,
                after_order=5, before_order=5, limit=10, offset=0,
            )


# NOTE: the limit-clamp guarantee is proved at the unit layer in
# tests/unit/test_timeline_api.py::test_list_events_filtered_clamps_limit
# — asserting via live Neo4j would require seeding 200+ events just to
# discriminate clamp-fires vs clamp-missing, when a single patched
# `run_read` call gives deterministic evidence in milliseconds.
