"""Strategy (d) — RE-COOK (RAID C17, Q-R2 P3 technique #4 — the LAST tier).

The fourth and final concrete :class:`~app.strategies.base.EnrichmentStrategy`
and the only P3 technique. Where fabrication (C16) extrapolates plausible detail
within the corpus + KG + era frame, **re-cook** takes REAL, attributable
reference material — history / news / encyclopedic text from LICENSED or
public-domain sources — and RE-CONTEXTUALISES (re-cooks / adapts) it into the
商周 / 封神演义 fictional setting. The real-world event/place/custom becomes a
source-faithful piece of 封神 lore; the originating source is always cited.

Two safety surfaces stack on top of the C8 gate machinery (per the C17 brief):

  1. **Gate enforcement (DEFERRED-054, reused from C16, NOT regressed):** re-cook
     is tier P3, so it registers under ``recook`` but is ONLY selectable through
     the :class:`~app.strategies.factory.GateAwareStrategyFactory`, which reads
     the LIVE C15 eval gate and forces every non-P1 technique OFF when the gate is
     LOCKED. The factory's ``gated_feature_flags`` already covers P3 (it forces
     ``t.tier is not Tier.P1`` off), and on a passed gate the factory
     default-enables ANY non-P1 strategy it holds — so re-cook plugs into the
     EXACT same enforcement as fabrication with no factory change. A locked gate
     (or a stale eval) makes ``recook`` unselectable from the runner.

  2. **LICENSING check (the C17-specific safety):** re-cook ingests EXTERNAL real
     material, so before it consumes a source it verifies — via
     :mod:`app.strategies.licensing` (default-deny) — that the source's license is
     ``public_domain`` or ``licensed``. An ``unlicensed`` / ``copyrighted`` /
     ``unknown`` / missing license → :class:`~app.strategies.licensing.UnlicensedSourceError`
     (refused + escalated). The check runs at BOTH corpus-admission (every
     grounding source) AND fact-emit (defence in depth).

H0 (NON-NEGOTIABLE — re-cook ingests third-party material, so a tagging miss
would admit external content as canon, the single worst failure): every re-cooked
fact is the same H0-tagged :class:`~app.generation.provenance.EnrichedFact` the
C11 chokepoint mints — ``origin='enriched:recook'``, ``confidence<1.0``,
quarantined (``pending_validation=True``), provenance recording ``recooked=True``
+ the licensed source it was re-cooked from + the grounding basis. There is NO
write-back here (reuse C13 unchanged); only the author's promote can canonize it.

Boundaries (locked — docs/raid/cycle_briefs/17_strategy-recook.md):
  * REUSES C10 retrieval (grounding from the licensed source), the C11
    ``make_enriched_fact`` H0 chokepoint + ``repair_generation``, and the C12
    ``CanonVerifier`` — all UNCHANGED. NO new write-back / proposal store / KG
    writer (C13 owns canon).
  * NO web search / live news fetch (locked — owned/licensed corpora only). The
    re-cook corpus is a curated, license-tagged input set.
  * NO model-name string — the model is resolved via provider-registry by
    ``context.model_ref`` (the injected ``CompleteFn`` seam, like C11/C16).
  * Output language = Chinese (源文一致, 封神演义 tone). The C12 anachronism check
    runs on the re-cooked content — re-contextualising MODERN material into 商周
    is precisely where an anachronism would surface, and it is FLAGGED.
"""

from __future__ import annotations

import logging
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
from app.strategies.licensing import (
    LicenseStatus,
    SourceLicense,
    UnlicensedSourceError,
    check_admissible,
)
from app.verify.canon_verify import CanonVerifier
from app.verify.sanitize import neutralize_proposal_text
from app.verify.wiring import AnnotatedVerify, verify_and_annotate

logger = logging.getLogger("lore_enrichment.recook")

__all__ = [
    "CompleteFn",
    "LicenseLookupFn",
    "ReCookError",
    "ReCookedProposal",
    "ReCookStrategy",
    "build_recook_prompt",
    "RECOOK_CONFIDENCE",
    "RECOOK_GAP_COST",
]


#: The injected LLM-completion seam: (prompt, context) → raw model text. Bound to
#: the provider-registry generation endpoint by ``model_ref`` on the context
#: (NEVER a model name) — IDENTICAL to the C11/C16 seam. Tests inject a stub; the
#: real binding is ``app.generation.complete.make_complete_fn``.
CompleteFn = Callable[[str, StrategyContext], Awaitable[str]]

#: The injected license-resolver seam: corpus_id → its :class:`SourceLicense`
#: (read from ``source_corpus.license``). Async so a real impl can hit the DB; a
#: ``None`` result means the corpus is unknown to the store → treated as an
#: ``UNKNOWN`` (refused) license (default-deny). The strategy NEVER trusts a
#: source whose license it could not resolve.
LicenseLookupFn = Callable[[str], Awaitable["SourceLicense | None"]]


# ── H0 + cost constants ───────────────────────────────────────────────────────
#: A re-cooked fact's confidence. Content now EXISTS (re-contextualised from a
#: real source), so it sits at the C11 generation level — but, like fabrication,
#: it is NEVER raised toward canon: re-cook is high makeup-risk (third-party
#: material adapted into fiction) and is gated hardest by the human review. H0:
#: strictly ``0 < c < 1.0``.
RECOOK_CONFIDENCE: float = GENERATION_CONFIDENCE

#: Per-gap TOKEN pre-charge (C1 / DEFERRED-052: denominated in real tokens, like
#: P1/P2). Re-cook is P3 — the LAST, highest-cost/highest-risk tier: retrieval + a
#: licensing resolution per source + the richest, re-generating LLM
#: re-contextualisation prompt. Declared HIGHER than P2 fabrication (3000) so the
#: C8 cost-cap pauses/escalates a runaway re-cook batch SOONEST (cost discipline,
#: Q-R2 — P3 is last and most expensive). Conservative PRE-charge; P3's post-call
#: meter-reconcile is deferred until the eval gate activates re-cook (DEFERRED-059).
RECOOK_GAP_COST: float = 4500.0


class ReCookError(RuntimeError):
    """Raised when re-cook cannot produce a schema-valid set of facts.

    Mirrors C11 ``GenerationError`` / C16 ``FabricationError`` semantics: an
    empty-grounding re-cook (nothing real to re-contextualise) or unrepairable
    model output is REJECTED, never emitted as a partial / untagged fact. NOTE: a
    LICENSING refusal is a DISTINCT :class:`UnlicensedSourceError` (not a
    ``ReCookError``) so a caller can tell "bad output" from "unlicensed source".
    """


class ReCookedProposal(BaseModel):
    """A re-cooked result for one gap (the C17 output unit).

    Carries the C10 grounded proposal it re-cooked from, the H0-tagged re-cooked
    facts (one per dimension), the C12 verify annotation, and the
    :class:`SourceLicense`\\ s of every source admitted into the re-cook (all of
    them necessarily admissible — an inadmissible one raises before this is
    built). The runner persists these as ONE quarantined ``enrichment_proposal``
    row (reusing C13 write-back) — this class adds no persistence, no canon path.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    proposal: GroundedProposal
    facts: list[EnrichedFact]
    verify: AnnotatedVerify
    licenses: list[SourceLicense] = Field(default_factory=list)


def _grounding_block(grounding: Sequence[GroundingRef]) -> str:
    """Format the C10 retrieved excerpts (the REAL source material) as the
    re-cook's source-faithful anchor block (Chinese, cited). Same shape as the
    C11/C16 prompt block so the model sees the same evidence framing.

    INJECTION DEFENSE-IN-DEPTH (RAID c17 WARN-2): the re-cook source is the MOST
    untrusted input — a poisoned corpus excerpt could steer the GENERATING LLM
    (C12 ``verify_and_annotate`` only neutralizes the OUTPUT, protecting C13/C15,
    not the model that composes this prompt). So every excerpt is neutralized via
    the C1/C12 :func:`neutralize_proposal_text` (tag-not-delete: it prepends a
    ``[FICTIONAL]`` marker to any injection span so the model reads it as quoted
    in-story text, never an instruction) BEFORE it enters the prompt. CJK lore is
    preserved verbatim — the neutralizer only tags matched directive spans."""
    return "\n".join(
        f"［{i + 1}］（来源 {g.corpus_id}#{g.chunk_index}，相似度 {g.score}）"
        f"{neutralize_proposal_text(g.excerpt)[0]}"
        for i, g in enumerate(grounding)
    )


def build_recook_prompt(proposal: GroundedProposal) -> str:
    """Build the RE-COOK prompt (Chinese, source-faithful).

    Distinct from the C11 retrieval-generation prompt (fill only what the excerpts
    directly support) and the C16 fabrication prompt (extrapolate within canon):
    this one instructs the model to take the REAL reference material below
    (history / news / encyclopedic text from a LICENSED source) and
    RE-CONTEXTUALISE / ADAPT it into the 商周 · 封神演义 fictional setting — the
    real event/place/custom becomes source-faithful 封神 lore. It BOUNDS the
    re-cook hard: (1) re-cast into the 商周/封神 era, never carry over later
    dynasties / modern tech / foreign faiths (the C12 anachronism frame); (2)
    stay consistent with the 封神演义 worldview; (3) Chinese, original tone; (4)
    JSON only. NO model name, NO provider-specific tokens.
    """
    dims = list(proposal.dimensions.keys())
    keys_csv = "、".join(dims)
    json_skeleton = ", ".join(f'"{d}": "……"' for d in dims)
    return (
        f"你是一位深谙《封神演义》世界观的世界构建师。\n"
        f"下面给出关于「{proposal.canonical_name}」的一批真实参考材料"
        f"（取自经授权或公有领域的历史·地理·文化文献）。\n"
        f"请将这些真实材料『再创作·再语境化』，融入商周·封神演义的虚构世界，"
        f"为「{proposal.canonical_name}」补全以下维度：{keys_csv}。\n"
        f"这是『据实再创作』而非凭空臆造，须遵守：\n"
        f"1. 须以下列真实材料为蓝本进行改写、移植，使其成为契合封神演义的设定；\n"
        f"2. 必须重置于商周·封神纪元的时代背景，"
        f"严禁保留原材料中的后世朝代、近现代器物、外来宗教等时代错置内容；\n"
        f"3. 须与《封神演义》既有世界观保持一致，不得自相矛盾；\n"
        f"4. 内容必须为中文，文言-白话皆可，须与原著语气一致；\n"
        f"5. 仅输出一个 JSON 对象，键为上述维度名，值为对应中文描述，"
        f"不要输出任何额外说明。\n\n"
        f"真实参考材料（授权/公有领域来源，待再语境化）：\n"
        f"{_grounding_block(proposal.grounding)}\n\n"
        f"请输出 JSON：{{{json_skeleton}}}"
    )


def _source_refs_from_grounding(grounding: list[GroundingRef]) -> list[SourceRef]:
    """Project the C10 grounding refs onto the H0 ``source_refs`` shape — the
    licensed source BASIS every re-cooked fact must cite (empty basis = nothing
    real to re-cook = rejected)."""
    return [
        SourceRef(
            corpus_id=g.corpus_id,
            chunk_id=g.chunk_id,
            chunk_index=g.chunk_index,
            score=g.score,
        )
        for g in grounding
    ]


class ReCookStrategy(EnrichmentStrategy):
    """Technique (d): re-cook real material into 商周/封神 lore (tier P3,
    gate-enforced + licensing-gated).

    Registers under the ``recook`` key but is ONLY selectable through the
    :class:`~app.strategies.factory.GateAwareStrategyFactory` (DEFERRED-054 — the
    live C15 gate must be CLEARED, exactly like fabrication). Construct with the
    C10 retrieval strategy (to obtain the grounded proposal from the licensed
    source), the injected C11-style ``CompleteFn`` (provider-registry by
    ``model_ref``), the C12 canon-verifier, and a :data:`LicenseLookupFn` that
    resolves each source corpus's license.

    :meth:`run` per gap:
      1. retrieve grounding (C10) from the source corpus(es);
      2. **licensing check at CORPUS-ADMISSION** — resolve + verify each grounding
         source's license is admissible (public_domain / licensed); an
         inadmissible source RAISES :class:`UnlicensedSourceError` (re-cook of that
         source is refused, never silently included);
      3. re-contextualise the licensed real material into the 商周/封神 era (LLM);
      4. repair (C11 ``repair_generation``);
      5. **licensing check at FACT-EMIT** (defence in depth) — re-verify the
         source licenses before minting any fact;
      6. H0-tag via the C11 chokepoint (one ``origin='enriched:recook'`` fact per
         dimension, citing the licensed source + ``recooked=True``);
      7. canon-verify (C12 — the anachronism check is load-bearing here: re-cooked
         MODERN content into 商周 surfaces as an anachronism flag).

    It refuses (raises :class:`ReCookError`) when there is no grounding to re-cook
    from. NEVER writes canon (no C13 here).
    """

    technique = Technique.RECOOK

    def __init__(
        self,
        *,
        retrieval: RetrievalStrategy,
        complete: CompleteFn,
        verifier: CanonVerifier,
        license_lookup: LicenseLookupFn,
        confidence: float = RECOOK_CONFIDENCE,
    ) -> None:
        self._retrieval = retrieval
        self._complete = complete
        self._verifier = verifier
        self._license_lookup = license_lookup
        self._confidence = confidence

    def estimate_cost(self, gap_batch: list[Gap]) -> CostEstimate:
        """Project the per-gap re-cook cost (HIGHEST tier — retrieval + licensing
        resolution + the richest re-contextualisation completion). Pure +
        side-effect-free: the highest figure lets the C8 cost-cap pause/escalate a
        runaway P3 batch soonest (cost-discipline, Q-R2 — P3 is last + dearest)."""
        n = len(gap_batch)
        return CostEstimate(
            technique=self.technique,
            gap_count=n,
            units=float(n),
            cost=RECOOK_GAP_COST * n,
        )

    async def run(
        self,
        gap_batch: list[Gap],
        context: StrategyContext,
        *,
        jwt: str = "",
    ) -> list[ReCookedProposal]:
        """Re-cook licensed real material into 商周/封神 lore for each gap.

        One :class:`ReCookedProposal` per gap, in input order. A gap with no
        grounding is REFUSED (:class:`ReCookError`). FIX-2: a gap whose grounding
        mixes licensed and unlicensed sources re-cooks from the LICENSED ones and
        SKIPS the unlicensed (never consuming them); a gap with NO admissible source
        is REFUSED (:class:`UnlicensedSourceError`) — re-cook consumes only
        public-domain / licensed material.
        """
        results: list[ReCookedProposal] = []
        proposals = await self._retrieval.run(gap_batch, context)
        for proposal in proposals:
            results.append(await self._recook(proposal, context, jwt=jwt))
        return results

    # ── internals ─────────────────────────────────────────────────────────────
    async def _recook(
        self,
        proposal: GroundedProposal,
        context: StrategyContext,
        *,
        jwt: str,
    ) -> ReCookedProposal:
        expected_keys = list(proposal.dimensions.keys())
        if not expected_keys:
            raise ReCookError(
                f"proposal for {proposal.canonical_name!r} has no missing "
                "dimensions to re-cook"
            )
        if not proposal.grounding:
            # No real source to re-contextualise → nothing to re-cook (H0: never
            # invent from nothing — that is fabrication's job, not re-cook's).
            raise ReCookError(
                f"proposal for {proposal.canonical_name!r} has no grounding — "
                "refusing to re-cook with no real source material (H0)"
            )

        # ── (1) LICENSING CHECK at CORPUS-ADMISSION — every grounding source ─────
        # Resolve every distinct source's license BEFORE any generation. FIX-2:
        # SKIP inadmissible sources (drop their grounding so they are NEVER fed to
        # the model) and re-cook from the admissible ones; refuse the WHOLE proposal
        # ONLY if no source is licensed. This keeps the per-source refusal (an
        # unlicensed source is never consumed) without letting one copyrighted
        # corpus poison a re-cook that has licensed grounding to work from.
        admissible, skipped = await self._admit_sources(proposal)
        admissible_ids = {lic.corpus_id for lic in admissible}
        kept = [g for g in proposal.grounding if g.corpus_id in admissible_ids]
        if not kept:
            names = ", ".join(
                f"{s.name!r}({s.status.value})" for s in skipped
            ) or "—"
            raise UnlicensedSourceError(
                f"re-cook refused [corpus-admission]: proposal for "
                f"{proposal.canonical_name!r} has NO admissible (public_domain / "
                f"licensed) grounding — all {len(skipped)} source(s) inadmissible: "
                f"{names}. Nothing licensed to re-cook from."
            )
        if skipped:
            logger.info(
                "re-cook %s: skipped %d unlicensed source(s) (%s), re-cooking from "
                "%d admissible",
                proposal.canonical_name, len(skipped),
                [s.corpus_id for s in skipped], len(admissible),
            )
        # Re-cook ONLY the admissible grounding from here on (filtered copy).
        proposal = proposal.model_copy(update={"grounding": kept})
        licenses = admissible

        source_refs = _source_refs_from_grounding(proposal.grounding)
        prompt = build_recook_prompt(proposal)
        raw = await self._complete(prompt, context)

        try:
            repaired, _report = repair_generation(raw, expected_keys=expected_keys)
        except RepairError as exc:
            raise ReCookError(
                f"re-cook for {proposal.canonical_name!r} unrepairable: {exc}"
            ) from exc

        # ── (5) LICENSING CHECK at FACT-EMIT (defence in depth) ──────────────────
        # Re-verify before minting any fact. By construction the same sources were
        # already admitted above, but re-checking at emit means an unlicensed
        # source can NEVER reach an emitted fact even if admission were bypassed.
        for lic in licenses:
            check_admissible(lic, stage="fact-emit")

        facts = self._tag_facts(
            proposal, repaired, expected_keys, source_refs, licenses, context,
            skipped=skipped,
        )

        # C12 canon-verify BEFORE the proposal is done — re-contextualising MODERN
        # material into 商周 is exactly where an anachronism surfaces; it is FLAGGED
        # (annotation only, never auto-admitted).
        verify = await verify_and_annotate(
            self._verifier, proposal, facts, jwt=jwt
        )
        return ReCookedProposal(
            proposal=proposal,
            facts=facts,
            verify=verify,
            licenses=list(licenses),
        )

    async def _admit_sources(
        self, proposal: GroundedProposal
    ) -> tuple[list[SourceLicense], list[SourceLicense]]:
        """Resolve the license of every distinct grounding source and PARTITION it.

        Returns ``(admissible, skipped)`` in first-seen order. FIX-2: an
        inadmissible source is SKIPPED (its grounding is dropped before any
        generation — never consumed), NOT a whole-job refusal. A single copyrighted
        corpus in a multi-corpus project must not poison a re-cook that can still
        ground on the project's licensed sources. The per-source refusal is
        preserved (an unlicensed source is never re-cooked) and the skipped set is
        recorded in provenance + logged, so the licensing decision stays auditable —
        never silently hidden. The all-inadmissible case is handled by the caller
        (raises — nothing licensed to re-cook from). A source the lookup cannot
        resolve is UNKNOWN → skipped (default-deny: never re-cook what you can't
        license)."""
        seen: set[str] = set()
        admissible: list[SourceLicense] = []
        skipped: list[SourceLicense] = []
        for ref in proposal.grounding:
            if ref.corpus_id in seen:
                continue
            seen.add(ref.corpus_id)
            resolved = await self._license_lookup(ref.corpus_id)
            lic = resolved if resolved is not None else SourceLicense(
                corpus_id=ref.corpus_id,
                name=ref.corpus_id,
                status=LicenseStatus.UNKNOWN,
            )
            (admissible if lic.admissible else skipped).append(lic)
        return admissible, skipped

    def _tag_facts(
        self,
        proposal: GroundedProposal,
        repaired: dict[str, str],
        expected_keys: list[str],
        source_refs: list[SourceRef],
        licenses: Sequence[SourceLicense],
        context: StrategyContext,
        *,
        skipped: Sequence[SourceLicense] = (),
    ) -> list[EnrichedFact]:
        """Mint one H0-tagged fact per re-cooked dimension via the C11 chokepoint.

        origin='enriched:recook', confidence<1.0, pending_validation, non-empty
        provenance that EXPLICITLY records ``recooked=True`` + the LICENSED source
        basis (corpus refs + their license statuses) so a reviewer sees this
        content was re-cooked from a specific licensed source — PLUS any
        ``skipped_unlicensed_sources`` (FIX-2) so the licensing decision is
        auditable, never hidden. The chokepoint makes a canon-looking fact
        impossible to construct."""
        source_basis = [
            {"corpus_id": lic.corpus_id, "name": lic.name, "license": lic.status.value}
            for lic in licenses
        ]
        skipped_basis = [
            {"corpus_id": s.corpus_id, "name": s.name, "license": s.status.value}
            for s in skipped
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
                    technique=Technique.RECOOK.value,
                    source_refs=source_refs,
                    model_ref=context.model_ref,
                    confidence=self._confidence,
                    qualified_origin=True,  # → origin='enriched:recook'
                    extra_provenance={
                        "recooked": True,
                        "recook_basis": {
                            "corpus_grounding_count": len(proposal.grounding),
                            "licensed_sources": source_basis,
                            "skipped_unlicensed_sources": skipped_basis,
                        },
                    },
                )
            )
        return facts
