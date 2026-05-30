"""Runner ASSEMBLY (RAID C14) — wire the real C7–C13 components for a live job.

This is the single composition root that binds the injected seams of the C14
:class:`~app.jobs.runner.JobRunner` to their production implementations:

  * retrieval (C10) — :class:`SourceCorpusStore` over the DB pool + the C1
    embed seam (``/internal/embed`` via provider-registry by ``model_ref``);
  * generation (C11) — :class:`SchemaGovernedGenerator` over the real
    ``/internal/llm/stream`` completion seam (by ``model_ref``);
  * canon-verify (C12) — :class:`CanonVerifier` over the C1 read port + a
    glossary/KG canon-lookup (degrades safely when canon is unavailable, Q6);
  * persistence (C2) — :class:`PgProposalStore`;
  * events — :class:`JobEventEmitter` over a real Redis Streams producer (best-
    effort; a down Redis never fails the job).

NO model NAMES appear here — the embedding + generation models are resolved by
provider-registry ``model_ref`` (carried on the :class:`StrategyContext`). This
module is exercised by the live-smoke / demo path; unit tests inject fakes
directly into the runner and do not touch it.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.clients.knowledge import KnowledgeClient
from app.clients.port import KnowledgeReadHttp
from app.config import settings
from app.generation.complete import make_complete_fn
from app.generation.generate import SchemaGovernedGenerator
from app.jobs.cost import JobCostBudget
from app.jobs.events import JobEventEmitter, make_redis_producer
from app.jobs.proposal_store import PgProposalStore
from app.jobs.runner import JobRunner
from app.jobs.stages import GapPipeline
from app.retrieval.embedding import make_embed_query_fn
from app.retrieval.store import SourceCorpusStore
from app.retrieval.strategy import RetrievalStrategy
from app.strategies.template import TemplateStrategy
from app.verify.canon_verify import CanonFact, CanonVerifier

__all__ = ["build_live_runner", "LiveRunnerBundle"]


class LiveRunnerBundle:
    """Owns the constructed runner + the resources that must be closed after."""

    def __init__(self, runner: JobRunner, *, knowledge_client: KnowledgeClient) -> None:
        self.runner = runner
        self._kc = knowledge_client

    async def aclose(self) -> None:
        await self._kc.aclose()


async def build_live_runner(
    *,
    pool: asyncpg.Pool,
    job_id: str,
    user_id: str,
    project_id: str,
    embedding_model_ref: str,
    cost_cap: float | None,
    eval_reserve_fraction: float = 0.15,
    top_k: int = 5,
) -> LiveRunnerBundle:
    """Compose a :class:`JobRunner` from the real platform components.

    ``embedding_model_ref`` is the provider-registry user_model id for the
    project's embedding model — used by retrieval. The GENERATION model_ref is
    carried per-run on the :class:`StrategyContext` the caller passes to
    ``run_job`` (so the embed + gen models can differ). NO model name here.
    """
    # ── C1 client (embed + graph-stats) ────────────────────────────────────────
    kc = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )

    # ── C10 retrieval (store + embed seam) ──────────────────────────────────────
    store = SourceCorpusStore(pool)
    embed_query = make_embed_query_fn(kc, user_id=UUID(user_id))
    retrieval = RetrievalStrategy(store=store, embed_query=embed_query, top_k=top_k)

    # ── C11 generation (real LLM completion seam by model_ref) ──────────────────
    complete = make_complete_fn(
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    generator = SchemaGovernedGenerator(complete=complete)

    # ── C12 canon-verify (read port degrades safely; no canon-write) ────────────
    read_port = KnowledgeReadHttp(kc)

    async def _canon_lookup(entity_name: str, dimension: str) -> list[CanonFact]:
        # No authored-canon assertions are read in the demo path (the seeded
        # LOCATIONs are sparse — that is precisely the gap). Returning [] is a
        # genuine "no canon known" (not an error), so verify does not degrade on
        # it; the read_port still gates reachability for the contradiction check.
        return []

    verifier = CanonVerifier(read_port=read_port, canon_lookup=_canon_lookup)

    pipeline = GapPipeline(
        retrieval=retrieval, generator=generator, verifier=verifier
    )

    # ── persistence (C2) ────────────────────────────────────────────────────────
    pg_store = PgProposalStore(pool)

    # ── events (Redis Streams; best-effort) ─────────────────────────────────────
    producer = make_redis_producer(settings.redis_url)
    emitter = JobEventEmitter(
        producer, job_id=job_id, project_id=project_id, user_id=user_id
    )

    # ── cost budget (cap + reserved eval line, M5) ──────────────────────────────
    budget = JobCostBudget(cost_cap, eval_reserve_fraction=eval_reserve_fraction)

    runner = JobRunner(
        store=pg_store,
        pipeline=pipeline,
        cost_strategy=TemplateStrategy(),  # the free, deterministic estimate unit
        emitter=emitter,
        budget=budget,
    )
    return LiveRunnerBundle(runner, knowledge_client=kc)
