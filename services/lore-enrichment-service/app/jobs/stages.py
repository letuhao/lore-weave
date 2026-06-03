"""Per-gap STAGE pipeline (RAID C14) — wires C9/C10 → C11 → C12 for one gap.

The runner (``app.jobs.runner``) drives the JOB lifecycle (state machine, cost
cap, events); THIS module is the per-gap WORK: take one C7 :class:`Gap` and run
it through the existing P1 pipeline, returning a :class:`StageResult` the runner
then persists + emits events for. It ORCHESTRATES existing components only — it
implements no new gap/strategy/generation/verify logic.

Pipeline per gap (P1 = template + retrieval):
  1. **retrieval (C10)** — the retrieval strategy embeds the gap query and
     attaches ``cultural_grounding_ref`` passages, yielding a
     :class:`GroundedProposal` (the template scaffold's empty Chinese slots +
     the grounding). For a P1 job the retrieval strategy is the proposal source;
     the template strategy (C9) supplies the same scaffold shape and is run for
     its (free) cost estimate + as the deterministic fallback when there is no
     grounding to generate from.
  2. **generation (C11)** — the schema-governed generator fills each empty
     dimension from the grounding via the LLM seam, minting one H0-tagged
     :class:`EnrichedFact` per dimension (origin='enriched:<technique>',
     confidence<1.0, pending_validation). Refuses (raises) when grounding is
     empty — an unprovenanced fact is an H0 violation.
  3. **canon-verify (C12)** — annotate the facts (contradiction / anachronism /
     injection). Annotation only — never lifts quarantine, never canonizes.

H0: every fact leaving this module is born quarantined (the C11 chokepoint); the
verify step only annotates. NO write-back (C13), NO promote. NO model names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.gaps.model import Gap
from app.generation.generate import GenerationError, SchemaGovernedGenerator
from app.generation.provenance import EnrichedFact
from app.retrieval.grounding import compose_grounding
from app.retrieval.strategy import GroundedProposal, RetrievalStrategy
from app.strategies.base import StrategyContext, Technique
from app.strategies.draft_expand import DraftExpandError, DraftExpandStrategy
from app.strategies.fabrication import FabricationError, FabricationStrategy
from app.strategies.recook import ReCookError, ReCookStrategy
from app.verify.canon_verify import CanonVerifier
from app.verify.wiring import AnnotatedVerify, verify_and_annotate

__all__ = [
    "StageResult",
    "JobPipeline",
    "GapPipeline",
    "FabricationPipeline",
    "ReCookPipeline",
    "DraftExpandPipeline",
    "source_refs_from_grounding",
]


@dataclass(frozen=True)
class StageResult:
    """The output of running one gap through the P1 pipeline.

    ``facts`` is the H0-tagged generated content (one per missing dimension);
    ``proposal`` is the C10 grounded proposal (scope + grounding); ``verify`` is
    the C12 annotation. The runner persists these as one quarantined
    ``enrichment_proposal`` row + emits a ``proposal_created`` event."""

    gap: Gap
    proposal: GroundedProposal
    facts: list[EnrichedFact]
    verify: AnnotatedVerify
    source_refs: list[dict[str, Any]]


def source_refs_from_grounding(proposal: GroundedProposal) -> list[dict[str, Any]]:
    """Project the proposal's C10 grounding onto the persisted ``source_refs_json``
    shape (corpus_id + chunk_id + chunk_index + score). This is the proposal's
    provenance — what the generated content was grounded on."""
    return [
        {
            "corpus_id": g.corpus_id,
            "chunk_id": g.chunk_id,
            "chunk_index": g.chunk_index,
            "score": g.score,
        }
        for g in proposal.grounding
    ]


class JobPipeline(Protocol):
    """The per-gap pipeline contract the C14 runner drives (technique-agnostic).

    The runner does not care WHICH technique produces a gap's :class:`StageResult`
    — it only needs (1) ``run_gap`` to take one :class:`Gap` + context and return
    one quarantined :class:`StageResult` (raising :class:`GenerationError` /
    :class:`FabricationError` when the gap can't be grounded → the runner SKIPS it)
    and (2) ``technique_value`` for event/provenance tagging. Both the P1
    :class:`GapPipeline` (retrieval+generation) and the P2 :class:`FabricationPipeline`
    satisfy this — so the SAME runner enforces cost-cap + H0 + lifecycle for either
    technique, and the gate-aware factory (DEFERRED-054) decides which pipeline the
    runner is handed."""

    async def run_gap(
        self, gap: Gap, context: StrategyContext, *, jwt: str = ...
    ) -> StageResult: ...

    def technique_value(self) -> str: ...


class GapPipeline:
    """Run one gap through retrieval → generation → verify (C10/C11/C12).

    Construct with the C10 retrieval strategy, the C11 generator, and the C12
    verifier — all already built/registered upstream. :meth:`run_gap` is pure
    orchestration; it raises :class:`GenerationError` when a gap cannot be
    grounded/generated (the runner decides whether to skip or fail the job)."""

    def __init__(
        self,
        *,
        retrieval: RetrievalStrategy,
        generator: SchemaGovernedGenerator,
        verifier: CanonVerifier,
        grounding_providers: "list | None" = None,
        top_k: int = 5,
    ) -> None:
        self._retrieval = retrieval
        self._generator = generator
        self._verifier = verifier
        # de-bias C2: extra grounding providers (glossary canon + knowledge
        # build_context passages) composed on top of the corpus search, so an
        # EXTRACTED book grounds without re-ingesting chapters. Empty = legacy
        # corpus-only behavior (no regression).
        self._grounding_providers = grounding_providers or []
        self._top_k = top_k

    async def run_gap(
        self, gap: Gap, context: StrategyContext, *, jwt: str = ""
    ) -> StageResult:
        """Execute the P1 pipeline for one gap.

        1. retrieval (C10) → a grounded proposal (scaffold slots + corpus grounding).
        1b. de-bias C2 — COMPOSE extra grounding (glossary canon + knowledge passages)
            on top of the corpus refs, deduped + top-K, so an extracted book grounds
            on its existing digest (no re-ingest).
        2. generation (C11) → H0-tagged facts (raises GenerationError if the gap
           has no grounding — unprovenanced content is refused).
        3. canon-verify (C12) → annotation (never canonizes).
        """
        # 1. retrieval — one gap → one grounded proposal.
        proposals = await self._retrieval.run([gap], context)
        if not proposals:
            raise GenerationError(
                f"retrieval produced no proposal for {gap.canonical_name!r}"
            )
        proposal: GroundedProposal = proposals[0]

        # 1b. compose extra grounding (de-bias C2). The dimension dict keys are the
        # localized missing-dim labels (the same query shape retrieval used).
        if self._grounding_providers:
            composed = await compose_grounding(
                proposal.grounding,
                self._grounding_providers,
                canonical_name=proposal.canonical_name,
                missing_labels=list(proposal.dimensions.keys()),
                context=context,
                top_k=self._top_k,
            )
            proposal = proposal.model_copy(update={"grounding": composed})

        # 2. generation (C11 H0 chokepoint). Raises if grounding is empty.
        facts = await self._generator.generate(proposal, context)

        # 3. canon-verify (C12) — annotation only.
        verify = await verify_and_annotate(
            self._verifier, proposal, facts, jwt=jwt
        )

        return StageResult(
            gap=gap,
            proposal=proposal,
            facts=facts,
            verify=verify,
            source_refs=source_refs_from_grounding(proposal),
        )

    @staticmethod
    def technique_value() -> str:
        """The technique these P1 proposals carry (retrieval — it supplies the
        grounding the generation cites)."""
        return Technique.RETRIEVAL.value


class FabricationPipeline:
    """Run one gap through the P2 canon-grounded FABRICATION (C16).

    The gate-enforced (DEFERRED-054) counterpart to :class:`GapPipeline`: it
    ADAPTS a :class:`~app.strategies.fabrication.FabricationStrategy` to the same
    :class:`JobPipeline` contract the C14 runner drives, so the runner enforces the
    IDENTICAL cost-cap + H0 + lifecycle for fabrication that it does for retrieval.
    It implements no new generation/verify logic — it delegates to the strategy
    (which already chains retrieval → fabricate → C12 verify per gap) and projects
    the strategy's :class:`~app.strategies.fabrication.FabricatedProposal` onto the
    runner's :class:`StageResult` shape (same proposal/facts/verify triple).

    H0: every fact leaving here is the strategy's H0-tagged
    ``origin='enriched:fabrication'``, confidence<1.0, pending fact — quarantine is
    untouched. An ungroundable gap raises :class:`FabricationError`, which the
    runner treats EXACTLY like a P1 ungroundable gap (skip, never an unprovenanced
    fact). This pipeline is ONLY constructed once the gate-aware factory has
    confirmed the live eval gate is CLEARED — it never re-checks the gate itself
    (one enforcement point, the factory)."""

    def __init__(self, *, strategy: FabricationStrategy) -> None:
        self._strategy = strategy

    async def run_gap(
        self, gap: Gap, context: StrategyContext, *, jwt: str = ""
    ) -> StageResult:
        """Fabricate one gap and project the result onto :class:`StageResult`.

        Delegates to the strategy (retrieve grounding → LLM fabricate → C12 verify)
        for the single gap, then maps its :class:`FabricatedProposal` onto the
        runner's stage shape. Raises :class:`FabricationError` (ungroundable →
        runner skips) — never mints an unprovenanced fact (H0)."""
        results = await self._strategy.run([gap], context, jwt=jwt)
        if not results:
            raise FabricationError(
                f"fabrication produced no proposal for {gap.canonical_name!r}"
            )
        fab = results[0]
        return StageResult(
            gap=gap,
            proposal=fab.proposal,
            facts=fab.facts,
            verify=fab.verify,
            source_refs=source_refs_from_grounding(fab.proposal),
        )

    @staticmethod
    def technique_value() -> str:
        """The technique these P2 proposals carry (fabrication)."""
        return Technique.FABRICATION.value


class ReCookPipeline:
    """Run one gap through the P3 RE-COOK (C17 — gate-enforced + licensing-gated).

    The P3 counterpart to :class:`FabricationPipeline`: it ADAPTS a
    :class:`~app.strategies.recook.ReCookStrategy` to the same :class:`JobPipeline`
    contract the C14 runner drives, so the runner enforces the IDENTICAL cost-cap +
    H0 + lifecycle for re-cook that it does for retrieval / fabrication. It
    implements no new generation/verify/licensing logic — it delegates to the
    strategy (which already chains retrieval → licensing-check → re-contextualise →
    C12 verify per gap) and projects the strategy's
    :class:`~app.strategies.recook.ReCookedProposal` onto the runner's
    :class:`StageResult` shape (same proposal/facts/verify triple).

    H0: every fact leaving here is the strategy's H0-tagged
    ``origin='enriched:recook'``, confidence<1.0, pending fact — quarantine is
    untouched. An ungroundable gap raises :class:`ReCookError`, which the runner
    treats EXACTLY like a P1/P2 ungroundable gap (skip, never an unprovenanced
    fact). An UNLICENSED source raises
    :class:`~app.strategies.licensing.UnlicensedSourceError`, which PROPAGATES
    (the job is refused) — re-cook never silently consumes unlicensed material.
    This pipeline is ONLY constructed once the gate-aware factory has confirmed the
    live eval gate is CLEARED — it never re-checks the gate itself (one enforcement
    point, the factory)."""

    def __init__(self, *, strategy: ReCookStrategy) -> None:
        self._strategy = strategy

    async def run_gap(
        self, gap: Gap, context: StrategyContext, *, jwt: str = ""
    ) -> StageResult:
        """Re-cook one gap and project the result onto :class:`StageResult`.

        Delegates to the strategy (retrieve → licensing-check → re-contextualise →
        C12 verify) for the single gap, then maps its
        :class:`~app.strategies.recook.ReCookedProposal` onto the runner's stage
        shape. Raises :class:`ReCookError` (ungroundable → runner skips) — never
        mints an unprovenanced fact (H0). An UnlicensedSourceError propagates (the
        source is refused)."""
        results = await self._strategy.run([gap], context, jwt=jwt)
        if not results:
            raise ReCookError(
                f"re-cook produced no proposal for {gap.canonical_name!r}"
            )
        rc = results[0]
        return StageResult(
            gap=gap,
            proposal=rc.proposal,
            facts=rc.facts,
            verify=rc.verify,
            source_refs=source_refs_from_grounding(rc.proposal),
        )

    @staticmethod
    def technique_value() -> str:
        """The technique these P3 proposals carry (recook)."""
        return Technique.RECOOK.value


class DraftExpandPipeline:
    """Run one gap through DRAFT EXPANSION (Compose mode D — P1, ungated).

    The mode-D counterpart to :class:`GapPipeline`: it ADAPTS a
    :class:`~app.strategies.draft_expand.DraftExpandStrategy` to the same
    :class:`JobPipeline` contract the C14 runner drives, so the runner enforces the
    IDENTICAL cost-cap + H0 + lifecycle for draft expansion that it does for the
    other techniques. It implements no new generation/verify logic — it delegates to
    the strategy (which makes its OWN seeded LLM call, mints the synthetic
    ``author_draft`` provenance, and runs C12 verify) and projects the strategy's
    :class:`~app.strategies.draft_expand.DraftExpandedProposal` onto the runner's
    :class:`StageResult`.

    Crucially this branch is wired EXPLICITLY (not the ``else → GapPipeline``
    fall-through): mode D has EMPTY grounding, and GapPipeline's generator REFUSES
    empty grounding — D must never fall into it. Its ``source_refs`` come from the
    facts' synthetic ``author_draft`` ref (the proposal grounding is empty by
    design), so the ③ regurgitation guard (output vs corpus) is mechanically N/A
    (F8). H0: every fact is origin='enriched:compose_draft', confidence<1.0,
    pending. An empty seed / unrepairable output raises
    :class:`DraftExpandError`, which the runner treats EXACTLY like a P1 ungroundable
    gap (skip, never an unprovenanced fact)."""

    def __init__(self, *, strategy: DraftExpandStrategy) -> None:
        self._strategy = strategy

    async def run_gap(
        self, gap: Gap, context: StrategyContext, *, jwt: str = ""
    ) -> StageResult:
        """Expand one gap's draft and project the result onto :class:`StageResult`.

        Delegates to the strategy (own seeded generation → C11 chokepoint → C12
        verify) for the single gap, then maps its
        :class:`~app.strategies.draft_expand.DraftExpandedProposal` onto the runner's
        stage shape. The ``source_refs`` are taken from the facts' synthetic
        ``author_draft`` ref (the proposal carries no corpus grounding). Raises
        :class:`DraftExpandError` (empty seed / unrepairable → runner skips) — never
        mints an unprovenanced fact (H0)."""
        results = await self._strategy.run([gap], context, jwt=jwt)
        if not results:
            raise DraftExpandError(
                f"draft expansion produced no proposal for {gap.canonical_name!r}"
            )
        de = results[0]
        return StageResult(
            gap=gap,
            proposal=de.proposal,
            facts=de.facts,
            verify=de.verify,
            source_refs=_source_refs_from_facts(de.facts),
        )

    @staticmethod
    def technique_value() -> str:
        """The technique these mode-D proposals carry (compose_draft)."""
        return Technique.COMPOSE_DRAFT.value


def _source_refs_from_facts(facts: list[EnrichedFact]) -> list[dict[str, Any]]:
    """Project the facts' synthetic ``author_draft`` source_refs onto the persisted
    ``source_refs_json`` shape (mode D has no corpus grounding to project from). The
    refs are identical across a draft's facts, so de-dup by (corpus_id, chunk_id)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for f in facts:
        for r in f.source_refs:
            key = (r.corpus_id, r.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "corpus_id": r.corpus_id,
                "chunk_id": r.chunk_id,
                "chunk_index": r.chunk_index,
                "score": r.score,
            })
    return out
