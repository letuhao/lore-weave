"""Schema-governed GENERATION (RAID C11) — fill the C9 scaffold's empty Chinese
dimensions with content GENERATED from the C10 retrieved cultural grounding.

This is the cycle where empty dimension slots become real (Chinese, source-
faithful) lore. The pipeline per proposal is:

  1. build a schema-governed PROMPT (Chinese, cites the C10 grounding passages,
     names exactly the missing dimensions the model must fill),
  2. call the LLM through an INJECTED ``CompleteFn`` seam — the generating model
     is resolved via provider-registry by ``model_ref`` on the
     :class:`StrategyContext`; NO model NAME appears in code (the locked engine,
     a strong Classical-Chinese model served over LM Studio, is referenced only
     by its registry ref). Tests inject a deterministic stub; the real binding
     (provider-registry ``/internal/llm``) is wired at orchestration time (C14),
     exactly as C10 deferred its embed registry-wiring,
  3. REPAIR the raw output to the schema (``repair.repair_generation``) —
     malformed → repaired-or-typed-reject, never silently dropped,
  4. for EACH repaired dimension, mint an :class:`EnrichedFact` through the H0
     chokepoint (``provenance.make_enriched_fact``) — every fact is born
     ``origin='enriched:<technique>'`` + provenance + ``confidence<1.0`` +
     ``pending_validation=True`` + non-empty ``source_refs``.

H0 / scope boundary: the ONLY way a fact leaves this module is via the
provenance chokepoint, so an untagged fact cannot be produced. This cycle STOPS
at tagged in-memory records — NO write-back to glossary/Neo4j/KG (C13), NO
contradiction/anachronism check (C12), NO orchestration (C14).
"""

from __future__ import annotations

from typing import Awaitable, Callable

from app.generation.provenance import (
    GENERATION_CONFIDENCE,
    EnrichedFact,
    SourceRef,
    make_enriched_fact,
)
from app.generation.repair import RepairError, repair_generation
from app.retrieval.strategy import GroundedProposal, GroundingRef
from app.strategies.base import StrategyContext, Technique

__all__ = [
    "CompleteFn",
    "GenerationError",
    "SchemaGovernedGenerator",
    "build_generation_prompt",
]


#: The injected LLM-completion seam: (prompt, context) → raw model text. Bound to
#: the provider-registry generation endpoint by ``model_ref`` on the context
#: (NEVER a model name). The generator never imports an HTTP/LLM client; tests
#: pass a deterministic stub. Real binding lands in C14 (like C10's embed seam).
CompleteFn = Callable[[str, StrategyContext], Awaitable[str]]


class GenerationError(RuntimeError):
    """Raised when generation cannot produce a schema-valid set of facts.

    Wraps the un-repairable :class:`RepairError` (and empty-grounding rejects) so
    a caller distinguishes "the model produced unusable output" from a transport
    error. A generation that cannot be repaired is REJECTED — never emitted as a
    partial / untagged fact.
    """


def build_generation_prompt(proposal: GroundedProposal) -> str:
    """Build the schema-governed, Chinese, grounding-citing generation prompt.

    Deterministic (no randomness): names the place, lists EXACTLY the missing
    dimension labels the model must fill (the JSON keys), embeds the C10 grounding
    excerpts as the ONLY evidence the model may draw on (source-faithful, no
    fabrication), and instructs Chinese-only output as a JSON object. The prompt
    contains NO model name and NO provider-specific tokens.
    """
    dims = list(proposal.dimensions.keys())
    grounding_block = "\n".join(
        f"［{i + 1}］（来源 {g.corpus_id}#{g.chunk_index}，相似度 {g.score}）{g.excerpt}"
        for i, g in enumerate(proposal.grounding)
    )
    keys_csv = "、".join(dims)
    json_skeleton = ", ".join(f'"{d}": "……"' for d in dims)
    return (
        f"你是一位忠于《封神演义》原著的世界观补全助手。\n"
        f"请仅依据下列原著与文化语料的检索片段，为地点「{proposal.canonical_name}」"
        f"补全以下维度：{keys_csv}。\n"
        f"要求：\n"
        f"1. 内容必须为中文，文言-白话皆可，须与原著语气一致；\n"
        f"2. 严禁编造检索片段未支持的事实；\n"
        f"3. 仅输出一个 JSON 对象，键为上述维度名，值为对应中文描述，"
        f"不要输出任何额外说明。\n\n"
        f"检索到的文化依据：\n{grounding_block}\n\n"
        f"请输出 JSON：{{{json_skeleton}}}"
    )


def _source_refs_from_grounding(grounding: list[GroundingRef]) -> list[SourceRef]:
    """Project the C10 grounding refs onto the H0 ``source_refs`` shape.

    The grounding the retrieval cycle attached IS the provenance of the generated
    content — each generated fact must cite at least one of these. An empty
    grounding list means the content has no source → generation is rejected
    (an unprovenanced fact is an H0 violation, enforced downstream too).
    """
    return [
        SourceRef(
            corpus_id=g.corpus_id,
            chunk_id=g.chunk_id,
            chunk_index=g.chunk_index,
            score=g.score,
        )
        for g in grounding
    ]


class SchemaGovernedGenerator:
    """Turn a grounded proposal (C10) into a list of H0-tagged enriched facts.

    Construct with the injected :data:`CompleteFn`. :meth:`generate` runs the
    prompt → complete → repair → H0-tag pipeline for one proposal and returns one
    :class:`EnrichedFact` per missing dimension. NEVER emits canon: every fact
    passes through the provenance chokepoint.
    """

    def __init__(
        self,
        *,
        complete: CompleteFn,
        confidence: float = GENERATION_CONFIDENCE,
    ) -> None:
        self._complete = complete
        self._confidence = confidence

    async def generate(
        self,
        proposal: GroundedProposal,
        context: StrategyContext,
    ) -> list[EnrichedFact]:
        """Generate + repair + H0-tag the missing dimensions of one proposal.

        Rejects (raises :class:`GenerationError`) if the proposal has no grounding
        (no source → unprovenanced), if there are no dimensions to fill, or if the
        model output cannot be repaired to cover every missing dimension. Each
        returned fact is born quarantined (H0) — origin ``enriched:<technique>``,
        non-empty provenance + source_refs, ``confidence<1.0``,
        ``pending_validation=True``.
        """
        expected_keys = list(proposal.dimensions.keys())
        if not expected_keys:
            raise GenerationError(
                f"proposal for {proposal.canonical_name!r} has no missing "
                "dimensions to generate"
            )
        if not proposal.grounding:
            raise GenerationError(
                f"proposal for {proposal.canonical_name!r} has no grounding — "
                "refusing to generate unprovenanced content (H0)"
            )

        source_refs = _source_refs_from_grounding(proposal.grounding)
        prompt = build_generation_prompt(proposal)
        raw = await self._complete(prompt, context)

        try:
            repaired, _report = repair_generation(raw, expected_keys=expected_keys)
        except RepairError as exc:
            raise GenerationError(
                f"generation for {proposal.canonical_name!r} unrepairable: {exc}"
            ) from exc

        technique = proposal.technique or Technique.RETRIEVAL.value
        facts: list[EnrichedFact] = []
        for dimension in expected_keys:  # C6 declaration order, deterministic
            content = repaired[dimension]
            facts.append(
                make_enriched_fact(
                    user_id=proposal.user_id,
                    project_id=proposal.project_id,
                    entity_kind=proposal.entity_kind,
                    canonical_name=proposal.canonical_name,
                    target_ref=proposal.target_ref,
                    dimension=dimension,
                    content=content,
                    technique=technique,
                    source_refs=source_refs,
                    model_ref=context.model_ref,
                    confidence=self._confidence,
                    qualified_origin=True,
                    extra_provenance={
                        "source_proposal_technique": proposal.technique,
                        "grounding_count": len(proposal.grounding),
                    },
                )
            )
        return facts
