"""Unit tests for the wiki-gen orchestrator (wiki-llm M6).

The pipeline stages (gather/generate/verify/revise/cite/build) are patched at the
orchestrator module so this isolates the LOOP logic: multi-entity drive,
skip-on-resume (items_done), per-article budget pause, skip-on-empty-context,
writeback-failure (not marked done), never-crash-on-entity-error.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.repositories.wiki_gen_jobs import WikiGenJob
from app.wiki.orchestrator import OrchestratorClients, run_wiki_gen_job


def _job(entity_ids, *, items_done=None, max_spend=None, cost_spent="0",
         revise_model_ref=None, revise_model_source=None) -> WikiGenJob:
    return WikiGenJob(
        job_id=uuid4(), user_id=uuid4(), project_id=uuid4(), book_id=uuid4(),
        status="pending", model_source="user_model", model_ref="m1",
        entity_ids=entity_ids, items_done=items_done or [],
        max_spend_usd=Decimal(max_spend) if max_spend else None,
        items_total=len(entity_ids), items_processed=0,
        cost_spent_usd=Decimal(cost_spent),
        revise_model_ref=revise_model_ref, revise_model_source=revise_model_source,
    )


def _clients(write_action="written"):
    glossary = MagicMock()
    glossary.write_wiki_article = AsyncMock(
        return_value={"action": write_action} if write_action else None)
    bp = MagicMock()
    bp.get_profile = AsyncMock(return_value=MagicMock())
    return OrchestratorClients(
        glossary=glossary, book=MagicMock(), embedding=MagicMock(),
        reranker=MagicMock(), llm=MagicMock(), book_profile=bp)


def _repo(*, status_reads=None):
    r = MagicMock()
    r.mark_running = AsyncMock()
    r.mark_entity_done = AsyncMock()
    r.pause = AsyncMock()
    r.complete = AsyncMock()
    r.fail = AsyncMock()
    # W4a — per-entity result + live-progress writes the orchestrator now drives.
    r.record_result = AsyncMock()
    r.set_progress = AsyncMock()
    # D-WIKI-M7B — the between-entity status poll. Default: always 'running' (no
    # external control → the loop runs to completion). A test can script a sequence
    # via `status_reads` to simulate a mid-run cancel/pause.
    if status_reads is not None:
        r.read_status = AsyncMock(side_effect=status_reads)
    else:
        r.read_status = AsyncMock(return_value="running")
    return r


def _ok_gen():
    g = MagicMock()
    g.status = "ok"
    g.ir = MagicMock()
    return g


_UNSET = object()


def _ctx(name="Mina"):
    """A context mock with a real string ``brief.name`` (the result-name source)."""
    c = MagicMock()
    c.brief.name = name
    return c


def _verify(flags=0):
    v = MagicMock()
    v.flag_count = flags
    return v


def _patches(*, context=_UNSET, gen=None):
    gen = gen or _ok_gen()
    ctx = _ctx() if context is _UNSET else context
    verify = _verify()
    return patch.multiple(
        "app.wiki.orchestrator",
        gather_entity_context=AsyncMock(return_value=ctx),
        generate_article=AsyncMock(return_value=gen),
        verify_article=AsyncMock(return_value=verify),
        revise_article=AsyncMock(return_value=(gen, verify)),
        compose_provenance_cites=AsyncMock(return_value=[]),
        compute_build_inputs=MagicMock(return_value={}),
        build_writeback_body=MagicMock(return_value={}),
    )


async def _run(job, clients, repo):
    return await run_wiki_gen_job(
        job, repo=repo, project=MagicMock(), clients=clients,
        retrieval_params={}, prompt_version="p", pipeline_version="v",
        cost_per_article_usd=Decimal("0.05"),
    )


@pytest.mark.asyncio
async def test_happy_multi_entity():
    job, clients, repo = _job(["e1", "e2", "e3"]), _clients(), _repo()
    with _patches():
        status = await _run(job, clients, repo)
    assert status == "complete"
    assert repo.mark_entity_done.await_count == 3
    assert clients.glossary.write_wiki_article.await_count == 3
    repo.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_running_cancel_stops_mid_loop():
    """D-WIKI-M7B: an external cancel mid-run (status flips to 'cancelled' between
    entities) stops the loop PROMPTLY — the remaining entities are not generated
    (no wasted tokens) and the job does not complete()."""
    # poll #1 (before e1) → running; poll #2 (before e2) → cancelled → stop.
    job = _job(["e1", "e2", "e3"])
    clients, repo = _clients(), _repo(status_reads=["running", "cancelled"])
    with _patches():
        status = await _run(job, clients, repo)
    assert status == "cancelled"
    assert repo.mark_entity_done.await_count == 1  # only e1 completed before the cancel
    # only e1 was generated+written — e2/e3 never ran (the token-saving stop).
    assert clients.glossary.write_wiki_article.await_count == 1
    repo.complete.assert_not_awaited()  # a cancelled job must NOT be completed


@pytest.mark.asyncio
async def test_running_cancel_before_first_entity_does_nothing():
    """A cancel that lands before the first entity stops with zero work done."""
    job = _job(["e1", "e2"])
    clients, repo = _clients(), _repo(status_reads=["cancelled"])
    with _patches():
        status = await _run(job, clients, repo)
    assert status == "cancelled"
    assert repo.mark_entity_done.await_count == 0
    assert clients.glossary.write_wiki_article.await_count == 0  # nothing generated
    repo.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_pause_mid_loop_is_resumable():
    """An external manual pause mid-run stops resumable (items_done persisted)."""
    job = _job(["e1", "e2", "e3"])
    clients, repo = _clients(), _repo(status_reads=["running", "paused"])
    with _patches():
        status = await _run(job, clients, repo)
    assert status == "paused"
    assert repo.mark_entity_done.await_count == 1
    repo.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_already_done():
    job, clients, repo = _job(["e1", "e2"], items_done=["e1"]), _clients(), _repo()
    with _patches():
        await _run(job, clients, repo)
    # only e2 generated
    assert clients.glossary.write_wiki_article.await_count == 1
    assert repo.mark_entity_done.await_count == 1


@pytest.mark.asyncio
async def test_budget_pause():
    # cap 0.08, cost 0.05/article → 1 fits, the 2nd would breach → pause before it.
    job, clients, repo = _job(["e1", "e2", "e3"], max_spend="0.08"), _clients(), _repo()
    with _patches():
        status = await _run(job, clients, repo)
    assert status == "paused"
    repo.pause.assert_awaited_once()
    assert clients.glossary.write_wiki_article.await_count == 1  # only e1 written
    repo.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_skips_when_no_context():
    job, clients, repo = _job(["e1"]), _clients(), _repo()
    with _patches(context=None):  # gather returns None → skip
        await _run(job, clients, repo)
    clients.glossary.write_wiki_article.assert_not_awaited()
    # a skip still advances (cost 0) so a resume doesn't re-attempt forever
    repo.mark_entity_done.assert_awaited_once()


@pytest.mark.asyncio
async def test_writeback_failure_not_marked_done():
    # write_wiki_article returns None → entity left NOT done (resume retries), no charge.
    job, clients, repo = _job(["e1"]), _clients(write_action=None), _repo()
    with _patches():
        status = await _run(job, clients, repo)
    assert status == "complete"
    repo.mark_entity_done.assert_not_awaited()


@pytest.mark.asyncio
async def test_aborts_when_not_claimable():
    # M7b /review-impl F1 — a concurrent cancel flipped the job to 'cancelled'
    # before mark_running; the claim returns False → abort WITHOUT running any
    # entity (no resurrect, no token spend), and don't mark it complete.
    job, clients, repo = _job(["e1", "e2"]), _clients(), _repo()
    repo.mark_running = AsyncMock(return_value=False)
    with _patches():
        status = await _run(job, clients, repo)
    assert status == "cancelled"
    clients.glossary.write_wiki_article.assert_not_awaited()
    repo.mark_entity_done.assert_not_awaited()
    repo.complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_gen_not_ok_skips():
    bad = MagicMock()
    bad.status = "llm_failed"
    bad.ir = None
    job, clients, repo = _job(["e1"]), _clients(), _repo()
    with _patches(gen=bad):
        await _run(job, clients, repo)
    clients.glossary.write_wiki_article.assert_not_awaited()
    repo.mark_entity_done.assert_awaited_once()  # skip advances


@pytest.mark.asyncio
async def test_entity_error_does_not_crash_batch():
    job, clients, repo = _job(["e1", "e2"]), _clients(), _repo()
    with patch.multiple(
        "app.wiki.orchestrator",
        gather_entity_context=AsyncMock(side_effect=[RuntimeError("boom"), _ctx()]),
        generate_article=AsyncMock(return_value=_ok_gen()),
        verify_article=AsyncMock(return_value=_verify()),
        revise_article=AsyncMock(side_effect=lambda **k: (_ok_gen(), _verify())),
        compose_provenance_cites=AsyncMock(return_value=[]),
        compute_build_inputs=MagicMock(return_value={}),
        build_writeback_body=MagicMock(return_value={}),
    ):
        status = await _run(job, clients, repo)
    assert status == "complete"  # e1 errored, e2 still processed
    assert clients.glossary.write_wiki_article.await_count == 1
    # the errored entity is recorded so the table shows it (not silently absent)
    err = [c.args[2]["outcome"] for c in repo.record_result.await_args_list]
    assert "error" in err


# ── W4a: per-entity results + live sub-step progress ──────────────────────────


@pytest.mark.asyncio
async def test_records_results_and_advances_passes():
    job, clients, repo = _job(["e1", "e2"]), _clients(), _repo()
    with _patches():
        await _run(job, clients, repo)
    outcomes = [c.args[2]["outcome"] for c in repo.record_result.await_args_list]
    # one preliminary 'processing' + one final 'written' per entity
    assert outcomes.count("processing") == 2
    assert outcomes.count("written") == 2
    # final rows carry the entity name (the table title)
    finals = [c.args[2] for c in repo.record_result.await_args_list if c.args[2]["outcome"] == "written"]
    assert all(f["name"] == "Mina" for f in finals)
    # the live pass pointer advanced through the whole pipeline for the first entity
    passes = [c.args[2] for c in repo.set_progress.await_args_list]
    assert passes[:5] == ["context", "generate", "verify", "revise", "writeback"]


@pytest.mark.asyncio
async def test_records_citation_and_flag_counts():
    # /review-impl #4 — pin the capture: citations = len(cites), flags = verify.flag_count.
    job, clients, repo = _job(["e1"]), _clients(), _repo()
    verify = _verify(flags=2)
    with patch.multiple(
        "app.wiki.orchestrator",
        gather_entity_context=AsyncMock(return_value=_ctx()),
        generate_article=AsyncMock(return_value=_ok_gen()),
        verify_article=AsyncMock(return_value=verify),
        revise_article=AsyncMock(return_value=(_ok_gen(), verify)),
        compose_provenance_cites=AsyncMock(return_value=["c1", "c2", "c3"]),
        compute_build_inputs=MagicMock(return_value={}),
        build_writeback_body=MagicMock(return_value={}),
    ):
        await _run(job, clients, repo)
    written = [c.args[2] for c in repo.record_result.await_args_list if c.args[2]["outcome"] == "written"]
    assert len(written) == 1
    assert written[0]["citations"] == 3
    assert written[0]["flags"] == 2


@pytest.mark.asyncio
async def test_skip_no_context_records_skipped_without_processing():
    job, clients, repo = _job(["e1"]), _clients(), _repo()
    with _patches(context=None):  # no grounding → no name, no preliminary row
        await _run(job, clients, repo)
    outcomes = [c.args[2]["outcome"] for c in repo.record_result.await_args_list]
    assert outcomes == ["skipped"]


@pytest.mark.asyncio
async def test_writeback_failure_is_recorded():
    job, clients, repo = _job(["e1"]), _clients(write_action=None), _repo()
    with _patches():
        await _run(job, clients, repo)
    finals = [c.args[2]["outcome"] for c in repo.record_result.await_args_list]
    assert "writeback_failed" in finals  # recorded even though not marked done


# ── W5: the corrective revise can use a separate model ────────────────────────


def _patched_revise():
    """A patch.multiple context that exposes the revise_article mock for kwargs asserts."""
    revise = AsyncMock(side_effect=lambda **k: (_ok_gen(), _verify()))
    ctx = patch.multiple(
        "app.wiki.orchestrator",
        gather_entity_context=AsyncMock(return_value=_ctx()),
        generate_article=AsyncMock(return_value=_ok_gen()),
        verify_article=AsyncMock(return_value=_verify()),
        revise_article=revise,
        compose_provenance_cites=AsyncMock(return_value=[]),
        compute_build_inputs=MagicMock(return_value={}),
        build_writeback_body=MagicMock(return_value={}),
    )
    return ctx, revise


@pytest.mark.asyncio
async def test_revise_uses_override_model_when_set():
    job, clients, repo = _job(["e1"], revise_model_ref="rm", revise_model_source="user_model"), _clients(), _repo()
    ctx, revise = _patched_revise()
    with ctx:
        await _run(job, clients, repo)
    assert revise.await_args.kwargs["model_ref"] == "rm"
    assert revise.await_args.kwargs["model_source"] == "user_model"


@pytest.mark.asyncio
async def test_revise_falls_back_to_prose_model_when_unset():
    job, clients, repo = _job(["e1"]), _clients(), _repo()  # no revise override
    ctx, revise = _patched_revise()
    with ctx:
        await _run(job, clients, repo)
    # the prose model (m1/user_model) drives the revise when no override is set
    assert revise.await_args.kwargs["model_ref"] == "m1"
    assert revise.await_args.kwargs["model_source"] == "user_model"


@pytest.mark.asyncio
async def test_revise_source_defaults_when_ref_set_without_source():
    job, clients, repo = _job(["e1"], revise_model_ref="rm"), _clients(), _repo()  # ref but no source
    ctx, revise = _patched_revise()
    with ctx:
        await _run(job, clients, repo)
    assert revise.await_args.kwargs["model_ref"] == "rm"
    assert revise.await_args.kwargs["model_source"] == "user_model"  # paired default
