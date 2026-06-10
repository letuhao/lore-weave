"""wiki-llm M6 — wiki-gen stream consumer (flag-gated, off by default).

A thin background loop: blocking-XREAD the ``loreweave:events:wiki-gen`` stream,
load the job, build the seam-injected clients, and run the orchestrator. The
stream is only the wake-up signal — the ``wiki_gen_jobs`` row (items_done) is the
durable truth, so a lost message degrades to "re-trigger to resume". Gated on
``settings.wiki_gen_enabled`` (OFF by default): generation costs tokens, so a
deploy never starts generating until explicitly enabled (mirrors the LE resume
consumer + the wiki spec).

NOT a consumer-group with ack/retry — that (+ DLQ) is a follow-up
(D-WIKI-M6-CONSUMER-GROUP); for M6 the job-row resume covers durability.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

import redis.asyncio as aioredis

from app.clients.book_client import get_book_client
from app.clients.book_profile_client import get_book_profile_client
from app.clients.embedding_client import get_embedding_client
from app.clients.glossary_client import get_glossary_client
from app.clients.llm_client import get_llm_client
from app.clients.reranker_client import get_reranker_client
from app.config import settings
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.wiki_gen_jobs import WikiGenJobsRepo
from app.deps import get_knowledge_pool
from app.jobs.wiki_gen_enqueue import WIKI_GEN_STREAM
from app.wiki.orchestrator import OrchestratorClients, run_wiki_gen_job

logger = logging.getLogger(__name__)

__all__ = ["run_wiki_gen_consumer", "process_wiki_gen_job"]


def _retrieval_params() -> dict:
    return {
        "mode": "hybrid",
        "granularity": "chapter",
        "rerank": settings.rerank_enabled,
        "limit": settings.wiki_gen_passage_limit,
    }


async def process_wiki_gen_job(job_id: str) -> None:
    """Load + run one job. Resolves the project, builds the clients from their
    singletons, and drives the orchestrator. A failure marks the job failed (and
    is logged) — never propagated (the consumer keeps draining)."""
    pool = get_knowledge_pool()
    repo = WikiGenJobsRepo(pool)
    try:
        from uuid import UUID
        job = await repo.get(UUID(job_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("wiki-gen: bad job_id %s: %s", job_id, exc)
        return
    if job is None:
        logger.warning("wiki-gen: job %s not found", job_id)
        return

    projects = await ProjectsRepo(pool).list(job.user_id, book_id=job.book_id, limit=1)
    if not projects:
        await repo.fail(job.job_id, error="project not found for book")
        return

    clients = OrchestratorClients(
        glossary=get_glossary_client(), book=get_book_client(),
        embedding=get_embedding_client(), reranker=get_reranker_client(),
        llm=get_llm_client(), book_profile=get_book_profile_client(),
    )
    try:
        status = await run_wiki_gen_job(
            job, repo=repo, project=projects[0], clients=clients,
            retrieval_params=_retrieval_params(),
            prompt_version=settings.wiki_prompt_version,
            pipeline_version=settings.wiki_pipeline_version,
            cost_per_article_usd=Decimal(str(settings.wiki_gen_cost_per_article_usd)),
        )
        logger.info("wiki-gen job %s finished status=%s", job_id, status)
    except Exception as exc:  # noqa: BLE001 — never let one job crash the consumer
        logger.exception("wiki-gen job %s crashed: %s", job_id, exc)
        await repo.fail(job.job_id, error=str(exc))


async def drain_resumable_jobs() -> None:
    """Pick up jobs orphaned while the consumer was down: pending (the trigger
    XADD was never consumed) + running (a process crashed mid-run). Without this,
    such a job stays active forever — holding the per-book lock with no way to
    re-trigger (409) — so this is what makes the resume story actually work.
    Skip-done (items_done) makes re-running a crashed job idempotent."""
    try:
        jobs = await WikiGenJobsRepo(get_knowledge_pool()).list_resumable()
    except Exception as exc:  # noqa: BLE001 — a drain failure must not block startup
        logger.warning("wiki-gen drain query failed: %s", exc)
        return
    if jobs:
        logger.info("wiki-gen: draining %d orphaned job(s) on startup", len(jobs))
    for job in jobs:
        await process_wiki_gen_job(str(job.job_id))


async def run_wiki_gen_consumer() -> None:
    """Blocking-XREAD loop over the wiki-gen stream (runs until cancelled on
    shutdown — the 2s block makes cancellation responsive). On start it first
    drains orphaned pending/running jobs (a message XADD'd while the consumer was
    down is otherwise missed by the '$' read), then tails new messages."""
    await drain_resumable_jobs()
    client = aioredis.from_url(settings.redis_url)
    last_id = "$"
    logger.info("wiki-gen consumer started (stream=%s)", WIKI_GEN_STREAM)
    try:
        while True:
            try:
                resp = await client.xread({WIKI_GEN_STREAM: last_id}, count=1, block=2000)
            except Exception as exc:  # noqa: BLE001 — transient redis blip; back off + retry
                logger.warning("wiki-gen xread failed: %s", exc)
                await asyncio.sleep(1.0)
                continue
            if not resp:
                continue
            for _stream, messages in resp:
                for msg_id, fields in messages:
                    last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    raw = fields.get(b"job_id") or fields.get("job_id")
                    job_id = raw.decode() if isinstance(raw, bytes) else raw
                    if job_id:
                        await process_wiki_gen_job(job_id)
    finally:
        await client.aclose()
        logger.info("wiki-gen consumer stopped")
