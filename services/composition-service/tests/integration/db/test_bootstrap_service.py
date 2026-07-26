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
from app.clients.glossary_client import GlossaryClientError
from app.db.migrate import run_migrations
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo
from app.db.repositories.plan_runs import PlanRunsRepo
from app.db.repositories.works import WorksRepo
from app.services.bootstrap_service import BootstrapService

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

_TABLES = [
    "plan_bootstrap_proposal", "plan_artifact", "generation_job", "plan_run",
    # composition_work is now seeded by _completed_pipeline_job (spec 25: a
    # generation_job derives book_id in-SQL from its Work partition), so the
    # fixture owns its cleanup too.
    "composition_work",
]


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
        self.fail_get_book: bool = False
        self._next_chapter_id = 0

    async def get_book(self, book_id, bearer):
        if self.fail_get_book:
            raise BookClientError(502, "BOOK_SERVICE_UNAVAILABLE", "simulated transient outage")
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


class FakeGlossaryClient:
    """Fakes `seed_entities_or_raise` — the only glossary_client method
    BootstrapService calls (M2)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_with: GlossaryClientError | None = None
        self._next_entity_id = 0

    async def seed_entities_or_raise(self, book_id, *, source_language, entities):
        self.calls.append({"source_language": source_language, "entities": list(entities)})
        if self.fail_with is not None:
            raise self.fail_with
        out = []
        for e in entities:
            self._next_entity_id += 1
            out.append({
                "entity_id": f"entity-{self._next_entity_id}",
                "name": e["name"], "kind_code": e.get("kind_code") or "character",
                "status": "created",
            })
        return out


async def _run_with_package(
    pool, user, book, *,
    chapters: list[dict[str, Any]], glossary_seeds: list[dict[str, Any]] | None = None,
):
    runs = PlanRunsRepo(pool)
    run = await runs.create(
        user, book, mode="rules", source_checksum="chk-poc",
        source_markdown="# plan", status="compiled",
    )
    await runs.save_artifact(
        user, run.id, "package",
        {
            "planning_package": {"arc_id": "arc_1", "chapters": chapters},
            "glossary_seeds": glossary_seeds or [],
        },
    )
    return run


def _svc(pool, book_client, glossary_client=None) -> BootstrapService:
    return BootstrapService(
        PlanBootstrapProposalsRepo(pool), PlanRunsRepo(pool),
        book_client, glossary_client or FakeGlossaryClient(), GenerationJobsRepo(pool),
    )


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
    prior = await proposals.create(
        user, book, prior_run.id,
        diff={"new_chapters": [{"event_id": "e2", "title": "Already Applied", "ordinal": 1}]},
    )
    await proposals.mark_approved(book, prior.id)
    await proposals.claim_for_apply(book, prior.id)
    await proposals.mark_item_applied(
        book, prior.id, item_key="e2",
        result={"chapter_id": "y", "title": "Already Applied"},
    )
    await proposals.mark_applied(book, prior.id)

    record = await svc.propose(user, book, run.id, bearer="tok")
    titles = {c["title"] for c in record.diff["new_chapters"]}
    assert titles == {"Truly New"}


async def test_propose_twice_before_applying_does_not_double_offer(pool):
    """M1 hardening: the POC's POST-REVIEW found that dedup scoped to only
    'applied' records let a second propose() (before the first is applied)
    silently re-offer — and if both got approved+applied, double-create —
    the same chapters. Dedup must also cover PENDING/APPROVED proposals."""
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    svc = _svc(pool, FakeBookClient())

    first = await svc.propose(user, book, run.id, bearer="tok")
    assert {c["title"] for c in first.diff["new_chapters"]} == {"Chapter One"}

    second = await svc.propose(user, book, run.id, bearer="tok")
    assert second.diff["new_chapters"] == []  # already claimed by `first`, still pending

    # Rejecting the first FREES its claim — a fresh propose can re-offer it.
    await svc.reject(book, first.id)
    third = await svc.propose(user, book, run.id, bearer="tok")
    assert {c["title"] for c in third.diff["new_chapters"]} == {"Chapter One"}


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
    approved = await svc.approve(book, proposed.id)
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
    await svc.approve(book, proposed.id)
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
    await svc.approve(book, proposed.id)

    with pytest.raises(BookClientError):
        await svc.apply(user, book, proposed.id, bearer="tok")

    failed = await svc.get(book, proposed.id)
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


# ── M2: real glossary wiring ──────────────────────────────────────────────

async def test_propose_includes_glossary_seeds_deduped_across_active_proposals(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book, chapters=[],
        glossary_seeds=[
            {"name": "Lin Feng", "kind_code": "character", "attributes": {"role": "protagonist"}},
            {"name": "Perfection Addiction", "kind_code": "concept", "attributes": {}},
        ],
    )
    svc = _svc(pool, FakeBookClient())

    first = await svc.propose(user, book, run.id, bearer="tok")
    names = {e["name"] for e in first.diff["new_glossary_entities"]}
    assert names == {"Lin Feng", "Perfection Addiction"}

    # A second propose before applying the first must not re-offer the same
    # entities (same M1 race-guard, extended to glossary items).
    second = await svc.propose(user, book, run.id, bearer="tok")
    assert second.diff["new_glossary_entities"] == []


async def test_approve_then_apply_seeds_glossary_entities(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book, chapters=[],
        glossary_seeds=[{"name": "Lin Feng", "kind_code": "character", "attributes": {}}],
    )
    glossary = FakeGlossaryClient()
    svc = _svc(pool, FakeBookClient(), glossary)

    proposed = await svc.propose(user, book, run.id, bearer="tok")
    await svc.approve(book, proposed.id)
    applied = await svc.apply(user, book, proposed.id, bearer="tok")

    assert applied.status == "applied"
    key = "glossary:character:Lin Feng"
    assert applied.applied_results[key]["entity_id"] == "entity-1"
    assert glossary.calls == [{"source_language": "vi", "entities": [
        {"name": "Lin Feng", "kind_code": "character", "attributes": {}},
    ]}]


async def test_apply_surfaces_book_not_adopted_as_actionable_422(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book, chapters=[],
        glossary_seeds=[{"name": "Lin Feng", "kind_code": "character", "attributes": {}}],
    )
    glossary = FakeGlossaryClient()
    glossary.fail_with = GlossaryClientError(422, "GLOSS_BOOK_NOT_SCAFFOLDED", "not adopted")
    svc = _svc(pool, FakeBookClient(), glossary)
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    await svc.approve(book, proposed.id)

    with pytest.raises(GlossaryClientError) as exc_info:
        await svc.apply(user, book, proposed.id, bearer="tok")
    assert exc_info.value.code == "GLOSS_BOOK_NOT_SCAFFOLDED"
    assert "Graph Schema" in exc_info.value.detail

    failed = await svc.get(book, proposed.id)
    assert failed is not None and failed.status == "failed"
    assert "Graph Schema" in failed.error_detail

    # Retry after "adopting" (the fake stops failing) resumes and succeeds.
    glossary.fail_with = None
    resumed = await svc.apply(user, book, proposed.id, bearer="tok")
    assert resumed.status == "applied"


async def test_apply_chapters_and_glossary_together_both_recorded(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
        glossary_seeds=[{"name": "Lin Feng", "kind_code": "character", "attributes": {}}],
    )
    book_client = FakeBookClient()
    glossary = FakeGlossaryClient()
    svc = _svc(pool, book_client, glossary)
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    await svc.approve(book, proposed.id)

    applied = await svc.apply(user, book, proposed.id, bearer="tok")
    assert applied.status == "applied"
    assert set(applied.applied_results.keys()) == {"e1", "glossary:character:Lin Feng"}


# ── M3: scene/beat drafting context (reads an ALREADY-COMPLETED plan_pipeline
# job — this gate never triggers that pipeline itself, so propose() stays
# zero-LLM-call regardless of whether one was run) ──────────────────────────

_PIPELINE_RESULT_FIXTURE = {
    "decompose": {
        "arc_title": "Arc 1",
        "chapters": [
            {
                "chapter": {"chapter_id": "e1", "title": "Chapter One", "sort_order": 1,
                            "beat_role": None, "intent": ""},
                "scenes": [
                    {"title": "Opening", "synopsis": "Hero wakes up powerless.", "tension": 20,
                     "present_entity_ids": [], "present_entity_names_unresolved": [], "suggested_k": 1},
                    {"title": "The Call", "synopsis": "A mysterious letter arrives.", "tension": 40,
                     "present_entity_ids": [], "present_entity_names_unresolved": [], "suggested_k": 1},
                ],
            },
        ],
    },
}


async def _completed_pipeline_job(pool, user, project_id, result=None):
    # Package re-key (spec 25): generation_job.book_id is NOT NULL and derived
    # in-SQL from composition_work, so the Work partition must exist first.
    # `created_by` is a plain actor stamp; the job is later looked up by id only.
    await WorksRepo(pool).create(user, project_id, uuid.uuid4())
    jobs = GenerationJobsRepo(pool)
    job, _ = await jobs.create(
        project_id, created_by=user, operation="plan_pipeline", mode="auto",
        status="pending", input={},
    )
    await jobs.update_status(job.id, "completed", result=result or _PIPELINE_RESULT_FIXTURE)
    return job


async def test_propose_attaches_drafting_guide_from_completed_pipeline_job(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    job = await _completed_pipeline_job(pool, user, uuid.uuid4())
    await PlanRunsRepo(pool).update_run(
        book, run.id, checkpoint_state={"pipeline_job_id": str(job.id)},
    )

    svc = _svc(pool, FakeBookClient())
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    guide = proposed.diff["new_chapters"][0]["drafting_guide"]
    assert "Hero wakes up powerless." in guide
    assert "A mysterious letter arrives." in guide


async def test_apply_carries_drafting_guide_into_applied_results(pool):
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    job = await _completed_pipeline_job(pool, user, uuid.uuid4())
    await PlanRunsRepo(pool).update_run(
        book, run.id, checkpoint_state={"pipeline_job_id": str(job.id)},
    )
    svc = _svc(pool, FakeBookClient())

    proposed = await svc.propose(user, book, run.id, bearer="tok")
    await svc.approve(book, proposed.id)
    applied = await svc.apply(user, book, proposed.id, bearer="tok")

    assert "Hero wakes up powerless." in applied.applied_results["e1"]["drafting_guide"]


async def test_propose_without_a_pipeline_job_has_no_drafting_guide(pool):
    """The common case: no run_pipeline=true was ever requested — chapters
    are proposed exactly as before M3, with no drafting_guide key at all."""
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    svc = _svc(pool, FakeBookClient())
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    assert "drafting_guide" not in proposed.diff["new_chapters"][0]


# ── /review-impl fixes ──────────────────────────────────────────────────────

async def test_propose_with_a_malformed_pipeline_job_id_still_succeeds(pool):
    """LOW: an optional M3 enhancement (the drafting-guide lookup) must never
    break the REQUIRED propose() behavior. Before the fix, UUID(pipeline_job_id)
    raised unguarded on a malformed id, aborting the whole call."""
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    await PlanRunsRepo(pool).update_run(
        book, run.id, checkpoint_state={"pipeline_job_id": "not-a-real-uuid"},
    )
    svc = _svc(pool, FakeBookClient())
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    assert {c["title"] for c in proposed.diff["new_chapters"]} == {"Chapter One"}
    assert "drafting_guide" not in proposed.diff["new_chapters"][0]


async def test_apply_get_book_failure_marks_failed_not_stuck_applying(pool):
    """HIGH (/review-impl): get_book() used to sit OUTSIDE apply()'s try block,
    so a transient book-service failure there left the record stuck at
    status='applying' forever — un-retriable, since claim_for_apply only
    re-claims from 'approved'/'failed'. Proves the fix: the record reaches
    'failed' (resumable), and a retry once the outage clears succeeds."""
    user, book = uuid.uuid4(), uuid.uuid4()
    run = await _run_with_package(
        pool, user, book,
        chapters=[{"event_id": "e1", "title": "Chapter One", "ordinal": 1}],
    )
    book_client = FakeBookClient()
    book_client.fail_get_book = True
    svc = _svc(pool, book_client)
    proposed = await svc.propose(user, book, run.id, bearer="tok")
    await svc.approve(book, proposed.id)

    with pytest.raises(BookClientError):
        await svc.apply(user, book, proposed.id, bearer="tok")

    failed = await svc.get(book, proposed.id)
    assert failed is not None and failed.status == "failed"
    assert failed.error_detail and "simulated transient outage" in failed.error_detail

    # The record is NOT stuck — it's resumable once the outage clears.
    book_client.fail_get_book = False
    resumed = await svc.apply(user, book, proposed.id, bearer="tok")
    assert resumed.status == "applied"
    assert resumed.applied_results["e1"]["chapter_id"] == "chapter-1"
