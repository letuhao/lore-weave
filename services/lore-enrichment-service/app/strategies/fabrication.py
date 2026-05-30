"""Strategy (c) — canon-grounded FABRICATION (RAID C16, Q-R2 P2 technique #3).

The third concrete :class:`~app.strategies.base.EnrichmentStrategy` and the FIRST
P2 (higher-cost / higher-risk) technique. Where retrieval (C10) + generation
(C11) only fill a gap's empty dimensions with content the retrieved excerpts
DIRECTLY support ("严禁编造检索片段未支持的事实" — forbid anything the excerpts
don't back), fabrication generates NEW plausible detail that goes BEYOND pure
retrieval: it extrapolates within the constraints of canon — the entity itself,
its KG neighbourhood, and the locked 商周 / 封神演义 era + cultural frame — to
fill detail the source corpus is silent on.

This is canon-GROUNDED, NOT free invention:
  * every fabricated dimension still cites the C10 grounding refs (``source_refs``)
    + the KG-neighbourhood context as its grounding BASIS, so the provenance
    records WHAT the fabrication was anchored to;
  * the prompt instructs the model to stay consistent with canon and the era and
    to NEVER contradict the cited grounding — it may add plausible texture, not
    rewrite the world;
  * the output is the same H0-tagged :class:`~app.generation.provenance.EnrichedFact`
    the C11 chokepoint mints (``origin='enriched:fabrication'``, ``confidence<1.0``,
    quarantined, ``pending_validation=True``), with provenance explicitly flagging
    ``fabricated=True`` + the grounding basis;
  * the facts run through the C12 canon-verify (contradiction / anachronism /
    injection) BEFORE a proposal is created — an anachronistic or contradictory
    fabrication is flagged for the human, never silently admitted.

H0 (NON-NEGOTIABLE — fabrication is the HIGHEST makeup-risk technique): a
fabricated fact NEVER reaches the system as canon. It stays quarantined; only the
author's explicit promote (C13) can canonize it, and the permanent origin marker
survives promotion. There is NO write-back here (reuse C13 unchanged).

Gate enforcement (DEFERRED-054): this strategy registers under ``fabrication``
(tier P2) but is only SELECTABLE through the
:class:`~app.strategies.factory.GateAwareStrategyFactory`, which reads the live
C15 eval gate and refuses to activate P2 while the gate is LOCKED. The strategy
itself does not check the gate — that is the factory's job (one enforcement
point) — but it can never be obtained except via that gated path.

Boundaries (locked — docs/raid/cycle_briefs/16_strategy-fabrication.md):
  * REUSES C11 (``make_enriched_fact`` H0 chokepoint + ``repair_generation``) and
    C12 (``CanonVerifier``) unchanged — NO edits to generation/ or verify/.
  * NO model-name string — the generating model is resolved via provider-registry
    by ``context.model_ref`` (the injected ``CompleteFn`` seam, like C11). A guard
    test greps this module for any literal model id.
  * NO new write-back / proposal store / KG writer (C13 owns that). NO recook
    (C17). NO history/news/licensing (that is C17).
  * Output language = Chinese (源文一致, 封神演义 tone).
"""

from __future__ import annotations

from typing import Awaitable, Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.gaps.model import Gap
from app.generation.provenance import (
    GENERATION_CONFIDENCE,
    EnrichedFact,
    SourceRef,
    make_enriched_fact,
)
from app.generation.repair import RepairError, repair_generation
from app.retrieval.strategy import GroundedProposal, GroundingRef, RetrievalStrategy
from app.strategies.base import (
    CostEstimate,
    EnrichmentStrategy,
    StrategyContext,
    Technique,
)
from app.verify.canon_verify import CanonVerifier
from app.verify.wiring import AnnotatedVerify, verify_and_annotate

__all__ = [
    "CompleteFn",
    "NeighborFact",
    "FabricationError",
    "FabricatedProposal",
    "FabricationStrategy",
    "build_fabrication_prompt",
    "FABRICATION_CONFIDENCE",
    "FABRICATION_GAP_COST",
]


#: The injected LLM-completion seam: (prompt, context) → raw model text. Bound to
#: the provider-registry generation endpoint by ``model_ref`` on the context
#: (NEVER a model name) — IDENTICAL to the C11 seam. Tests inject a deterministic
#: stub; the real binding is the same ``app.generation.complete.make_complete_fn``.
CompleteFn = Callable[[str, StrategyContext], Awaitable[str]]


# ── H0 + cost constants ───────────────────────────────────────────────────────
#: A fabricated fact's confidence. It sits at the C11 generation level (content
#: now EXISTS) but is NEVER raised toward canon — fabrication is the highest
#: makeup-risk technique, so it carries the same low quarantine confidence and is
#: gated harder by the human review. H0: strictly ``0 < c < 1.0``.
FABRICATION_CONFIDENCE: float = GENERATION_CONFIDENCE

#: Per-gap abstract cost. Fabrication is P2 (higher cost than P1 retrieval): it
#: does the retrieval embed + assembles the KG neighbourhood + a richer LLM
#: completion (longer prompt, more reasoning). Declared HIGHER than the P1 per-gap
#: cost so the C8 cost-cap pauses/escalates a runaway fabrication batch sooner.
#: Unit-opaque (same abstract unit as every other CostEstimate) — NOT currency.
FABRICATION_GAP_COST: float = 8.0


class NeighborFact(BaseModel):
    """One KG-neighbourhood fact about (or related to) the entity being enriched.

    The canon-grounding context fabrication anchors to BEYOND the corpus excerpts:
    a related entity / relationship read from the knowledge graph (e.g. 玉虛宮 →
    元始天尊 居所, 闡教 总部). Read-only context (Q2 — never written here); the
    fabrication must stay consistent with these. Optional — when the KG is empty
    or down (Q6), fabrication proceeds on the corpus grounding alone (degraded).
    """

    model_config = ConfigDict(frozen=True)

    subject: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    object: str = Field(min_length=1)


class FabricationError(RuntimeError):
    """Raised when fabrication cannot produce a schema-valid set of facts.

    Mirrors C11 ``GenerationError`` semantics: an empty-grounding fabrication
    (nothing to anchor to → free invention, an H0 violation) or unrepairable
    model output is REJECTED, never emitted as a partial / untagged fact.
    """


class FabricatedProposal(BaseModel):
    """A canon-grounded fabrication result for one gap (the C16 output unit).

    Carries the C10 grounded proposal it extended, the H0-tagged fabricated facts
    (one per dimension), and the C12 verify annotation. The runner persists these
    as ONE quarantined ``enrichment_proposal`` row (reusing C13 write-back) — this
    class adds no persistence and no canon path.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    proposal: GroundedProposal
    facts: list[EnrichedFact]
    verify: AnnotatedVerify
    neighbors: list[NeighborFact] = Field(default_factory=list)


def _grounding_block(grounding: Sequence[GroundingRef]) -> str:
    """Format the C10 retrieved excerpts as the fabrication's source-faithful
    anchor block (Chinese, cited). Identical shape to the C11 prompt's block so
    the model sees the same evidence framing."""
    return "\n".join(
        f"［{i + 1}］（来源 {g.corpus_id}#{g.chunk_index}，相似度 {g.score}）{g.excerpt}"
        for i, g in enumerate(grounding)
    )


def _neighbor_block(neighbors: Sequence[NeighborFact]) -> str:
    """Format the KG-neighbourhood facts as additional canon context. Empty string
    when no neighbourhood is available (Q6 degrade — corpus grounding only)."""
    if not neighbors:
        return "（暂无知识图谱关联信息）"
    return "\n".join(
        f"・{n.subject} —{n.relation}→ {n.object}" for n in neighbors
    )


def build_fabrication_prompt(
    proposal: GroundedProposal,
    neighbors: Sequence[NeighborFact],
) -> str:
    """Build the canon-grounded FABRICATION prompt (Chinese, source-faithful).

    Distinct from the C11 retrieval-generation prompt: that one FORBIDS anything
    the excerpts don't directly support; this one PERMITS plausible extrapolation
    BUT bounds it hard — the fabrication must (1) stay consistent with the cited
    corpus excerpts + the KG neighbourhood, (2) never CONTRADICT them, (3) respect
    the locked 商周 / 封神演义 era (no later dynasties / modern tech / foreign
    faiths — the C12 anachronism frame), and (4) be Chinese in the original tone.
    The prompt contains NO model name and NO provider-specific tokens.
    """
    dims = list(proposal.dimensions.keys())
    keys_csv = "、".join(dims)
    json_skeleton = ", ".join(f'"{d}": "……"' for d in dims)
    return (
        f"你是一位深谙《封神演义》世界观的世界构建师。\n"
        f"地点「{proposal.canonical_name}」在原著中被提及却缺乏细节。"
        f"请在忠于原著与既有设定的前提下，为其合理地「补全·虚构」以下维度："
        f"{keys_csv}。\n"
        f"这是『有据虚构』而非凭空臆造，须遵守：\n"
        f"1. 必须与下列原著语料与知识图谱关联信息保持一致，"
        f"严禁与其相矛盾；\n"
        f"2. 仅可在上述依据之上做合情合理的延伸想象，"
        f"须符合商周·封神纪元的时代背景（不得出现后世朝代、近现代器物、外来宗教等）；\n"
        f"3. 内容必须为中文，文言-白话皆可，须与原著语气一致；\n"
        f"4. 仅输出一个 JSON 对象，键为上述维度名，值为对应中文描述，"
        f"不要输出任何额外说明。\n\n"
        f"原著与文化语料依据：\n{_grounding_block(proposal.grounding)}\n\n"
        f"知识图谱关联（同一世界观内的既有设定）：\n"
        f"{_neighbor_block(neighbors)}\n\n"
        f"请输出 JSON：{{{json_skeleton}}}"
    )


def _source_refs_from_grounding(grounding: list[GroundingRef]) -> list[SourceRef]:
    """Project the C10 grounding refs onto the H0 ``source_refs`` shape — the
    grounding BASIS every fabricated fact must cite (an empty basis = free
    invention = rejected)."""
    return [
        SourceRef(
            corpus_id=g.corpus_id,
            chunk_id=g.chunk_id,
            chunk_index=g.chunk_index,
            score=g.score,
        )
        for g in grounding
    ]


class FabricationStrategy(EnrichmentStrategy):
    """Technique (c): canon-grounded fabrication (tier P2, gate-enforced).

    Registers under the ``fabrication`` key but is ONLY selectable through the
    :class:`~app.strategies.factory.GateAwareStrategyFactory` (DEFERRED-054 — the
    live C15 gate must be CLEARED). Construct with the C10 retrieval strategy (to
    obtain the grounded proposal + grounding basis), the injected C11-style
    ``CompleteFn`` (provider-registry by ``model_ref``), the C12 canon-verifier,
    and an optional KG-neighbourhood lookup.

    :meth:`run` per gap: retrieve grounding (C10) → fabricate the missing
    dimensions from grounding + KG neighbourhood + era frame (LLM) → repair
    (C11 ``repair_generation``) → H0-tag via the C11 chokepoint (one
    ``origin='enriched:fabrication'`` fact per dimension) → canon-verify (C12). It
    refuses (raises :class:`FabricationError`) when there is no grounding to anchor
    to (free invention is an H0 violation). NEVER writes canon (no C13 here).
    """

    technique = Technique.FABRICATION

    #: Injected KG-neighbourhood lookup: (entity_name, context) → related canon
    #: facts. Optional — defaults to "no neighbourhood" (Q6 degrade). The real impl
    #: reads through the C1 KnowledgeReadPort; tests pass a stub. Read-only (Q2).
    NeighborLookupFn = Callable[
        [str, StrategyContext], Awaitable[Sequence["NeighborFact"]]
    ]

    def __init__(
        self,
        *,
        retrieval: RetrievalStrategy,
        complete: CompleteFn,
        verifier: CanonVerifier,
        neighbor_lookup: "FabricationStrategy.NeighborLookupFn | None" = None,
        confidence: float = FABRICATION_CONFIDENCE,
    ) -> None:
        self._retrieval = retrieval
        self._complete = complete
        self._verifier = verifier
        self._neighbor_lookup = neighbor_lookup
        self._confidence = confidence

    def estimate_cost(self, gap_batch: list[Gap]) -> CostEstimate:
        """Project the per-gap fabrication cost (HIGHER than P1 — embed + KG
        neighbourhood + richer LLM completion). Pure + side-effect-free: the
        higher figure lets the C8 cost-cap pause/escalate a runaway P2 batch
        sooner (cost-discipline, Q-R2)."""
        n = len(gap_batch)
        return CostEstimate(
            technique=self.technique,
            gap_count=n,
            units=float(n),
            cost=FABRICATION_GAP_COST * n,
        )

    async def run(
        self,
        gap_batch: list[Gap],
        context: StrategyContext,
        *,
        jwt: str = "",
    ) -> list[FabricatedProposal]:
        """Fabricate canon-grounded content for each gap.

        One :class:`FabricatedProposal` per gap, in input order. Each carries the
        H0-tagged fabricated facts + the C12 verify annotation. A gap with no
        grounding is REFUSED (raises :class:`FabricationError`) — fabrication must
        anchor to canon, never invent from nothing.
        """
        results: list[FabricatedProposal] = []
        proposals = await self._retrieval.run(gap_batch, context)
        for proposal in proposals:
            results.append(await self._fabricate(proposal, context, jwt=jwt))
        return results

    # ── internals ─────────────────────────────────────────────────────────────
    async def _fabricate(
        self,
        proposal: GroundedProposal,
        context: StrategyContext,
        *,
        jwt: str,
    ) -> FabricatedProposal:
        expected_keys = list(proposal.dimensions.keys())
        if not expected_keys:
            raise FabricationError(
                f"proposal for {proposal.canonical_name!r} has no missing "
                "dimensions to fabricate"
            )
        if not proposal.grounding:
            # No corpus anchor → fabrication would be free invention (H0 violation).
            raise FabricationError(
                f"proposal for {proposal.canonical_name!r} has no grounding — "
                "refusing to fabricate ungrounded content (H0)"
            )

        neighbors = await self._read_neighbors(proposal.canonical_name, context)
        source_refs = _source_refs_from_grounding(proposal.grounding)
        prompt = build_fabrication_prompt(proposal, neighbors)
        raw = await self._complete(prompt, context)

        try:
            repaired, _report = repair_generation(raw, expected_keys=expected_keys)
        except RepairError as exc:
            raise FabricationError(
                f"fabrication for {proposal.canonical_name!r} unrepairable: {exc}"
            ) from exc

        facts = self._tag_facts(
            proposal, repaired, expected_keys, source_refs, neighbors, context
        )

        # C12 canon-verify BEFORE the proposal is considered done — an
        # anachronistic / contradictory / injected fabrication is flagged.
        verify = await verify_and_annotate(
            self._verifier, proposal, facts, jwt=jwt
        )
        return FabricatedProposal(
            proposal=proposal,
            facts=facts,
            verify=verify,
            neighbors=list(neighbors),
        )

    def _tag_facts(
        self,
        proposal: GroundedProposal,
        repaired: dict[str, str],
        expected_keys: list[str],
        source_refs: list[SourceRef],
        neighbors: Sequence[NeighborFact],
        context: StrategyContext,
    ) -> list[EnrichedFact]:
        """Mint one H0-tagged fact per fabricated dimension via the C11 chokepoint.

        origin='enriched:fabrication', confidence<1.0, pending_validation, non-empty
        provenance that EXPLICITLY records ``fabricated=True`` + the grounding basis
        (corpus refs + KG neighbours) so a reviewer sees this content was fabricated
        and on what it was anchored. The chokepoint makes a canon-looking fact
        impossible to construct."""
        neighbor_basis = [
            {"subject": n.subject, "relation": n.relation, "object": n.object}
            for n in neighbors
        ]
        facts: list[EnrichedFact] = []
        for dimension in expected_keys:  # C6 declaration order, deterministic
            facts.append(
                make_enriched_fact(
                    user_id=proposal.user_id,
                    project_id=proposal.project_id,
                    entity_kind=proposal.entity_kind,
                    canonical_name=proposal.canonical_name,
                    target_ref=proposal.target_ref,
                    dimension=dimension,
                    content=repaired[dimension],
                    technique=Technique.FABRICATION.value,
                    source_refs=source_refs,
                    model_ref=context.model_ref,
                    confidence=self._confidence,
                    qualified_origin=True,  # → origin='enriched:fabrication'
                    extra_provenance={
                        "fabricated": True,
                        "grounding_basis": {
                            "corpus_grounding_count": len(proposal.grounding),
                            "kg_neighbors": neighbor_basis,
                        },
                    },
                )
            )
        return facts

    async def _read_neighbors(
        self, entity_name: str, context: StrategyContext
    ) -> list[NeighborFact]:
        """Read the KG neighbourhood for the entity (Q6 degrade to empty).

        Never raises into fabrication: a lookup error / down KG → no neighbourhood
        (fabrication anchors on the corpus grounding alone). The lookup is
        read-only (Q2)."""
        if self._neighbor_lookup is None:
            return []
        try:
            return list(await self._neighbor_lookup(entity_name, context))
        except Exception:  # noqa: BLE001 — Q6 graceful degrade, never crash
            return []
