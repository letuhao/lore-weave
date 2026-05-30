"""End-to-end job-runner orchestration tests (RAID C14).

The LLM + retrieval are MOCKED for determinism (per the brief: unit tests mock
the LLM). Asserts the runner orchestrates C9/C10→C11→C12→persist correctly:
  * stage chaining: each gap → retrieval → generate → verify → one persisted,
    QUARANTINED proposal; job reaches `completed`;
  * H0 on EVERY persisted proposal: origin='enrichment', confidence<1.0,
    review_status='proposed', pending_validation=True (never canon);
  * lifecycle events emitted in order (started → per-gap stage/proposal →
    completed), idempotent;
  * cost-cap breach PAUSES (resumable) before a gap — never crashes, eval
    reserve protected;
  * an ungroundable gap is SKIPPED (no unprovenanced fact), not a job failure;
  * an unexpected stage error FAILS the job cleanly (failed + job.failed event).
"""

from __future__ import annotations

import pytest

from app.gaps.model import Dimension, EntityKind, Gap, dimensions_for
from app.generation.generate import GenerationError, SchemaGovernedGenerator
from app.jobs.cost import GapCostModel, JobCostBudget
from app.jobs.events import JobEventEmitter, JobEventType
from app.jobs.proposal_store import InMemoryProposalStore
from app.jobs.runner import JobRunner
from app.jobs.stages import GapPipeline
from app.retrieval.strategy import GroundedProposal, GroundingRef
from app.strategies.base import CostEstimate, StrategyContext, Technique
from app.strategies.template import TemplateStrategy
from app.verify.canon_verify import CanonVerifier
from app.clients.port import NullKnowledgeRead

# asyncio_mode=auto (pytest.ini) handles async tests; no module-wide mark needed
# (a module mark would warn on the pure-sync collector/H0-guard tests below).

_USER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
_PROJECT = "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39"

_LOCATIONS = ["蓬萊", "玉虛宮", "碧遊宮", "陳塘關"]

_VALID_COMPLETION = (
    '{"历史": "上古即为仙真所居，岁月悠远。", '
    '"地理": "地处东海之中，云雾环绕。", '
    '"文化": "重道法，轻俗务，岁时祭海。", '
    '"features": "灵气充沛，奇花异草。", '
    '"inhabitants": "仙人、修真者居之。"}'
)


# ── fakes ─────────────────────────────────────────────────────────────────────


class _FakeRetrieval:
    """A retrieval strategy stub: returns one grounded proposal per gap with a
    fixed grounding (so generation has provenance). Matches RetrievalStrategy's
    `run` signature (duck-typed)."""

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
                    entity_kind=gap.entity_kind.value,
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
    # All 5 dimensions missing (sparse canon) — the demo under-described case.
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


def _pipeline(*, grounded: bool = True) -> GapPipeline:
    return GapPipeline(
        retrieval=_FakeRetrieval(grounded=grounded),
        generator=SchemaGovernedGenerator(complete=_const_complete(_VALID_COMPLETION)),
        verifier=_verifier(),
    )


def _emitter(producer=None) -> JobEventEmitter:
    return JobEventEmitter(
        producer, job_id="job-1", project_id=_PROJECT, user_id=_USER
    )


def _runner(*, store, pipeline, budget, emitter) -> JobRunner:
    return JobRunner(
        store=store,
        pipeline=pipeline,
        cost_strategy=TemplateStrategy(),  # free estimate by default
        emitter=emitter,
        budget=budget,
    )


# ── happy path: full chain → completed, every proposal H0 ─────────────────────


async def test_full_pipeline_completes_with_h0_proposals():
    store = InMemoryProposalStore()
    emitter = _emitter()
    runner = _runner(
        store=store, pipeline=_pipeline(),
        budget=JobCostBudget(None), emitter=emitter,
    )
    gaps = [_gap(n) for n in _LOCATIONS]
    outcome = await runner.run_job(
        job_id="job-1", gaps=gaps, context=_ctx(), entity_kind="location"
    )

    assert outcome.final_state == "completed"
    assert len(outcome.proposals) == len(_LOCATIONS)
    # H0 on EVERY persisted proposal — quarantined, never canon.
    for p in outcome.proposals:
        assert p.origin == "enrichment"
        assert p.origin != "glossary"
        assert 0.0 < p.confidence < 1.0
        assert p.review_status == "proposed"
        assert p.pending_validation is True
        assert set(p.dimensions.keys()) == {"历史", "地理", "文化", "features", "inhabitants"}
    # the persisted raw fields carry the H0 columns + folded dimensions.
    for f in store.raw_fields:
        assert f["origin"] == "enrichment"
        assert f["confidence"] < 1.0
        assert f["review_status"] == "proposed"
        assert "dimensions" in f["provenance_json"]
        assert "canon_verify" in f["provenance_json"]  # C12 annotation folded in


async def test_lifecycle_events_emitted_in_order():
    store = InMemoryProposalStore()
    emitter = _emitter()
    runner = _runner(
        store=store, pipeline=_pipeline(),
        budget=JobCostBudget(None), emitter=emitter,
    )
    gaps = [_gap("蓬萊")]
    await runner.run_job(job_id="job-1", gaps=gaps, context=_ctx())
    types = [e.event_type for e in emitter.emitted]
    assert types[0] is JobEventType.STARTED
    assert JobEventType.STAGE_COMPLETED in types
    assert JobEventType.PROPOSAL_CREATED in types
    assert types[-1] is JobEventType.COMPLETED


async def test_job_marked_completed_in_store():
    store = InMemoryProposalStore()
    runner = _runner(
        store=store, pipeline=_pipeline(),
        budget=JobCostBudget(None), emitter=_emitter(),
    )
    await runner.run_job(job_id="job-1", gaps=[_gap("蓬萊")], context=_ctx())
    assert store.jobs["job-1"]["status"] == "completed"
    assert store.jobs["job-1"]["proposals_total"] == 1


# ── cost-cap: breach PAUSES (resumable), never crashes ────────────────────────


class _CostlyStrategy(TemplateStrategy):
    """A strategy whose per-gap estimate is non-zero so the cap can bite."""

    def estimate_cost(self, gap_batch):
        n = len(gap_batch)
        return CostEstimate(
            technique=Technique.TEMPLATE, gap_count=n, units=float(n), cost=5.0 * n
        )


async def test_cost_cap_breach_pauses_before_gap():
    store = InMemoryProposalStore()
    emitter = _emitter()
    # working cap = 12 − 2 = 10 → fits 2 gaps (5 each), pauses before the 3rd.
    budget = JobCostBudget(12.0, eval_reserve=2.0)
    runner = JobRunner(
        store=store, pipeline=_pipeline(), cost_strategy=_CostlyStrategy(),
        emitter=emitter, budget=budget,
    )
    gaps = [_gap(n) for n in _LOCATIONS]  # 4 gaps
    outcome = await runner.run_job(job_id="job-1", gaps=gaps, context=_ctx())

    assert outcome.final_state == "paused"
    assert outcome.paused_at_gap is not None
    assert len(outcome.proposals) == 2  # only the two that fit
    assert outcome.spent == pytest.approx(10.0)  # never exceeded the working cap
    # eval reserve untouched; a paused event was emitted.
    assert any(e.event_type is JobEventType.PAUSED for e in emitter.emitted)
    assert store.jobs["job-1"]["status"] == "paused"
    # NO completed event — the job paused, it did not finish.
    assert not any(e.event_type is JobEventType.COMPLETED for e in emitter.emitted)


# ── BLOCK-1: cap PAUSES on the REAL cost path (GapCostModel = what assembly ────
#    wires), NOT a fabricated _CostlyStrategy. This closes the mock-only
#    false-green: with the inert TemplateStrategy estimate (cost 0.0) the cap
#    NEVER fired in production; GapCostModel is the same non-zero cost the live
#    runner now charges, so a runaway job is paused before unbounded overshoot.


def _real_runner(*, store, pipeline, budget, emitter) -> JobRunner:
    """A runner wired EXACTLY like app.jobs.assembly.build_live_runner: the
    NON-ZERO GapCostModel as the cost path (not the free TemplateStrategy)."""
    return JobRunner(
        store=store, pipeline=pipeline, cost_strategy=GapCostModel(),
        emitter=emitter, budget=budget,
    )


async def test_cost_cap_pauses_on_real_cost_path_not_template():
    store = InMemoryProposalStore()
    emitter = _emitter()
    # GapCostModel charges PER_GAP_WORKING_COST (=5.0) per gap. working cap =
    # 12 − 2 = 10 → fits 2 gaps, pauses before the 3rd. With the OLD inert wiring
    # (TemplateStrategy, cost 0.0) this would NEVER pause (all 4 would run free).
    from app.jobs.cost import PER_GAP_WORKING_COST

    budget = JobCostBudget(2.0 + 2 * PER_GAP_WORKING_COST, eval_reserve=2.0)
    runner = _real_runner(
        store=store, pipeline=_pipeline(), budget=budget, emitter=emitter,
    )
    gaps = [_gap(n) for n in _LOCATIONS]  # 4 gaps
    outcome = await runner.run_job(job_id="job-1", gaps=gaps, context=_ctx())

    assert outcome.final_state == "paused"
    assert outcome.paused_at_gap is not None
    assert len(outcome.proposals) == 2  # only the two that fit the working cap
    assert outcome.spent == pytest.approx(2 * PER_GAP_WORKING_COST)
    # budget protected: spend never reached or passed the working cap's headroom.
    assert outcome.spent <= budget.working_cap
    assert store.jobs["job-1"]["status"] == "paused"
    assert not any(e.event_type is JobEventType.COMPLETED for e in emitter.emitted)


async def test_runaway_job_cannot_run_unbounded_under_tiny_cap():
    """A tiny max_spend pauses on the REAL cost path before doing any work —
    proving the cap can stop a runaway (the safety control is no longer inert)."""
    from app.jobs.cost import PER_GAP_WORKING_COST

    store = InMemoryProposalStore()
    # working cap < one gap's real cost → pauses BEFORE the very first gap.
    budget = JobCostBudget(PER_GAP_WORKING_COST * 0.5, eval_reserve=0.0)
    runner = _real_runner(
        store=store, pipeline=_pipeline(), budget=budget, emitter=_emitter(),
    )
    gaps = [_gap(n) for n in _LOCATIONS]  # 4 gaps — none should run
    outcome = await runner.run_job(job_id="job-1", gaps=gaps, context=_ctx())

    assert outcome.final_state == "paused"
    assert outcome.proposals == []  # NOTHING ran — cap bit immediately
    assert outcome.spent == 0.0  # budget fully protected


# ── WARN-1: resume/re-run is SAFE — no double-charge, no duplicate proposals ───


async def test_rerun_does_not_duplicate_proposals():
    """A re-run over the SAME job_id + gaps reloads each gap's existing proposal
    (idempotent persist) instead of inserting duplicates."""
    store = InMemoryProposalStore()  # shared across both runs (same DB)
    gaps = [_gap(n) for n in _LOCATIONS]

    run1 = await _real_runner(
        store=store, pipeline=_pipeline(),
        budget=JobCostBudget(None), emitter=_emitter(),
    ).run_job(job_id="job-1", gaps=gaps, context=_ctx())
    assert run1.final_state == "completed"
    assert len(run1.proposals) == len(_LOCATIONS)
    first_ids = {p.proposal_id for p in run1.proposals}

    # re-run the SAME job over the SAME gaps (e.g. an operator re-trigger).
    run2 = await _real_runner(
        store=store, pipeline=_pipeline(),
        budget=JobCostBudget(None), emitter=_emitter(),
    ).run_job(job_id="job-1", gaps=gaps, context=_ctx())
    assert run2.final_state == "completed"
    # NO new rows: the store still holds exactly one proposal per gap.
    assert len(store.proposals) == len(_LOCATIONS)
    # every re-run proposal reloaded the SAME existing row (deduped).
    assert {p.proposal_id for p in run2.proposals} == first_ids
    assert all(p.deduped for p in run2.proposals)
    assert sorted(run2.deduped_gaps) == sorted(g.target_ref for g in gaps)


async def test_resume_seeds_spent_so_budget_not_reset():
    """A resumed run seeds the budget with the prior spend (build_live_runner's
    spent_so_far) so it does NOT reset to 0 and double-spend up to the cap."""
    from app.jobs.cost import PER_GAP_WORKING_COST

    store = InMemoryProposalStore()
    gaps = [_gap(n) for n in _LOCATIONS]  # 4 gaps

    # Run 1: cap fits 2 gaps, pauses; prior spend = 2 * per-gap cost.
    cap = 2 * PER_GAP_WORKING_COST  # working cap (no eval reserve)
    run1 = await _real_runner(
        store=store, pipeline=_pipeline(),
        budget=JobCostBudget(cap, eval_reserve=0.0), emitter=_emitter(),
    ).run_job(job_id="job-1", gaps=gaps, context=_ctx())
    assert run1.final_state == "paused"
    prior_spent = run1.spent
    assert prior_spent == pytest.approx(2 * PER_GAP_WORKING_COST)

    # Resume: seed the budget with the prior spend. The cap is ALREADY consumed,
    # so the resumed run must pause immediately (NOT re-spend up to the cap).
    resumed_budget = JobCostBudget(cap, eval_reserve=0.0, spent=prior_spent)
    run2 = await _real_runner(
        store=store, pipeline=_pipeline(), budget=resumed_budget, emitter=_emitter(),
    ).run_job(job_id="job-1", gaps=gaps, context=_ctx())
    assert run2.final_state == "paused"
    # the resumed run added NO new spend (budget was already at the cap).
    assert run2.spent == pytest.approx(prior_spent)
    # and it did NOT duplicate the 2 proposals run 1 already persisted.
    assert len(store.proposals) == 2


# ── ungroundable gap is SKIPPED (H0: no unprovenanced fact), not a failure ─────


async def test_ungroundable_gap_skipped_not_failed():
    store = InMemoryProposalStore()
    runner = _runner(
        store=store, pipeline=_pipeline(grounded=False),  # no grounding
        budget=JobCostBudget(None), emitter=_emitter(),
    )
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("蓬萊")], context=_ctx()
    )
    assert outcome.final_state == "completed"  # job still completes
    assert outcome.proposals == []  # nothing persisted (refused unprovenanced)
    assert "loc:蓬萊" in outcome.skipped_gaps


# ── unexpected stage error FAILS the job cleanly ──────────────────────────────


class _BrokenGenerator(SchemaGovernedGenerator):
    async def generate(self, proposal, context):
        raise RuntimeError("upstream exploded")


async def test_unexpected_error_fails_job():
    store = InMemoryProposalStore()
    emitter = _emitter()
    pipeline = GapPipeline(
        retrieval=_FakeRetrieval(),
        generator=_BrokenGenerator(complete=_const_complete(_VALID_COMPLETION)),
        verifier=_verifier(),
    )
    runner = JobRunner(
        store=store, pipeline=pipeline, cost_strategy=TemplateStrategy(),
        emitter=emitter, budget=JobCostBudget(None),
    )
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("蓬萊")], context=_ctx()
    )
    assert outcome.final_state == "failed"
    assert outcome.error is not None and "upstream exploded" in outcome.error
    assert any(e.event_type is JobEventType.FAILED for e in emitter.emitted)
    assert store.jobs["job-1"]["status"] == "failed"


# ── GenerationError vs ungroundable: a no-dimension gap is skipped too ─────────


async def test_generation_error_surfaces_as_skip():
    store = InMemoryProposalStore()

    class _AlwaysGenError(SchemaGovernedGenerator):
        async def generate(self, proposal, context):
            raise GenerationError("unrepairable")

    pipeline = GapPipeline(
        retrieval=_FakeRetrieval(),
        generator=_AlwaysGenError(complete=_const_complete("{}")),
        verifier=_verifier(),
    )
    runner = JobRunner(
        store=store, pipeline=pipeline, cost_strategy=TemplateStrategy(),
        emitter=_emitter(), budget=JobCostBudget(None),
    )
    outcome = await runner.run_job(
        job_id="job-1", gaps=[_gap("蓬萊")], context=_ctx()
    )
    assert outcome.final_state == "completed"
    assert outcome.proposals == []
    assert outcome.skipped_gaps == ["loc:蓬萊"]


# ── persistence H0 guard + SSE collector (pure unit) ──────────────────────────


def test_build_proposal_fields_rejects_canon_confidence():
    from app.generation.provenance import make_enriched_fact, SourceRef
    from app.jobs.proposal_store import build_proposal_fields

    fact = make_enriched_fact(
        user_id=_USER, project_id=_PROJECT, entity_kind="location",
        canonical_name="蓬萊", target_ref="loc:蓬萊", dimension="历史",
        content="上古仙山。", technique="retrieval",
        source_refs=[SourceRef(corpus_id="c", chunk_id="k", chunk_index=0, score=0.7)],
        model_ref="ref", confidence=0.3, qualified_origin=True,
    )
    # confidence outside (0,1.0) is an H0 violation — refused before the DB.
    with pytest.raises(ValueError):
        build_proposal_fields(
            user_id=_USER, project_id=_PROJECT, entity_kind="location",
            canonical_name="蓬萊", target_ref="loc:蓬萊", technique="retrieval",
            confidence=1.0, facts=[fact], verify=None, source_refs=[],
        )


def test_collect_stream_text_concatenates_token_deltas():
    from app.generation.complete import collect_stream_text

    sse = (
        "event: token\ndata: {\"event\":\"token\",\"delta\":\"蓬\"}\n\n"
        "event: reasoning\ndata: {\"event\":\"reasoning\",\"delta\":\"<think>\"}\n\n"
        "event: token\ndata: {\"event\":\"token\",\"delta\":\"萊\"}\n\n"
        "event: done\ndata: {\"event\":\"done\"}\n\n"
    )
    # only token deltas collected; reasoning dropped.
    assert collect_stream_text(sse) == "蓬萊"


def test_collect_stream_text_raises_on_error_frame():
    from app.generation.complete import CompletionSeamError, collect_stream_text

    sse = "event: error\ndata: {\"event\":\"error\",\"message\":\"boom\"}\n\n"
    with pytest.raises(CompletionSeamError):
        collect_stream_text(sse)
