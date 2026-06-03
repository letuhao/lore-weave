"""End-to-end RUNNER ↔ gate-aware factory wiring (RAID C16, DEFERRED-054 e2e).

WARN-1 closes the C14/054-shape false-green: before this, the gate-aware factory
+ FabricationStrategy were correct in isolation but NOT on the production job
path — ``build_live_runner`` hardwired the P1 GapPipeline and never called the
factory, so the gate never gated a REAL job. These tests drive the RUNNER (the
thing ``POST /jobs`` → ``build_live_runner`` builds) through the SAME selection
logic the assembly uses, with a fake gate reader, and prove:

  * gate LOCKED + technique=fabrication → selection RAISES InactiveStrategyError
    (the job is refused; the runner is never built) — gate enforced end-to-end;
  * gate CLEARED + technique=fabrication → the runner is handed a
    FabricationPipeline and produces H0-tagged (origin='enriched:fabrication',
    conf<1.0, quarantined) proposals — fabrication runs only when unlocked;
  * gate CLEARED + technique=fabrication → the cost-cap charges the FABRICATION
    per-gap cost (8.0), so the higher P2 cost actually binds (fab_cost_binds);
  * DEFAULT path (retrieval, P1) works regardless of the gate — no regression to
    the C14 demo path.

The LLM + retrieval are MOCKED (deterministic; per the brief unit tests mock the
LLM). The point is the WIRING: factory.select → pipeline choice → JobRunner.
"""

from __future__ import annotations

import pytest

from app.gaps.model import Dimension, EntityKind, Gap, dimensions_for
from app.generation.generate import SchemaGovernedGenerator
from app.jobs.cost import GapCostModel, JobCostBudget
from app.jobs.events import JobEventEmitter, JobEventType
from app.jobs.proposal_store import InMemoryProposalStore
from app.jobs.runner import JobRunner
from app.jobs.stages import FabricationPipeline, GapPipeline
from app.retrieval.strategy import GroundedProposal, GroundingRef
from app.strategies.base import EnrichmentStrategy, StrategyContext, Technique
from app.strategies.fabrication import FABRICATION_GAP_COST, FabricationStrategy
from app.strategies.factory import GateAwareStrategyFactory, LiveGateStatus
from app.strategies.registry import InactiveStrategyError
from app.verify.canon_verify import CanonVerifier
from app.clients.port import NullKnowledgeRead

# asyncio_mode=auto (pytest.ini) — async tests run without an explicit marker.

_USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
_PROJECT = "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39"
_SUITE = "enrichment-v1"

_VALID_COMPLETION = (
    '{"历史": "上古即为仙真所居，岁月悠远。", '
    '"地理": "地处东海之中，云雾环绕。", '
    '"文化": "重道法，轻俗务，岁时祭海。", '
    '"features": "灵气充沛，奇花异草。", '
    '"inhabitants": "仙人、修真者居之。"}'
)


# ── fakes (mirror test_job_runner / test_fabrication_strategy) ─────────────────


class _FakeRetrieval:
    """Quacks like RetrievalStrategy.run — one grounded proposal per gap with a
    fixed grounding so generation/fabrication has provenance."""

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
                        corpus_id="corpus-shanhaijing",
                        chunk_id="chunk-1",
                        chunk_index=1,
                        excerpt=f"{gap.canonical_name}在东海之中，仙人居之。",
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
    """A fake GateStatusReader — the live persisted gate the assembly reads,
    stubbed for determinism. ``unlocked`` mirrors a passing/failing eval run."""

    async def _read(user_id, project_id, suite_version) -> LiveGateStatus:
        if not unlocked:
            return LiveGateStatus.locked(suite_version)
        return LiveGateStatus(
            has_run=True,
            p2_p3_unlocked=True,
            suite_version=suite_version,
            composite=96.0,
            passed=True,
        )

    return _read


def _factory(*, unlocked: bool) -> GateAwareStrategyFactory:
    """Build the factory EXACTLY like app.jobs.assembly.build_live_runner: both
    the P1 retrieval marker and the P2 fabrication strategy registered, over the
    (stubbed) live gate reader."""
    retrieval = _FakeRetrieval()
    fabrication = FabricationStrategy(
        retrieval=retrieval,
        complete=_const_complete(_VALID_COMPLETION),
        verifier=_verifier(),
    )
    return GateAwareStrategyFactory(
        gate_reader=_gate_reader(unlocked=unlocked),
        strategies=[retrieval, fabrication],
        suite_version=_SUITE,
    )


async def _build_runner_via_factory(
    *, technique: str, unlocked: bool, store, budget, emitter
) -> JobRunner:
    """Replicate the assembly's gate-enforced selection → pipeline → runner.

    This is the SAME path ``build_live_runner`` takes (factory.select honours the
    live gate; the resolved technique picks the pipeline + cost model). Raises
    InactiveStrategyError when the requested P2 technique is gate-locked — i.e.
    the job is refused BEFORE a runner exists, gate enforced end-to-end."""
    factory = _factory(unlocked=unlocked)
    selected: EnrichmentStrategy = await factory.select(
        technique, user_id=_USER, project_id=_PROJECT
    )
    if selected.technique is Technique.FABRICATION:
        pipeline = FabricationPipeline(strategy=selected)  # type: ignore[arg-type]
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
# WARN-1: gate LOCKED + technique=fabrication → the RUNNER is REFUSED
# ═══════════════════════════════════════════════════════════════════════════════


async def test_locked_gate_refuses_fabrication_job_before_runner():
    """The C14/054 false-green closed: a fabrication job while the gate is LOCKED
    is REFUSED at selection — the runner is never built, fabrication never runs."""
    store = InMemoryProposalStore()
    with pytest.raises(InactiveStrategyError):
        await _build_runner_via_factory(
            technique=Technique.FABRICATION.value, unlocked=False,
            store=store, budget=JobCostBudget(None), emitter=_emitter(),
        )
    # Nothing was persisted — the gate stopped the job before any work.
    assert store.proposals == []


# ═══════════════════════════════════════════════════════════════════════════════
# WARN-1: gate CLEARED + technique=fabrication → the RUNNER fabricates (H0)
# ═══════════════════════════════════════════════════════════════════════════════


async def test_cleared_gate_runner_fabricates_h0_proposals():
    """Gate CLEARED → the runner is handed the FabricationPipeline and produces
    H0-tagged fabrication proposals (origin='enriched:fabrication', conf<1.0,
    quarantined). The runner — the thing POST /jobs drives — honors the gate."""
    store = InMemoryProposalStore()
    emitter = _emitter()
    runner = await _build_runner_via_factory(
        technique=Technique.FABRICATION.value, unlocked=True,
        store=store, budget=JobCostBudget(None), emitter=emitter,
    )
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("蓬萊")], context=_ctx(), entity_kind="location"
    )
    assert outcome.final_state == "completed"
    assert len(outcome.proposals) == 1
    p = outcome.proposals[0]
    # H0: the proposal carries the fabrication technique + quarantine markers.
    assert p.technique == Technique.FABRICATION.value
    assert p.origin == "enrichment"  # the proposal-row origin (≠ glossary)
    assert p.origin != "glossary"
    assert 0.0 < p.confidence < 1.0
    assert p.review_status == "proposed"
    assert p.pending_validation is True
    # the persisted facts are origin='enriched:fabrication' (the strategy chokepoint)
    raw = store.raw_fields[0]
    assert raw["technique"] == Technique.FABRICATION.value
    assert "dimensions" in raw["provenance_json"]
    assert "canon_verify" in raw["provenance_json"]  # C12 ran on fabrication
    # event stream completed (lifecycle honored for fabrication too)
    types = [e.event_type for e in emitter.emitted]
    assert types[-1] is JobEventType.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# WARN-1: fabrication's higher per-gap cost (8.0) actually binds on the cap
# ═══════════════════════════════════════════════════════════════════════════════


async def test_fabrication_cost_binds_on_the_cost_cap():
    """fab_cost_binds: with the FabricationStrategy as the cost model, the cap
    charges FABRICATION_GAP_COST (8.0)/gap — so a runaway P2 batch pauses sooner.
    A cap that fits 2 fabrications pauses before the 3rd (proving 8.0 binds, not
    the inert P1 GapCostModel of 5.0)."""
    store = InMemoryProposalStore()
    emitter = _emitter()
    # working cap = 2 * 8.0 = 16 → fits exactly 2 fabrications, pauses before #3.
    budget = JobCostBudget(2 * FABRICATION_GAP_COST, eval_reserve=0.0)
    runner = await _build_runner_via_factory(
        technique=Technique.FABRICATION.value, unlocked=True,
        store=store, budget=budget, emitter=emitter,
    )
    gaps = [_gap(n) for n in ("蓬萊", "玉虛宮", "碧遊宮", "陳塘關")]  # 4 gaps
    outcome = await runner.run_job(
        job_id="job-1", gaps=gaps, context=_ctx(), entity_kind="location"
    )
    assert outcome.final_state == "paused"
    assert len(outcome.proposals) == 2  # only the two the 8.0/gap cap fits
    assert outcome.spent == pytest.approx(2 * FABRICATION_GAP_COST)


# ═══════════════════════════════════════════════════════════════════════════════
# No-regression: the DEFAULT retrieval (P1) path works regardless of the gate
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("unlocked", [True, False])
async def test_default_retrieval_path_unaffected_by_gate(unlocked):
    """The C14 demo path (technique=retrieval, P1) is NEVER gated — it ships
    active and produces the proposals the gate scores. It must complete whether
    the gate is locked or cleared (no regression)."""
    store = InMemoryProposalStore()
    runner = await _build_runner_via_factory(
        technique=Technique.RETRIEVAL.value, unlocked=unlocked,
        store=store, budget=JobCostBudget(None), emitter=_emitter(),
    )
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("蓬萊")], context=_ctx(), entity_kind="location"
    )
    assert outcome.final_state == "completed"
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0].technique == Technique.RETRIEVAL.value
