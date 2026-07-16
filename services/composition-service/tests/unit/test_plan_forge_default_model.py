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


# ── close-21-28 D-G5-DRIVE-EXEC — rules-mode propose auto-compile (flag-gated) ────────────────
#
# The S06 flagship exposed that a weak agent reliably PROPOSES a valid rules spec but drops the
# follow-up plan_compile call (DR-G5-REROLL: 6 live gemma-4 rolls proposed, 0 chained the compile),
# and the rail drive holds+re-prompts but by G1 design does not execute the deterministic step.
# `planforge_rules_autocompile` (deploy ceiling, default OFF) closes it: a rules propose that parses
# ≥1 arc compiles every arc inline. These two tests pin BOTH sides of the flag — the write-only-
# behavior bug (a flag consumed by nothing) and the HIL-preservation (OFF must not auto-compile).


class _Spec:
    def __init__(self, arcs):
        self.content = {"arcs": arcs}


@pytest.mark.asyncio
async def test_rules_autocompile_on_compiles_every_parsed_arc(monkeypatch):
    """Flag ON: a rules propose that parses arcs auto-compiles EACH one inline — structure
    materialises with the propose, not on a second call the weak model drops."""
    svc, runs, jobs, works, llm = _svc()
    runs.get_for_book.return_value = _run(mode="rules", status="proposed")
    # The real transcription is exercised elsewhere; here we drive only the flag→compile wiring.
    svc._finalize_rules_propose = AsyncMock()
    runs.latest_artifact.return_value = _Spec([{"id": "arc_1"}, {"id": "arc_2"}, {"id": "arc_3"}])
    svc.compile = AsyncMock(return_value=("sync", {}))
    monkeypatch.setattr(
        "app.db.repositories.structure.StructureRepo", _fake_structure_repo([]),
    )  # cold-start book ⇒ the P-O1a pre-flight is a no-op, autocompile fires
    monkeypatch.setattr(
        "app.services.plan_forge_service.settings.planforge_rules_autocompile", True,
    )

    await svc.create_run(
        USER, BOOK, source_markdown="# 1. Arc Overview\n## A\n### b", mode="rules", model_ref=None,
    )

    assert svc.compile.await_count == 3  # one deterministic compile per parsed arc
    compiled = {c.kwargs["arc_id"] for c in svc.compile.await_args_list}
    assert compiled == {"arc_1", "arc_2", "arc_3"}


@pytest.mark.asyncio
async def test_rules_autocompile_off_preserves_hil(monkeypatch):
    """Flag OFF (the default): a rules propose does NOT auto-compile — the GUI's
    propose→review→compile flow is unchanged."""
    svc, runs, jobs, works, llm = _svc()
    runs.get_for_book.return_value = _run(mode="rules", status="proposed")
    svc._finalize_rules_propose = AsyncMock()
    svc.compile = AsyncMock()
    monkeypatch.setattr(
        "app.db.repositories.structure.StructureRepo", _fake_structure_repo([]),
    )
    monkeypatch.setattr(
        "app.services.plan_forge_service.settings.planforge_rules_autocompile", False,
    )

    await svc.create_run(
        USER, BOOK, source_markdown="# 1. Arc Overview\n## A\n### b", mode="rules", model_ref=None,
    )

    svc.compile.assert_not_awaited()


# ── close-21-28 P-O1a — the RULES-mode pre-flight (autocompile-ON safety guard) ───────────────
#
# With autocompile ON, a rules propose on a book that ALREADY has arcs would silently materialise
# arcs that PARALLEL the book's existing ones. The pre-flight holds the auto-compile when the book has
# arcs (a collision to review) and lets a cold-start book auto-compile unchanged.


class _Arc:
    def __init__(self, title):
        self.kind, self.title = "arc", title


def _fake_structure_repo(arcs):
    class _R:
        def __init__(self, _pool):
            pass

        async def list_tree(self, _book_id):
            return arcs

    return _R


@pytest.mark.asyncio
async def test_rules_preflight_cold_start_autocompiles(monkeypatch):
    """Cold-start book (no existing arcs) ⇒ no collision ⇒ autocompile fires as before."""
    svc, runs, jobs, works, llm = _svc()
    runs.get_for_book.return_value = _run(mode="rules", status="proposed")
    svc._finalize_rules_propose = AsyncMock()
    runs.latest_artifact.return_value = _Spec([{"id": "arc_1", "title": "A"}])
    svc.compile = AsyncMock(return_value=("sync", {}))
    monkeypatch.setattr("app.db.repositories.structure.StructureRepo", _fake_structure_repo([]))
    monkeypatch.setattr("app.services.plan_forge_service.settings.planforge_rules_autocompile", True)

    await svc.create_run(USER, BOOK, source_markdown="# 1. Arc Overview\n## A", mode="rules", model_ref=None)

    svc.compile.assert_awaited()  # cold start → auto-materialised


@pytest.mark.asyncio
async def test_rules_preflight_midbook_collision_holds_autocompile(monkeypatch):
    """Book already has arcs ⇒ the pre-flight reports a collision + HOLDS the auto-compile (the author
    must compile explicitly), even with the flag ON."""
    svc, runs, jobs, works, llm = _svc()
    runs.get_for_book.return_value = _run(mode="rules", status="proposed")
    svc._finalize_rules_propose = AsyncMock()
    runs.latest_artifact.return_value = _Spec([{"id": "arc_1", "title": "A Brand New Arc"}])
    svc.compile = AsyncMock()
    monkeypatch.setattr(
        "app.db.repositories.structure.StructureRepo", _fake_structure_repo([_Arc("An Existing Arc")]),
    )
    monkeypatch.setattr("app.services.plan_forge_service.settings.planforge_rules_autocompile", True)

    await svc.create_run(USER, BOOK, source_markdown="# 1. Arc Overview\n## A", mode="rules", model_ref=None)

    svc.compile.assert_not_awaited()  # collision → auto-compile HELD
    saved_kinds = [c.args[2] for c in runs.save_artifact.await_args_list if len(c.args) >= 3]
    assert "preflight" in saved_kinds  # the collision report was persisted for the FE/agent
