"""BootstrapService (PlanForge auto-bootstrap gate POC) integration tests.

Same real-Postgres convention as test_repositories.py (gated on
TEST_COMPOSITION_DB_URL) — the gate's persistence/state-machine logic is
real DB code, only the cross-service book-service call is faked (it isn't
running in this test context). See docs/specs/2026-07-06-planforge-auto-bootstrap.md.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import asyncpg
import pytest

from app.clients.book_client import BookClientError
from app.db.migrate import run_migrations
from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo
from app.db.repositories.plan_runs import PlanRunsRepo
from app.services.bootstrap_service import BootstrapService

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
)

_TABLES = ["plan_bootstrap_proposal", "plan_artifact", "plan_run"]


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await run_migrations(p)
        yield p
    finally:
        async with p.acquire() as c:
            for t in _TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        await p.close()


class FakeBookClient:
    """Fakes only the two book_client methods BootstrapService calls —
    `list_chapters` (propose's dedup source) and `create_chapter` (apply's
    mutation) — plus `get_book` for the original_language lookup."""

    def __init__(self, *, existing_chapters: list[dict[str, Any]] | None = None) -> None:
        self.existing_chapters = existing_chapters or []
        self.created: list[dict[str, Any]] = []
        self.fail_on_title: str | None = None
        self._next_chapter_id = 0

    async def get_book(self, book_id, bearer):
        return {"original_language": "vi"}

    async def list_chapters(self, book_id, bearer):
        return self.existing_chapters

    async def create_chapter(self, book_id, bearer, *, title, original_language):
        if title == self.fail_on_title:
            raise BookClientError(502, "BOOK_SERVICE_UNAVAILABLE", "simulated failure")
        self._next_chapter_id += 1
        chapter_id = f"chapter-{self._next_chapter_id}"
        self.created.append({"title": title, "original_language": original_language})
        return {"chapter_id": chapter_id, "title": title}


async def _run_with_package(pool, user, book, *, chapters: list[dict[str, Any]]):
    runs = PlanRunsRepo(pool)
    run = await runs.create(
        user, book, mode="rules", source_checksum="chk-poc",
        source_markdown="# plan", status="compiled",
    )
    await runs.save_artifact(
        user, run.id, "package",
        {"planning_package": {"arc_id": "arc_1", "chapters": chapters}},
    )
    return run


def _svc(pool, book_client) -> BootstrapService:
    return BootstrapService(PlanBootstrapProposalsRepo(pool), PlanRunsRepo(pool), book_client)


async def test_propose_excludes_existing_and_prior_applied_titles(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[
            {"event_id": "e1", "title": "Already In Book", "ordinal": 1},
            {"event_id": "e2", "title": "Already Applied", "ordinal": 2},
            {"event_id": "e3", "title": "Truly New", "ordinal": 3},
        ],
    )
    book_client = FakeBookClient(existing_chapters=[{"chapter_id": "x", "title": "Already In Book"}])
    svc = _svc(pool, book_client)

    # Simulate a PRIOR applied bootstrap for "Already Applied" (a separate record).
    prior_run = await _run_with_package(pool, user, book, chapters=[])
    proposals = PlanBootstrapProposalsRepo(pool)
    prior = await proposals.create(user, book, prior_run.id, diff={"new_chapters": []})
    await proposals.mark_approved(user, book, prior.id)
    await proposals.claim_for_apply(user, book, prior.id)
    await proposals.mark_item_applied(
        user, book, prior.id, item_key="e2",
        result={"chapter_id": "y", "title": "Already Applied"},
    )
    await proposals.mark_applied(user, book, prior.id)

    record = await svc.propose(user, book, run.id, bearer="tok")
    titles = {c["title"] for c in record.diff["new_chapters"]}
    assert titles == {"Truly New"}


async def test_propose_raises_without_compiled_package(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    runs = PlanRunsRepo(pool)
    run = await runs.create(
        user, book, mode="rules", source_checksum="chk-nopkg",
        source_markdown="# plan", status="pending",
    )
    svc = _svc(pool, FakeBookClient())
    with pytest.raises(ValueError, match="no compiled package"):
        await svc.propose(user, book, run.id, bearer="tok")


async def test_approve_then_apply_creates_chapters_and_records_results(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    book_client = FakeBookClient()
    svc = _svc(pool, book_client)

    proposed = await svc.propose(user, book, run.id, bearer="tok")
    approved = await svc.approve(user, book, proposed.id)
    assert approved.status == "approved"

    applied = await svc.apply(user, book, proposed.id, bearer="tok")
    assert applied.status == "applied"
    assert applied.applied_results["e1"]["chapter_id"] == "chapter-1"
    assert book_client.created == [{"title": "Chapter One", "original_language": "vi"}]


async def test_apply_before_approve_is_a_safe_readback_not_a_mutation(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    book_client = FakeBookClient()
    svc = _svc(pool, book_client)
    proposed = await svc.propose(user, book, run.id, bearer="tok")

    result = await svc.apply(user, book, proposed.id, bearer="tok")
    assert result.status == "pending"
    assert book_client.created == []


async def test_apply_twice_on_applied_record_is_a_safe_noop(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    book_client = FakeBookClient()
    svc = _svc(pool, book_client)
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    await svc.approve(user, book, proposed.id)
    first = await svc.apply(user, book, proposed.id, bearer="tok")
    assert first.status == "applied"

    second = await svc.apply(user, book, proposed.id, bearer="tok")
    assert second.status == "applied"
    assert len(book_client.created) == 1  # no double-create


async def test_apply_partial_failure_then_resume_only_retries_remaining_items(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[
            {"event_id": "e1", "title": "Chapter One", "ordinal": 1},
            {"event_id": "e2", "title": "Chapter Two", "ordinal": 2},
        ],
    )
    book_client = FakeBookClient()
    book_client.fail_on_title = "Chapter Two"
    svc = _svc(pool, book_client)
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    await svc.approve(user, book, proposed.id)

    with pytest.raises(BookClientError):
        await svc.apply(user, book, proposed.id, bearer="tok")

    failed = await svc.get(user, book, proposed.id)
    assert failed is not None and failed.status == "failed"
    assert "e1" in failed.applied_results
    assert "e2" not in failed.applied_results
    assert len(book_client.created) == 1

    book_client.fail_on_title = None
    resumed = await svc.apply(user, book, proposed.id, bearer="tok")
    assert resumed.status == "applied"
    assert set(resumed.applied_results.keys()) == {"e1", "e2"}
    # e1 was NOT re-created on resume — only e2 (the previously-failed item).
    assert len(book_client.created) == 2
