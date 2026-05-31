"""End-to-end JOB RUNNER (RAID C14, DEMO milestone).

Chains the WHOLE P1 enrichment pipeline into one job with lifecycle state +
Redis Streams events + a per-job cost-cap (incl. the reserved eval-cost line,
M5). It ORCHESTRATES the existing C7–C13 components — it builds NO new gap /
strategy / generation / verify / write-back logic.

Flow (one ``run_job`` call):

    estimate  (pending → estimating)   sum strategy cost over gaps + eval reserve
    start     (estimating → running)   emit job.started
    per gap:
        cost-cap charge_or_pause  BEFORE the gap (breach → PAUSE + job.paused,
                                  re-runnable safely — NEVER crash, NEVER touch
                                  the eval reserve)
        stage pipeline (C10→C11→C12)   retrieval → generate (H0 facts) → verify
        persist proposal (quarantined, H0: origin='enrichment', confidence<1.0,
                          review_status='proposed')
        emit job.stage_completed + job.proposal_created  (idempotent)
    complete  (running → completed)    emit job.completed
    on error  (→ failed)               emit job.failed

H0 (LOCKED): every persisted proposal is born quarantined; ONLY a later author
promote (C13) canonizes. The runner NEVER writes canon, NEVER calls promote.
Cost-cap breach PAUSES — it does not drop work or crash.

Resume/re-run SAFETY (WARN-1): a paused job is re-run by invoking ``run_job``
again on a fresh runner seeded with the prior spend (``build_live_runner
(spent_so_far=...)``). Re-running is SAFE but NOT yet skip-prior-work: it
re-processes from gap 0, but it does NOT double-charge (the budget is seeded
from ``actual_cost_usd``) and does NOT duplicate proposals (the per-gap
idempotent persist, UNIQUE(job_id, gap_ref), reloads an already-persisted gap's
row instead of inserting again — ``persisted.deduped`` flags it). Skipping the
already-done gaps on resume is tracked as D-C14-FULL-RESUME. Events are
idempotent within one emitter instance (dedupe set); a fresh emitter on a re-run
may re-emit, but the consumer dedupes on ``dedupe_key`` (at-least-once stream).

Boundaries: lore-enrichment-service only. NO model names (the strategies resolve
via provider-registry by model_ref). NO direct Neo4j / glossary canonical write.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.gaps.model import Gap
from app.generation.generate import GenerationError
from app.jobs.cost import CostCapExceeded, JobCostBudget
from app.jobs.events import JobEventEmitter, JobEventType
from app.jobs.proposal_store import (
    PersistedProposal,
    ProposalStore,
    build_proposal_fields,
)
from app.jobs.stages import JobPipeline
from app.jobs.state_machine import JobRecord, JobStateMachine, PersistFn
from app.jobs.tokens import UsageMeter
from app.strategies.base import EnrichmentStrategy, StrategyContext
from app.strategies.fabrication import FabricationError
from app.verify.wiring import VerifyStatus, decide_auto_reject

__all__ = [
    "JobOutcome",
    "JobRunner",
]

logger = logging.getLogger("lore_enrichment.job_runner")


@dataclass
class JobOutcome:
    """The result of a (possibly partial) job run.

    ``final_state`` is the C8 state the job ended in (completed / paused /
    failed). ``proposals`` are the quarantined H0 proposals persisted this run.
    ``paused_at_gap`` names the gap a cost-cap pause stopped before (None unless
    paused). ``error`` carries a failure message (None unless failed)."""

    job_id: str
    final_state: str
    proposals: list[PersistedProposal] = field(default_factory=list)
    estimated_cost: float = 0.0
    spent: float = 0.0
    paused_at_gap: str | None = None
    error: str | None = None
    skipped_gaps: list[str] = field(default_factory=list)
    #: gaps whose proposal already existed (a resume/re-run re-processed them —
    #: the idempotent persist reloaded the row instead of duplicating it, WARN-1).
    deduped_gaps: list[str] = field(default_factory=list)
    #: gaps SKIPPED before any work on a resume because their proposal already
    #: exists (passed via skip_gap_refs) — neither budget nor an LLM call spent
    #: on them (the token-safe convergence fix, 051/F-C14-1).
    resumed_skipped: list[str] = field(default_factory=list)
    #: gaps whose proposal was AUTO-REJECTED as egregious (C3): persisted as a
    #: terminal `rejected` row (audited), NOT surfaced to the review queue/wiki,
    #: and NOT counted as a created proposal. Still never canon (H0).
    auto_rejected_gaps: list[str] = field(default_factory=list)


class JobRunner:
    """Drives one enrichment job end-to-end over a ranked gap list.

    Construct with the persistence store (C2 writes), the P1 :class:`GapPipeline`
    (C10/C11/C12), the cost strategy (for the per-gap estimate/charge unit), the
    event emitter (Redis Streams), and the cost budget (cap + eval reserve). All
    seams are injected so unit tests run with in-memory store + fake Redis +
    stubbed LLM, and the demo injects the real stack.
    """

    def __init__(
        self,
        *,
        store: ProposalStore,
        pipeline: JobPipeline,
        cost_strategy: EnrichmentStrategy,
        emitter: JobEventEmitter,
        budget: JobCostBudget,
        persist_state: PersistFn | None = None,
        meter: UsageMeter | None = None,
    ) -> None:
        self._store = store
        self._pipeline = pipeline
        self._cost_strategy = cost_strategy
        self._emitter = emitter
        self._budget = budget
        self._persist_state = persist_state
        # C1 (DEFERRED-052): when a meter is wired (P1 token path), the runner
        # reconciles each gap's pre-charged estimate to the REAL tokens the seams
        # recorded. None → no reconcile (P2/P3 opaque pre-charge, gate-locked).
        self._meter = meter

    @property
    def store(self) -> ProposalStore:
        """The persistence store (the caller creates the job row through this)."""
        return self._store

    @property
    def technique(self) -> str:
        """The technique the P1 proposals carry (retrieval — supplies grounding)."""
        return self._pipeline.technique_value()

    async def run_job(
        self,
        *,
        job_id: str,
        gaps: list[Gap],
        context: StrategyContext,
        entity_kind: str | None = None,
        jwt: str = "",
        skip_gap_refs: frozenset[str] = frozenset(),
    ) -> JobOutcome:
        """Run the full P1 pipeline over ``gaps`` for one job.

        Returns a :class:`JobOutcome`. The job persists through the C8 state
        machine (pending→estimating→running→completed | paused | failed), emits a
        lifecycle event per phase, and enforces the cost cap (pause on breach).

        ``skip_gap_refs`` (resume, 051/F-C14-1): gaps whose proposal already
        exists from a prior run. They are skipped BEFORE the cost-cap charge and
        the LLM ``run_gap``, so a resumed job re-spends neither budget nor tokens
        on done gaps — it processes strictly fewer gaps each time and converges.
        """
        record = JobRecord(job_id=job_id)
        machine = JobStateMachine(record, persist=self._persist_state)
        outcome = JobOutcome(job_id=job_id, final_state=record.state.value)

        # ── estimate (pending → estimating) ─────────────────────────────────────
        await machine.estimate()
        estimate = self._cost_strategy.estimate_cost(gaps)
        outcome.estimated_cost = estimate.cost
        await self._store.mark_job_status(
            job_id=job_id, status="estimating",
        )

        # ── start (estimating → running) ────────────────────────────────────────
        await machine.start()
        await self._store.mark_job_status(job_id=job_id, status="running")
        await self._emitter.emit(
            JobEventType.STARTED,
            data={
                "gap_count": len(gaps),
                "estimated_cost": estimate.cost,
                "cap": self._budget.cap,
                "working_cap": self._budget.working_cap,
                "eval_reserve": self._budget.eval_reserve,
                "technique": self._pipeline.technique_value(),
            },
        )

        try:
            for gap in gaps:
                gap_ref = self._gap_ref(gap)
                # ── resume skip (051): a gap already persisted on a prior run is
                # skipped BEFORE the cost charge + the LLM run_gap, so a resumed
                # job spends neither budget nor tokens on it (token-safe).
                if gap_ref in skip_gap_refs:
                    outcome.resumed_skipped.append(gap_ref)
                    continue
                # Per-gap cost: the strategy's estimate for a one-gap batch.
                unit_cost = self._cost_strategy.estimate_cost([gap]).cost
                # ── cost-cap BEFORE the gap (breach → PAUSE, resumable) ──────────
                try:
                    await self._budget.charge_or_pause(unit_cost, machine)
                except CostCapExceeded as exc:
                    await self._store.mark_job_status(
                        job_id=job_id,
                        status="paused",
                        actual_cost=self._budget.spent,
                        error_message=f"paused: cost_cap before {gap_ref}",
                    )
                    await self._emitter.emit(
                        JobEventType.PAUSED,
                        gap_ref=gap_ref,
                        data={
                            "reason": "cost_cap",
                            "before_gap": gap_ref,
                            "spent": self._budget.spent,
                            "working_cap": self._budget.working_cap,
                            "eval_reserve_protected": self._budget.eval_reserve,
                            "attempted": exc.attempted,
                        },
                    )
                    outcome.final_state = record.state.value
                    outcome.paused_at_gap = gap_ref
                    outcome.spent = self._budget.spent
                    return outcome

                # ── stage pipeline (C10 → C11 → C12) ────────────────────────────
                # C1 (DEFERRED-052): snapshot the meter AFTER the pre-charge and
                # BEFORE the gap runs; the per-gap token delta (post − pre) is the
                # real spend the runner reconciles against the pre-charged estimate.
                before_tokens = (
                    self._meter.total_tokens if self._meter is not None else 0
                )
                stage_started = time.monotonic()
                try:
                    stage = await self._pipeline.run_gap(gap, context, jwt=jwt)
                except (GenerationError, FabricationError) as exc:
                    # An ungroundable / unrepairable gap is SKIPPED (not a job
                    # failure): the pipeline refused to mint an unprovenanced
                    # fact (H0). FabricationError is the P2 counterpart of
                    # GenerationError — an ungrounded fabrication is refused the
                    # same way (never free invention). Record + continue; other
                    # gaps still enrich.
                    # Reconcile the tokens that DID run (the embed query, and any
                    # generation up to the refusal) so a skipped gap's real spend
                    # is charged truthfully — not the full pre-estimate.
                    self._reconcile_gap(unit_cost, before_tokens)
                    logger.info("skipping gap %s: %s", gap_ref, exc)
                    outcome.skipped_gaps.append(gap_ref)
                    continue

                # The gap produced content: reconcile its pre-charged estimate to
                # the REAL tokens the embed + LLM seams recorded into the meter.
                self._reconcile_gap(unit_cost, before_tokens)

                # ── persist (quarantined, H0) ───────────────────────────────────
                # The proposal confidence reflects GENERATION (the facts now hold
                # generated content), not the empty-grounding retrieval floor —
                # still strictly < 1.0 (H0). Falls back to the proposal's grounded
                # confidence only if (defensively) no fact carries one.
                proposal_confidence = max(
                    (f.confidence for f in stage.facts),
                    default=stage.proposal.confidence,
                )
                # ── C3 auto-reject: an EGREGIOUS verify result (injection / HIGH
                # contradiction / >=2 distinct anachronism markers) is persisted as
                # a terminal `rejected` row (audited) and NOT surfaced to the review
                # queue/wiki — still never canon (suppression, not promotion). The
                # rest stay on the advisory `proposed` path (the human gate decides).
                reject = decide_auto_reject(stage.verify.result)
                fields = build_proposal_fields(
                    user_id=context.user_id,
                    project_id=context.project_id,
                    entity_kind=stage.proposal.entity_kind,
                    canonical_name=stage.proposal.canonical_name,
                    target_ref=stage.proposal.target_ref,
                    # The technique that actually PRODUCED the facts (the pipeline's
                    # own), NOT the grounding proposal's — for fabrication the
                    # grounding proposal is the C10 retrieval proposal (technique=
                    # 'retrieval'), but the facts were fabricated (technique=
                    # 'fabrication'). For the P1 path both agree on 'retrieval'.
                    technique=self._pipeline.technique_value(),
                    confidence=proposal_confidence,
                    facts=stage.facts,
                    verify=stage.verify,
                    source_refs=stage.source_refs,
                    base_provenance=stage.proposal.provenance_json,
                    gap_ref=gap_ref,  # per-gap idempotency key (WARN-1)
                    review_status="rejected" if reject else "proposed",
                    rejected_reason=reject.reason if reject else None,
                )
                persisted = await self._store.persist_proposal(
                    job_id=job_id, fields=fields
                )
                if reject:
                    # Auditable terminal rejection — NOT counted as a created
                    # proposal, NOT surfaced. Emit the audit event and move on.
                    outcome.auto_rejected_gaps.append(gap_ref)
                else:
                    outcome.proposals.append(persisted)
                    if persisted.deduped:
                        # A resume/re-run re-processed an already-persisted gap; the
                        # store reloaded the existing row instead of duplicating it.
                        # Record it for visibility, but flag the no-op (WARN-1).
                        outcome.deduped_gaps.append(gap_ref)

                # ── events (idempotent per job+stage+gap) ───────────────────────
                # ``elapsed_seconds`` + ``technique`` feed the C18 per-stage
                # latency histogram (observed in the emitter); both are bounded
                # scalars, never enriched content.
                stage_elapsed = time.monotonic() - stage_started
                await self._emitter.emit(
                    JobEventType.STAGE_COMPLETED,
                    gap_ref=gap_ref,
                    data={
                        "gap": gap_ref,
                        "dimensions": list(persisted.dimensions.keys()),
                        "verify_status": stage.verify.status.value,
                        "elapsed_seconds": round(stage_elapsed, 6),
                        "technique": self._pipeline.technique_value(),
                    },
                )
                if reject:
                    await self._emitter.emit(
                        JobEventType.PROPOSAL_AUTO_REJECTED,
                        gap_ref=gap_ref,
                        data={
                            "proposal_id": persisted.proposal_id,
                            "canonical_name": persisted.canonical_name,
                            "review_status": persisted.review_status,
                            "rejected_reason": persisted.rejected_reason,
                            "verify_status": stage.verify.status.value,
                        },
                    )
                else:
                    await self._emitter.emit(
                        JobEventType.PROPOSAL_CREATED,
                        gap_ref=gap_ref,
                        data={
                            "proposal_id": persisted.proposal_id,
                            "canonical_name": persisted.canonical_name,
                            "origin": persisted.origin,
                            "technique": persisted.technique,
                            "review_status": persisted.review_status,
                            "confidence": persisted.confidence,
                            "pending_validation": persisted.pending_validation,
                        },
                    )

            # ── complete (running → completed) ──────────────────────────────────
            await machine.complete()
            outcome.spent = self._budget.spent
            await self._store.mark_job_status(
                job_id=job_id,
                status="completed",
                actual_cost=self._budget.spent,
                proposals_total=len(outcome.proposals),
            )
            await self._emitter.emit(
                JobEventType.COMPLETED,
                data={
                    "proposals_total": len(outcome.proposals),
                    "skipped_gaps": outcome.skipped_gaps,
                    "spent": self._budget.spent,
                },
            )
            outcome.final_state = record.state.value
            return outcome

        except Exception as exc:  # noqa: BLE001 — convert to a clean failed state
            # Any unexpected error fails the job (resumable lifecycle is for
            # cost-cap pauses; a real error is terminal-failed with a message).
            err = f"{type(exc).__name__}: {exc}"
            if not machine.is_terminal():
                await machine.fail(error_message=err)
            await self._store.mark_job_status(
                job_id=job_id,
                status="failed",
                actual_cost=self._budget.spent,
                proposals_total=len(outcome.proposals),
                error_message=err,
            )
            await self._emitter.emit(
                JobEventType.FAILED, data={"error": err}
            )
            outcome.final_state = record.state.value
            outcome.error = err
            outcome.spent = self._budget.spent
            return outcome

    def _reconcile_gap(self, pre_estimate: float, before_tokens: int) -> None:
        """Reconcile one gap's pre-charged estimate to the REAL tokens it spent
        (C1, DEFERRED-052). No-op when no meter is wired (P2/P3 opaque path).

        ``before_tokens`` is the meter total snapshotted right after the
        pre-charge; ``meter.total_tokens − before_tokens`` is this gap's actual
        token spend (sequential-run invariant). The budget is trued up by
        ``actual − pre_estimate``: down (refund headroom) when the gap under-ran
        its estimate, up (one-gap overshoot, eval-reserve-absorbed) when it
        over-ran. The cap is still guarded BEFORE the next gap's pre-charge."""
        if self._meter is None:
            return
        actual = self._meter.total_tokens - before_tokens
        self._budget.reconcile(actual - pre_estimate)

    @staticmethod
    def _gap_ref(gap: Gap) -> str:
        """A stable per-gap discriminator for dedupe keys + event payloads.

        Uses target_ref when present (the canon entity), else the canonical name
        — both faithful identities (never makeup content)."""
        return (gap.target_ref or "").strip() or gap.canonical_name
