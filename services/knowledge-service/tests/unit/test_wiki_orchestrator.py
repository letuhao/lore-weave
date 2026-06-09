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


def _job(entity_ids, *, items_done=None, max_spend=None, cost_spent="0") -> WikiGenJob:
    return WikiGenJob(
        job_id=uuid4(), user_id=uuid4(), project_id=uuid4(), book_id=uuid4(),
        status="pending", model_source="user_model", model_ref="m1",
        entity_ids=entity_ids, items_done=items_done or [],
        max_spend_usd=Decimal(max_spend) if max_spend else None,
        items_total=len(entity_ids), items_processed=0,
        cost_spent_usd=Decimal(cost_spent),
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


def _repo():
    r = MagicMock()
    r.mark_running = AsyncMock()
    r.mark_entity_done = AsyncMock()
    r.pause = AsyncMock()
    r.complete = AsyncMock()
    r.fail = AsyncMock()
    return r


def _ok_gen():
    g = MagicMock()
    g.status = "ok"
    g.ir = MagicMock()
    return g


def _patches(*, context=MagicMock(), gen=None):
    gen = gen or _ok_gen()
    return patch.multiple(
        "app.wiki.orchestrator",
        gather_entity_context=AsyncMock(return_value=context),
        generate_article=AsyncMock(return_value=gen),
        verify_article=AsyncMock(return_value=MagicMock()),
        revise_article=AsyncMock(return_value=(gen, MagicMock())),
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
        gather_entity_context=AsyncMock(side_effect=[RuntimeError("boom"), MagicMock()]),
        generate_article=AsyncMock(return_value=_ok_gen()),
        verify_article=AsyncMock(return_value=MagicMock()),
        revise_article=AsyncMock(side_effect=lambda **k: (_ok_gen(), MagicMock())),
        compose_provenance_cites=AsyncMock(return_value=[]),
        compute_build_inputs=MagicMock(return_value={}),
        build_writeback_body=MagicMock(return_value={}),
    ):
        status = await _run(job, clients, repo)
    assert status == "complete"  # e1 errored, e2 still processed
    assert clients.glossary.write_wiki_article.await_count == 1
