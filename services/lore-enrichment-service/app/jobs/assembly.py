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
from app.db.repositories.eval_runs import EvalRunsRepo
from app.generation.complete import make_complete_fn
from app.generation.generate import SchemaGovernedGenerator
from app.jobs.cost import GapCostModel, JobCostBudget
from app.jobs.events import JobEventEmitter, make_redis_producer
from app.jobs.proposal_store import PgProposalStore
from app.jobs.runner import JobRunner
from app.jobs.stages import FabricationPipeline, GapPipeline, JobPipeline, ReCookPipeline
from app.jobs.tokens import UsageMeter
from app.retrieval.embedding import make_embed_query_fn
from app.retrieval.store import SourceCorpusStore
from app.retrieval.strategy import RetrievalStrategy
from app.strategies.base import EnrichmentStrategy, Technique
from app.strategies.fabrication import FabricationStrategy
from app.strategies.factory import GateAwareStrategyFactory
from app.strategies.gate_reader import make_eval_runs_gate_reader
from app.strategies.licensing import SourceLicense
from app.strategies.recook import ReCookStrategy
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
    spent_so_far: float = 0.0,
    top_k: int = 5,
    technique: str = Technique.RETRIEVAL.value,
    suite_version: str = "enrichment-v1",
) -> LiveRunnerBundle:
    """Compose a :class:`JobRunner` from the real platform components.

    ``embedding_model_ref`` is the provider-registry user_model id for the
    project's embedding model — used by retrieval. The GENERATION model_ref is
    carried per-run on the :class:`StrategyContext` the caller passes to
    ``run_job`` (so the embed + gen models can differ). NO model name here.

    ``spent_so_far`` seeds the cost budget with the spend a PRIOR run already
    incurred (read from ``enrichment_job.actual_cost_usd`` on a resume) so a
    resumed job's cap accounts for what it already spent — it does NOT reset to
    0 and double-spend up to the cap again (WARN-1 budget-reset fix).

    ``technique`` selects WHICH enrichment technique drives this job (default
    ``retrieval`` = the P1 demo path, unchanged). Selection is routed through the
    :class:`~app.strategies.factory.GateAwareStrategyFactory` so the LIVE eval gate
    (DEFERRED-054) is enforced END-TO-END: a P2/P3 technique (e.g. ``fabrication``)
    while the gate is LOCKED RAISES
    :class:`~app.strategies.registry.InactiveStrategyError` here — the job is
    REFUSED at assembly time, never built. Only a real, persisted, passing eval run
    for the project unlocks fabrication. The selected strategy's ``estimate_cost``
    is what the cost-cap charges (so fabrication's higher per-gap cost actually
    binds), while the P1 retrieval path keeps the truthful embed+generation
    :class:`~app.jobs.cost.GapCostModel` it has always used.
    """
    # ── C1 client (embed + graph-stats) ────────────────────────────────────────
    kc = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )

    # ── C1 token meter (DEFERRED-052) ───────────────────────────────────────────
    # One meter per job run; the embed + generation seams record their REAL token
    # usage into it and the runner reconciles the per-gap pre-charge against the
    # meter's delta. Wired into the shared seams below; passed to the runner ONLY
    # on the P1 token path (P2/P3 keep their opaque pre-charge — gate-locked).
    meter = UsageMeter()

    # ── C10 retrieval (store + embed seam) ──────────────────────────────────────
    store = SourceCorpusStore(pool)
    embed_query = make_embed_query_fn(kc, user_id=UUID(user_id), meter=meter)
    retrieval = RetrievalStrategy(store=store, embed_query=embed_query, top_k=top_k)

    # ── C11 generation (real LLM completion seam by model_ref) ──────────────────
    complete = make_complete_fn(
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
        meter=meter,
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

    # ── technique selection via the GATE-AWARE FACTORY (DEFERRED-054 e2e) ────────
    # The factory reads the LIVE persisted eval gate (the same row the
    # /internal/eval/{project}/gate-status route exposes) and REFUSES a P2/P3
    # technique while the gate is LOCKED. ``factory.select`` raises
    # InactiveStrategyError for a locked fabrication request — so a job that asks
    # for fabrication is refused at assembly time, gate-enforced END-TO-END. The
    # P1 retrieval technique is always active (its tier is never gated), so the
    # DEFAULT demo path is unchanged.
    #
    # The fabrication STRATEGY reuses the SAME retrieval + verifier + completion
    # seams; it is constructed unconditionally but is unreachable until the gate
    # clears (the factory is the single enforcement point).
    fabrication = FabricationStrategy(
        retrieval=retrieval, complete=complete, verifier=verifier
    )

    # ── C17 re-cook (P3): same gate-enforced selection path + a LICENSING gate.
    # The license-resolver reads ``source_corpus.license`` for each grounding
    # source; the re-cook strategy refuses any non-public_domain/non-licensed
    # source (default-deny) at corpus-admission AND fact-emit. Like fabrication it
    # is constructed unconditionally but unreachable until the gate clears (the
    # factory is the single enforcement point; P3 is forced OFF on a locked gate).
    async def _license_lookup(corpus_id: str) -> SourceLicense | None:
        raw = await store.get_corpus_license(corpus_id=UUID(corpus_id))
        if raw is None:
            return None  # unknown corpus → caller treats as UNKNOWN (refused)
        return SourceLicense.from_raw(corpus_id=corpus_id, name=corpus_id, license=raw)

    recook = ReCookStrategy(
        retrieval=retrieval,
        complete=complete,
        verifier=verifier,
        license_lookup=_license_lookup,
    )
    factory = GateAwareStrategyFactory(
        gate_reader=make_eval_runs_gate_reader(EvalRunsRepo(pool)),
        strategies=[retrieval, fabrication, recook],
        suite_version=suite_version,
    )
    # Gate enforcement happens HERE — a locked fabrication raises
    # InactiveStrategyError (propagated to the caller as a refused job). The
    # selected strategy decides the pipeline + the cost model the runner charges.
    try:
        selected: EnrichmentStrategy = await factory.select(
            technique, user_id=user_id, project_id=project_id
        )
    except Exception:
        # The factory's gate read fails CLOSED; an InactiveStrategyError (locked
        # gate) or any selection error must NOT leak an open KnowledgeClient.
        await kc.aclose()
        raise

    pipeline: JobPipeline
    cost_strategy: EnrichmentStrategy
    # The runner reconciles real tokens ONLY on the P1 token path; P2/P3 keep
    # their opaque pre-charge (8.0/12.0 per gap) until their token-denomination
    # lands at gate activation (DEFERRED-059) — meter=None → no reconcile.
    runner_meter: UsageMeter | None = None
    if selected.technique is Technique.FABRICATION:
        # P2: the fabrication pipeline (retrieve → fabricate → verify per gap).
        # Its OWN estimate_cost (FABRICATION_GAP_COST=8.0/gap) is what the cost-cap
        # charges, so the higher P2 cost actually binds (not the inert P1 model).
        pipeline = FabricationPipeline(strategy=selected)  # type: ignore[arg-type]
        cost_strategy = selected
    elif selected.technique is Technique.RECOOK:
        # P3: the re-cook pipeline (retrieve → licensing-check → re-contextualise →
        # verify per gap). Reachable ONLY when the gate is CLEARED (the factory
        # forces P3 OFF on a locked gate). Its OWN estimate_cost
        # (RECOOK_GAP_COST=12.0/gap) is what the cost-cap charges, so the highest
        # P3 cost binds soonest. The licensing gate inside the strategy refuses any
        # unlicensed source (UnlicensedSourceError propagates → job refused).
        pipeline = ReCookPipeline(strategy=selected)  # type: ignore[arg-type]
        cost_strategy = selected
    else:
        # P1 default (retrieval): the unchanged C10→C11→C12 pipeline + the
        # truthful embed+generation GapCostModel the demo path has always used
        # (RetrievalStrategy.estimate_cost alone would under-count the generation).
        pipeline = GapPipeline(
            retrieval=retrieval, generator=generator, verifier=verifier
        )
        cost_strategy = GapCostModel()
        # P1 is token-denominated: hand the runner the meter so it reconciles each
        # gap's pre-charge to the REAL tokens the embed + LLM seams recorded (C1).
        runner_meter = meter

    # ── persistence (C2) ────────────────────────────────────────────────────────
    pg_store = PgProposalStore(pool)

    # ── events (Redis Streams; best-effort) ─────────────────────────────────────
    producer = make_redis_producer(settings.redis_url)
    emitter = JobEventEmitter(
        producer, job_id=job_id, project_id=project_id, user_id=user_id
    )

    # ── cost budget (cap + reserved eval line, M5) ──────────────────────────────
    # ``spent_so_far`` (resume) preloads what a prior run already spent so the
    # working cap accounts for it (WARN-1: never reset to 0 and re-spend).
    budget = JobCostBudget(
        cost_cap, eval_reserve_fraction=eval_reserve_fraction, spent=spent_so_far
    )

    runner = JobRunner(
        store=pg_store,
        pipeline=pipeline,
        # The REAL per-gap cost — NON-ZERO so the cap actually bites a runaway
        # job (BLOCK-1; the old wiring injected TemplateStrategy's free-scaffold
        # estimate, cost 0.0, making the cap inert). For P1 retrieval this is the
        # truthful embed+generation GapCostModel; for P2 fabrication it is the
        # strategy's own higher estimate (8.0/gap) so the higher P2 cost binds.
        cost_strategy=cost_strategy,
        emitter=emitter,
        budget=budget,
        # C1: the meter on the P1 token path (None for P2/P3 → no reconcile yet).
        meter=runner_meter,
    )
    return LiveRunnerBundle(runner, knowledge_client=kc)
