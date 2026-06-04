"""End-to-end RUNNER ↔ gate-aware factory wiring for RE-COOK (RAID C17).

The C17 counterpart to ``test_runner_gate_e2e`` (C16/DEFERRED-054). It drives the
RUNNER (the thing ``POST /jobs`` → ``build_live_runner`` builds) through the SAME
gate-enforced selection logic the assembly uses — with a fake gate reader + a fake
license resolver — and proves the re-cook path is enforced END-TO-END:

  * gate LOCKED + technique=recook → selection RAISES InactiveStrategyError (the
    job is refused; the runner is never built) — gate enforced for P3 too;
  * gate CLEARED + technique=recook + a PUBLIC-DOMAIN source → the runner is
    handed a ReCookPipeline and produces H0-tagged (origin='enriched:recook',
    conf<1.0, quarantined) proposals;
  * gate CLEARED + technique=recook + an UNLICENSED source → the licensing gate
    REFUSES (UnlicensedSourceError) inside the run — no proposal persisted;
  * the re-cook per-gap cost (12.0) binds on the cap (highest tier pauses soonest);
  * the DEFAULT retrieval (P1) path is unaffected by the gate (no regression).

The LLM + retrieval + license lookup are MOCKED (deterministic). The point is the
WIRING: factory.select → ReCookPipeline → JobRunner, gate + licensing enforced.
"""

from __future__ import annotations

import pytest

from app.clients.port import NullKnowledgeRead
from app.gaps.model import Dimension, EntityKind, Gap, dimensions_for
from app.generation.generate import SchemaGovernedGenerator
from app.jobs.cost import GapCostModel, JobCostBudget
from app.jobs.events import JobEventEmitter, JobEventType
from app.jobs.proposal_store import InMemoryProposalStore
from app.jobs.runner import JobRunner
from app.jobs.stages import GapPipeline, ReCookPipeline
from app.retrieval.strategy import GroundedProposal, GroundingRef
from app.strategies.base import EnrichmentStrategy, StrategyContext, Technique
from app.strategies.factory import GateAwareStrategyFactory, LiveGateStatus
from app.strategies.licensing import LicenseStatus, SourceLicense
from app.strategies.recook import RECOOK_GAP_COST, ReCookStrategy
from app.strategies.registry import InactiveStrategyError
from app.verify.canon_verify import CanonVerifier

# asyncio_mode=auto (pytest.ini) — async tests run without an explicit marker.

_USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
_PROJECT = "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39"
_SUITE = "enrichment-v1"
_CORPUS = "corpus-history"

_VALID_COMPLETION = (
    '{"历史": "古为商畿要塞，殷商边陲重镇。", '
    '"地理": "据山川形胜，扼水陆之冲。", '
    '"文化": "关民敬奉雷神，岁时祭祷。", '
    '"features": "城高池深，烽燧相望。", '
    '"inhabitants": "戍卒、关民、修道之士居之。"}'
)


class _FakeRetrieval:
    """Quacks like RetrievalStrategy.run — one grounded proposal per gap with a
    fixed grounding (from a single source corpus) so re-cook has provenance."""

    technique = Technique.RETRIEVAL

    def __init__(self, *, grounded: bool = True) -> None:
        self._grounded = grounded

    async def run(self, gaps, context):
        out = []
        for gap in gaps:
            slots = {
                spec.label: ""
                for spec in dimensions_for(gap.entity_kind)
                if spec.dimension in set(gap.missing_dimensions)
            }
            grounding = (
                [
                    GroundingRef(
                        corpus_id=_CORPUS,
                        chunk_id="chunk-1",
                        chunk_index=1,
                        excerpt=f"{gap.canonical_name}为古代边陲重镇。",
                        score=0.79,
                    )
                ]
                if self._grounded
                else []
            )
            out.append(
                GroundedProposal(
                    user_id=context.user_id,
                    project_id=context.project_id,
                    entity_kind=gap.entity_kind,
                    canonical_name=gap.canonical_name,
                    target_ref=gap.target_ref,
                    dimensions=slots,
                    grounding=grounding,
                )
            )
        return out


def _const_complete(text: str):
    async def _fn(prompt, ctx):
        return text
    return _fn


def _license_lookup(status: LicenseStatus):
    async def _fn(corpus_id: str):
        return SourceLicense(corpus_id=corpus_id, name=corpus_id, status=status)
    return _fn


def _gap(name: str) -> Gap:
    return Gap(
        entity_kind=EntityKind.LOCATION,
        canonical_name=name,
        target_ref=f"loc:{name}",
        mention_count=3,
        present_dimensions=(),
        missing_dimensions=tuple(Dimension),
    )


def _ctx() -> StrategyContext:
    return StrategyContext(user_id=_USER, project_id=_PROJECT, model_ref="gen-ref")


def _verifier() -> CanonVerifier:
    async def _no_canon(entity, dim):
        return []
    return CanonVerifier(read_port=NullKnowledgeRead(), canon_lookup=_no_canon)


def _emitter() -> JobEventEmitter:
    return JobEventEmitter(None, job_id="job-1", project_id=_PROJECT, user_id=_USER)


def _gate_reader(*, unlocked: bool):
    async def _read(user_id, project_id, suite_version) -> LiveGateStatus:
        if not unlocked:
            return LiveGateStatus.locked(suite_version)
        return LiveGateStatus(
            has_run=True, p2_p3_unlocked=True, suite_version=suite_version,
            composite=96.0, passed=True,
        )
    return _read


def _factory(*, unlocked: bool, license_status: LicenseStatus) -> GateAwareStrategyFactory:
    """Build the factory EXACTLY like app.jobs.assembly.build_live_runner: the P1
    retrieval marker + the P3 recook strategy registered, over the stubbed gate."""
    retrieval = _FakeRetrieval()
    recook = ReCookStrategy(
        retrieval=retrieval,
        complete=_const_complete(_VALID_COMPLETION),
        verifier=_verifier(),
        license_lookup=_license_lookup(license_status),
    )
    return GateAwareStrategyFactory(
        gate_reader=_gate_reader(unlocked=unlocked),
        strategies=[retrieval, recook],
        suite_version=_SUITE,
    )


async def _build_runner_via_factory(
    *, technique: str, unlocked: bool, license_status: LicenseStatus,
    store, budget, emitter,
) -> JobRunner:
    """Replicate the assembly's gate-enforced selection → pipeline → runner.

    SAME path ``build_live_runner`` takes for re-cook. Raises InactiveStrategyError
    when the requested P3 technique is gate-locked — i.e. the job is refused BEFORE
    a runner exists, gate enforced end-to-end."""
    factory = _factory(unlocked=unlocked, license_status=license_status)
    selected: EnrichmentStrategy = await factory.select(
        technique, user_id=_USER, project_id=_PROJECT
    )
    if selected.technique is Technique.RECOOK:
        pipeline = ReCookPipeline(strategy=selected)  # type: ignore[arg-type]
        cost_strategy: EnrichmentStrategy = selected
    else:
        pipeline = GapPipeline(
            retrieval=_FakeRetrieval(),
            generator=SchemaGovernedGenerator(
                complete=_const_complete(_VALID_COMPLETION)
            ),
            verifier=_verifier(),
        )
        cost_strategy = GapCostModel()
    return JobRunner(
        store=store, pipeline=pipeline, cost_strategy=cost_strategy,
        emitter=emitter, budget=budget,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# gate LOCKED + recook → the RUNNER is REFUSED (gate enforced for P3)
# ═══════════════════════════════════════════════════════════════════════════════
async def test_locked_gate_refuses_recook_job_before_runner():
    store = InMemoryProposalStore()
    with pytest.raises(InactiveStrategyError):
        await _build_runner_via_factory(
            technique=Technique.RECOOK.value, unlocked=False,
            license_status=LicenseStatus.PUBLIC_DOMAIN,
            store=store, budget=JobCostBudget(None), emitter=_emitter(),
        )
    assert store.proposals == []


# ═══════════════════════════════════════════════════════════════════════════════
# gate CLEARED + recook + PD source → the RUNNER re-cooks (H0)
# ═══════════════════════════════════════════════════════════════════════════════
async def test_cleared_gate_runner_recooks_h0_proposals():
    store = InMemoryProposalStore()
    emitter = _emitter()
    runner = await _build_runner_via_factory(
        technique=Technique.RECOOK.value, unlocked=True,
        license_status=LicenseStatus.PUBLIC_DOMAIN,
        store=store, budget=JobCostBudget(None), emitter=emitter,
    )
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("陳塘關")], context=_ctx(), entity_kind="location"
    )
    assert outcome.final_state == "completed"
    assert len(outcome.proposals) == 1
    p = outcome.proposals[0]
    assert p.technique == Technique.RECOOK.value
    assert p.origin == "enrichment"
    assert p.origin != "glossary"
    assert 0.0 < p.confidence < 1.0
    assert p.review_status == "proposed"
    assert p.pending_validation is True
    raw = store.raw_fields[0]
    assert raw["technique"] == Technique.RECOOK.value
    assert "canon_verify" in raw["provenance_json"]  # C12 ran on re-cook
    types = [e.event_type for e in emitter.emitted]
    assert types[-1] is JobEventType.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# gate CLEARED + recook + UNLICENSED source → licensing gate REFUSES inside run
# ═══════════════════════════════════════════════════════════════════════════════
async def test_cleared_gate_unlicensed_source_refused_at_run():
    store = InMemoryProposalStore()
    runner = await _build_runner_via_factory(
        technique=Technique.RECOOK.value, unlocked=True,
        license_status=LicenseStatus.COPYRIGHTED,  # inadmissible
        store=store, budget=JobCostBudget(None), emitter=_emitter(),
    )
    # The gate let recook be selected (cleared), but the LICENSING gate refuses the
    # unlicensed source mid-run. UnlicensedSourceError is NOT a skippable per-gap
    # miss (unlike GenerationError/FabricationError) — it is a hard refusal, so the
    # runner fails the job and persists NOTHING (no proposal from an unlicensed src).
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("陳塘關")], context=_ctx(), entity_kind="location"
    )
    assert outcome.final_state == "failed"
    assert "UnlicensedSourceError" in (outcome.error or "")
    assert store.proposals == []  # unlicensed source → no proposal admitted


# ═══════════════════════════════════════════════════════════════════════════════
# re-cook's highest per-gap cost (12.0) binds on the cost-cap
# ═══════════════════════════════════════════════════════════════════════════════
async def test_recook_cost_binds_on_the_cost_cap():
    store = InMemoryProposalStore()
    # working cap = 2 * 12.0 = 24 → fits exactly 2 re-cooks, pauses before #3.
    budget = JobCostBudget(2 * RECOOK_GAP_COST, eval_reserve=0.0)
    runner = await _build_runner_via_factory(
        technique=Technique.RECOOK.value, unlocked=True,
        license_status=LicenseStatus.PUBLIC_DOMAIN,
        store=store, budget=budget, emitter=_emitter(),
    )
    gaps = [_gap(n) for n in ("蓬萊", "玉虛宮", "碧遊宮", "陳塘關")]
    outcome = await runner.run_job(
        job_id="job-1", gaps=gaps, context=_ctx(), entity_kind="location"
    )
    assert outcome.final_state == "paused"
    assert len(outcome.proposals) == 2
    assert outcome.spent == pytest.approx(2 * RECOOK_GAP_COST)


# ═══════════════════════════════════════════════════════════════════════════════
# No-regression: DEFAULT retrieval (P1) path unaffected by the gate
# ═══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("unlocked", [True, False])
async def test_default_retrieval_path_unaffected_by_gate(unlocked):
    store = InMemoryProposalStore()
    runner = await _build_runner_via_factory(
        technique=Technique.RETRIEVAL.value, unlocked=unlocked,
        license_status=LicenseStatus.PUBLIC_DOMAIN,
        store=store, budget=JobCostBudget(None), emitter=_emitter(),
    )
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("蓬萊")], context=_ctx(), entity_kind="location"
    )
    assert outcome.final_state == "completed"
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0].technique == Technique.RETRIEVAL.value
