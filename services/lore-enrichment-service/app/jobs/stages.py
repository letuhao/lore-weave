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
from typing import Any

from app.gaps.model import Gap
from app.generation.generate import GenerationError, SchemaGovernedGenerator
from app.generation.provenance import EnrichedFact
from app.retrieval.strategy import GroundedProposal, RetrievalStrategy
from app.strategies.base import StrategyContext, Technique
from app.verify.canon_verify import CanonVerifier
from app.verify.wiring import AnnotatedVerify, verify_and_annotate

__all__ = [
    "StageResult",
    "GapPipeline",
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
    ) -> None:
        self._retrieval = retrieval
        self._generator = generator
        self._verifier = verifier

    async def run_gap(
        self, gap: Gap, context: StrategyContext, *, jwt: str = ""
    ) -> StageResult:
        """Execute the P1 pipeline for one gap.

        1. retrieval (C10) → a grounded proposal (scaffold slots + grounding).
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
