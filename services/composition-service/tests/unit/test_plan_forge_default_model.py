"""D-PLANFORGE-DEFAULT-MODEL — PlanForgeService.create_run's model_ref
resolution + its interaction with the checksum/mode dedupe gate.

Coverage gap this closes (found in /review-impl): the dedupe check must compare
against the RESOLVED model_ref, not the caller's (possibly omitted) one -- two
LLM-mode proposes for identical text that both omit model_ref must dedupe
against each other (both resolve to the same server-side default), not each
silently re-run a billed LLM propose.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.models import CompositionWork, GenerationJob, PlanRun
from app.services.plan_forge_service import PlanForgeService

USER = uuid4()
BOOK = uuid4()
DEFAULT_MODEL = uuid4()
EXPLICIT_MODEL = uuid4()


def _run(**over) -> PlanRun:
    base = dict(
        id=uuid4(), created_by=USER, book_id=BOOK, mode="llm",
        model_ref=DEFAULT_MODEL, source_checksum="chk", status="proposed",
    )
    base.update(over)
    return PlanRun(**base)


def _job() -> GenerationJob:
    return GenerationJob(id=uuid4(), created_by=USER, project_id=uuid4(), book_id=BOOK,
                         operation="plan_forge_propose")


def _svc(*, find_by_checksum_return=None, llm_resolve_return=str(DEFAULT_MODEL)):
    """A PlanForgeService wired to fully-mocked repos, pre-configured so the
    `mode="llm"` worker-enabled propose path (create -> _ensure_work ->
    _jobs.create -> enqueue_job) runs end to end without touching real infra."""
    runs = AsyncMock()
    runs.find_by_checksum.return_value = find_by_checksum_return
    runs.create.return_value = _run()
    runs.get_for_book.return_value = _run()

    works = AsyncMock()
    works.resolve_by_book.return_value = []
    works.get_pending_for_book.return_value = None
    works.create_pending.return_value = CompositionWork(
        id=uuid4(), created_by=USER, book_id=BOOK, project_id=uuid4(),
    )

    jobs = AsyncMock()
    jobs.create.return_value = (_job(), False)

    llm = AsyncMock()
    llm.resolve_planner_model.return_value = llm_resolve_return

    svc = PlanForgeService(runs, jobs, works, llm=llm)
    # O-1 added a book-state grounding read to the llm-propose path; these tests exercise
    # model_ref resolution + dedupe over MOCKED repos (no real pool), so stub the grounding to
    # pass the source through unchanged — grounding has its own effect test in test_repositories.
    svc._ground_llm_source = AsyncMock(side_effect=lambda _b, t: t)
    return svc, runs, jobs, works, llm


@pytest.mark.asyncio
async def test_omitted_model_ref_resolves_before_the_dedupe_lookup(monkeypatch):
    """The dedupe query must run with the RESOLVED model_ref, not None -- proves
    the fix ordering (resolve, then find_by_checksum), not just that resolve runs."""
    svc, runs, jobs, works, llm = _svc()
    call_order: list[str] = []

    async def _find_by_checksum(*a, **k):
        call_order.append("find_by_checksum")
        return None
    runs.find_by_checksum.side_effect = _find_by_checksum

    async def _resolve(*a, **k):
        call_order.append("resolve")
        return str(DEFAULT_MODEL)
    llm.resolve_planner_model.side_effect = _resolve

    monkeypatch.setattr("app.services.plan_forge_service.settings.composition_worker_enabled", True)
    monkeypatch.setattr("app.services.plan_forge_service.enqueue_job", AsyncMock())

    await svc.create_run(
        USER, BOOK, source_markdown="same text", mode="llm", model_ref=None,
    )

    assert call_order == ["resolve", "find_by_checksum"]
    runs.find_by_checksum.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_omitted_model_ref_proposes_for_identical_text_dedupe():
    """The actual regression: retry #2 (same text, no model_ref, no `force`) must
    reuse retry #1's run -- NOT re-run the LLM propose a second time."""
    existing = _run(model_ref=DEFAULT_MODEL, status="proposed")
    svc, runs, jobs, works, llm = _svc(find_by_checksum_return=existing)
    runs.get_for_book.return_value = existing

    result_run, is_async, job_id = await svc.create_run(
        USER, BOOK, source_markdown="same text", mode="llm", model_ref=None,
    )

    # Reused the existing run (sync_from_job path) -- never called runs.create.
    runs.create.assert_not_awaited()
    assert result_run.id == existing.id
    assert is_async is False


@pytest.mark.asyncio
async def test_no_default_model_available_raises_clear_error():
    svc, runs, jobs, works, llm = _svc(llm_resolve_return=None)

    with pytest.raises(ValueError, match="no default chat model is set"):
        await svc.create_run(
            USER, BOOK, source_markdown="text", mode="llm", model_ref=None,
        )
    runs.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_model_ref_skips_resolution_entirely(monkeypatch):
    svc, runs, jobs, works, llm = _svc(find_by_checksum_return=None)
    monkeypatch.setattr("app.services.plan_forge_service.settings.composition_worker_enabled", True)
    monkeypatch.setattr("app.services.plan_forge_service.enqueue_job", AsyncMock())

    await svc.create_run(
        USER, BOOK, source_markdown="text", mode="llm", model_ref=EXPLICIT_MODEL,
    )

    llm.resolve_planner_model.assert_not_awaited()
    assert runs.create.await_args.kwargs["model_ref"] == EXPLICIT_MODEL
