"""Strategy (b) — RETRIEVAL grounding (RAID C10, Q-R2 P1 technique #2).

The second concrete :class:`~app.strategies.base.EnrichmentStrategy`. Given a
:class:`Gap` (a place + its MISSING dimensions, from the C7 engine) it embeds a
gap query, retrieves the top-K most-similar passages from the OWNED corpora
(山海经 + 封神演义) via the C10 store, and emits a :class:`GroundedProposal` whose
``cultural_grounding_ref`` cites the real corpus + chunk ids + similarity scores.

It REUSES knowledge-service ``/internal/embed`` for embedding (the embedding
model is a provider-registry ``model_ref`` on the :class:`StrategyContext` —
NEVER a hardcoded model name). It builds NO RAG framework, imports no langchain/
llamaindex, runs no web search.

Boundaries (locked — docs/raid/cycle_briefs/10_strategy-retrieval.md):
  * NO model-name string anywhere — the embed model is resolved via
    ``context.model_ref`` (a provider-registry user_model id). A guard test
    greps this module for any literal embed-model id.
  * NO LLM PROSE generation — that is C11. Retrieval only ATTACHES grounding
    passages; the dimension slots stay empty placeholders (the generation cycle
    fills them, citing the grounding this strategy attached).
  * H0 (enriched lore != canon): every :class:`GroundedProposal` is born
    ``origin='enrichment'``, ``technique='retrieval'``, ``review_status=
    'proposed'``, ``0 < confidence < 1.0``, ``pending_validation=True``. It is
    NEVER ``source_type='glossary'`` / confidence=1.0, and it writes NOTHING to
    glossary / KG — it only attaches a ``cultural_grounding_ref`` to a PROPOSAL.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.gaps.model import Gap, dimensions_for
from app.retrieval.store import ScoredChunk, SourceCorpusStore
from app.strategies.base import (
    CostEstimate,
    EnrichmentStrategy,
    StrategyContext,
    Technique,
)

__all__ = [
    "GroundingRef",
    "GroundedProposal",
    "RetrievalStrategy",
    "EmbedQueryFn",
    "RETRIEVAL_CONFIDENCE",
    "DEFAULT_TOP_K",
]

#: The injected query-embedding callable: (query, context) → one query vector.
#: Bound by ``app.retrieval.embedding.make_embed_query_fn`` to the C1 client +
#: the run's ``model_ref`` — the strategy never imports an HTTP/LLM client.
EmbedQueryFn = Callable[[str, StrategyContext], Awaitable[list[float]]]


# ── H0 constants (the makeup-lore markers for a grounded proposal) ────────────
#: A grounded (but un-generated) proposal's confidence. The C2 schema CHECKs
#: ``confidence > 0 AND < 1.0``. Grounding lifts confidence slightly above the
#: empty-scaffold floor (we now have cited evidence) but it remains near-zero —
#: nothing has been GENERATED yet, only grounded. H0: strictly < 1.0.
RETRIEVAL_CONFIDENCE: float = 0.05

#: How many passages to retrieve per gap query by default.
DEFAULT_TOP_K: int = 5

_ENRICHED_ORIGIN: str = "enrichment"
#: One embed call per gap query; abstract cost counts the queries (gaps).
_EMBED_UNIT_COST: float = 1.0


class GroundingRef(BaseModel):
    """One cultural-grounding citation: a retrieved corpus passage + its score.

    Maps onto a ``cultural_grounding_ref`` row (corpus + locator + excerpt) plus
    the similarity score the retrieval produced. The proposal carries a list of
    these; the strongest (highest score) is the anchor a later cycle persists as
    the proposal's ``cultural_grounding_ref_id``.
    """

    model_config = ConfigDict(frozen=True)

    corpus_id: str
    chunk_id: str
    chunk_index: int
    excerpt: str
    score: float

    @classmethod
    def from_scored(cls, scored: ScoredChunk) -> "GroundingRef":
        return cls(
            corpus_id=str(scored.corpus_id),
            chunk_id=str(scored.chunk_id),
            chunk_index=scored.chunk_index,
            excerpt=scored.content,
            score=round(scored.score, 6),
        )


class GroundedProposal(BaseModel):
    """An H0-stamped proposal grounded in retrieved corpus passages (C10 output).

    One per gap. Like the C9 :class:`ScaffoldedProposal` it carries the Q3 scope,
    the empty per-missing-dimension slots, and the H0 markers — PLUS the
    ``grounding`` list (the ``cultural_grounding_ref`` payload) citing the real
    corpus + chunk ids + scores that ground this place. The dimension slots stay
    EMPTY (generation is C11); retrieval supplies evidence, not prose.

    H0 by construction: ``technique`` fixed to ``retrieval``, ``origin`` to
    ``enrichment``, ``review_status`` to ``proposed``, ``confidence`` validated
    strictly between 0 and 1.0. A caller cannot flip it to canon.
    """

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    target_ref: str | None = None

    # empty per-missing-dimension slots (Chinese keys from C6) — filled in C11.
    dimensions: dict[str, str]

    # the cultural_grounding_ref payload: retrieved passages, strongest first.
    grounding: list[GroundingRef] = Field(default_factory=list)

    # ── H0 distinguishing markers (never canon) ───────────────────────────────
    origin: str = Field(default=_ENRICHED_ORIGIN)
    technique: str = Field(default=Technique.RETRIEVAL.value)
    review_status: str = Field(default="proposed")
    confidence: float = Field(default=RETRIEVAL_CONFIDENCE, gt=0.0, lt=1.0)
    pending_validation: bool = Field(default=True)
    provenance_json: dict[str, object] = Field(default_factory=dict)

    def has_grounding(self) -> bool:
        """True iff at least one corpus passage was attached as grounding."""
        return len(self.grounding) > 0


class RetrievalStrategy(EnrichmentStrategy):
    """Technique (b): corpus-grounded retrieval (tier P1).

    Registers under the ``retrieval`` key. Construct with the C10
    :class:`SourceCorpusStore` and an async ``embed_fn`` that reuses knowledge-
    service ``/internal/embed`` (the C1 ``KnowledgeClient.embed`` bound to the
    project's ``model_ref``). :meth:`run` embeds each gap's query, searches the
    project's corpus, and attaches the top-K passages as ``cultural_grounding_ref``
    on an H0 :class:`GroundedProposal`. NO model name, NO prose generation, NO
    write-back.
    """

    technique = Technique.RETRIEVAL

    def __init__(
        self,
        *,
        store: SourceCorpusStore,
        embed_query: EmbedQueryFn,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._store = store
        self._embed_query = embed_query
        self._top_k = top_k

    def estimate_cost(self, gap_batch: list[Gap]) -> CostEstimate:
        """One embed call per gap query. Cost counts the queries; pure +
        side-effect-free (no embed runs here — only the projection)."""
        n = len(gap_batch)
        return CostEstimate(
            technique=self.technique,
            gap_count=n,
            units=float(n),
            cost=_EMBED_UNIT_COST * n,
        )

    async def run(
        self,
        gap_batch: list[Gap],
        context: StrategyContext,
    ) -> list[GroundedProposal]:
        """Ground each gap in retrieved corpus passages.

        For each gap: build a query string, embed it (reusing /internal/embed via
        the injected ``embed_query`` with ``context.model_ref``), retrieve the
        top-K similar chunks scoped to the project (Q3), and emit one
        :class:`GroundedProposal` whose ``grounding`` cites them. Empty corpus →
        a proposal with NO grounding (still H0, never canon). Input order kept.
        """
        project_uuid = UUID(context.project_id)
        proposals: list[GroundedProposal] = []
        for gap in gap_batch:
            query = self._gap_query(gap)
            query_vector = await self._embed_query(query, context)
            scored: list[ScoredChunk] = await self._store.search(
                project_id=project_uuid, query_vector=query_vector, k=self._top_k
            )
            proposals.append(self._build_proposal(gap, context, scored))
        return proposals

    # ── internals ─────────────────────────────────────────────────────────────
    @staticmethod
    def _gap_query(gap: Gap) -> str:
        """Compose the retrieval query for a gap: the place's canonical name plus
        the source-faithful labels of its missing dimensions. Deterministic,
        Chinese-first (source language), no model-specific formatting."""
        labels = [
            spec.label
            for spec in dimensions_for(gap.entity_kind)
            if spec.dimension in set(gap.missing_dimensions)
        ]
        return gap.canonical_name + " " + " ".join(labels)

    @staticmethod
    def _dimension_slots(gap: Gap) -> dict[str, str]:
        """Empty Chinese-keyed slots, one per MISSING dimension (mirrors C9 —
        generation fills them in C11, citing the grounding attached here)."""
        missing = set(gap.missing_dimensions)
        return {
            spec.label: ""
            for spec in dimensions_for(gap.entity_kind)
            if spec.dimension in missing
        }

    def _build_proposal(
        self, gap: Gap, context: StrategyContext, scored: Sequence[ScoredChunk]
    ) -> GroundedProposal:
        grounding = [GroundingRef.from_scored(s) for s in scored]
        provenance = {
            "technique": Technique.RETRIEVAL.value,
            "source_gap": {
                "entity_kind": gap.entity_kind,
                "canonical_name": gap.canonical_name,
                "target_ref": gap.target_ref,
                "missing_dimensions": list(gap.missing_dimensions),
            },
            "retrieval": {
                "top_k": self._top_k,
                "grounding_count": len(grounding),
                # model_ref (NOT a model name) records WHICH embedding space this
                # retrieval used — drift between proposals is then auditable.
                "model_ref": context.model_ref,
            },
        }
        return GroundedProposal(
            user_id=context.user_id,
            project_id=context.project_id,
            entity_kind=gap.entity_kind,
            canonical_name=gap.canonical_name,
            target_ref=gap.target_ref,
            dimensions=self._dimension_slots(gap),
            grounding=grounding,
            provenance_json=provenance,
            # H0 markers come from model defaults — never set to canon.
        )
