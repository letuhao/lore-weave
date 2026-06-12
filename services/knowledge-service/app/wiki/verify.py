"""Wiki canon-verify — wrap a generated article with the grounding-SDK gate (M4).

Adapts a :class:`WikiArticleIR` to the SDK `CanonVerifier`'s duck-typed inputs and
runs its four checks (injection · anachronism · regurgitation · contradiction),
then classifies the result for publishing via a ported `decide_auto_reject`.

Risk #11 — the SDK verifier was built for enrichment's dimension-keyed facts; a
wiki article is free prose. 3/4 checks run on raw text directly. For contradiction
we use **section-level facts** (PO Q1-A): each `## section` (and the lead) becomes
one fact whose ``dimension`` is the section title and ``content`` is its prose, all
checked against the entity's authored canon (the `short_description`, via
`make_canon_lookup`). ANNOTATES only — never writes canon, never publishes; M5
persists the flags + ``publish_blocked``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from loreweave_grounding.verify import (
    CanonVerifier,
    FlagKind,
    Severity,
    VerifyResult,
)
from pydantic import BaseModel, Field

from app.clients.book_profile_client import BookProfile
from app.wiki.canon import make_canon_lookup
from app.wiki.context import GenerationContext
from app.wiki.ir import WikiArticleIR

__all__ = [
    "WikiVerifyResult",
    "decide_auto_reject",
    "verify_article",
    "AUTO_REJECT_ANACHRONISM_MIN_MARKERS",
]

#: >= this many DISTINCT anachronism markers = egregiously anachronistic
#: (auto-reject). One marker stays advisory; two distinct out-of-era concepts in
#: one article is a strong egregious signal. (Ported from LE wiring.py.)
AUTO_REJECT_ANACHRONISM_MIN_MARKERS = 2


# ── duck-typed adapters for the SDK Protocols (ProposalLike / FactLike) ─────────

@dataclass(frozen=True)
class _Grounding:
    corpus_id: str
    chunk_index: int
    excerpt: str


@dataclass(frozen=True)
class _Proposal:
    canonical_name: str
    grounding: Sequence[_Grounding]


@dataclass(frozen=True)
class _Fact:
    dimension: str
    content: str


def _block_text(block) -> str:
    return " ".join(s.text for s in block.all_spans() if s.text).strip()


def ir_to_facts(ir: WikiArticleIR) -> list[_Fact]:
    """Section-level facts (Q1-A): the lead + each ``## section`` → one fact whose
    ``dimension`` is the section title (heading text included in the content so an
    anachronism/contradiction IN a heading is also checked)."""
    facts: list[_Fact] = []
    current_dim = "lead"
    parts: list[str] = []

    def flush() -> None:
        content = " ".join(p for p in parts if p).strip()
        if content:
            facts.append(_Fact(dimension=current_dim, content=content))

    for b in ir.blocks:
        if b.type == "heading":
            flush()
            htext = _block_text(b) or "section"
            current_dim = htext
            parts = [htext]
        else:
            parts.append(_block_text(b))
    flush()
    return facts


def ir_to_proposal(ir: WikiArticleIR, context: GenerationContext) -> _Proposal:
    """The proposal the verifier checks: the entity name + the retrieved passage
    excerpts (the source material the regurgitation check looks for verbatim
    copying against)."""
    grounding = [
        _Grounding(
            corpus_id=it.source.chapter_id or it.source.cite_id,
            chunk_index=it.source.block_index or 0,
            excerpt=it.text,
        )
        for it in context.items
        if it.source.kind == "passage"
    ]
    return _Proposal(canonical_name=ir.display_name, grounding=grounding)


def decide_auto_reject(result: VerifyResult) -> str | None:
    """Classify a verify result as EGREGIOUS (auto-reject → publish-blocked) or
    advisory. Conservative (false-positive-averse). Egregious iff: ANY injection
    flag · a HIGH contradiction · >= AUTO_REJECT_ANACHRONISM_MIN_MARKERS distinct
    anachronism markers · a HIGH regurgitation flag. Returns a reason string when
    egregious, else None. (Ported verbatim from LE `wiring.decide_auto_reject`.)"""
    reasons: list[str] = []

    injection = [f for f in result.flags if f.kind is FlagKind.INJECTION]
    if injection:
        reasons.append(f"injection ({injection[0].evidence})")

    high_contradiction = [
        f for f in result.flags
        if f.kind is FlagKind.CONTRADICTION and f.severity is Severity.HIGH
    ]
    if high_contradiction:
        reasons.append(f"high-severity contradiction ({high_contradiction[0].evidence})")

    distinct_anachronisms = {
        f.evidence for f in result.flags if f.kind is FlagKind.ANACHRONISM
    }
    if len(distinct_anachronisms) >= AUTO_REJECT_ANACHRONISM_MIN_MARKERS:
        reasons.append(f"{len(distinct_anachronisms)} distinct anachronism markers")

    high_regurgitation = [
        f for f in result.flags
        if f.kind is FlagKind.REGURGITATION and f.severity is Severity.HIGH
    ]
    if high_regurgitation:
        reasons.append(f"verbatim source regurgitation ({high_regurgitation[0].evidence})")

    if not reasons:
        return None
    return "auto-reject: " + "; ".join(reasons)


class WikiVerifyResult(BaseModel):
    """The article-level verify outcome (annotation only). ``flags`` are the
    serialized SDK flags (persisted into ``generation_provenance.verify_flags`` by
    M5); ``publish_blocked`` is the auto-reject verdict the writeback honours."""

    passed: bool
    publish_blocked: bool
    reject_reason: str | None = None
    degraded: bool = False
    flags: list[dict[str, str]] = Field(default_factory=list)

    @property
    def flag_count(self) -> int:
        return len(self.flags)

    @property
    def has_high(self) -> bool:
        return any(f.get("severity") == Severity.HIGH.value for f in self.flags)


async def verify_article(
    ir: WikiArticleIR,
    context: GenerationContext,
    profile: BookProfile,
) -> WikiVerifyResult:
    """Run the SDK CanonVerifier over a generated article + classify it.

    Anachronism markers come from the book profile (empty → the anachronism check
    is off — a modern/sci-fi book is never flagged for 'modern tech'). Contradiction
    is checked against the entity's authored canon (the brief ``short_description``).
    Never raises — a canon read can't fail here (it's in-memory)."""
    verifier = CanonVerifier(
        canon_lookup=make_canon_lookup(context.brief),
        anachronism_markers=profile.anachronism_markers,
    )
    proposal = ir_to_proposal(ir, context)
    facts = ir_to_facts(ir)
    result = await verifier.verify(proposal, facts)
    reject_reason = decide_auto_reject(result)
    return WikiVerifyResult(
        passed=result.passed,
        publish_blocked=reject_reason is not None,
        reject_reason=reject_reason,
        degraded=result.verify_degraded,
        flags=[
            {
                "kind": f.kind.value,
                "dimension": f.dimension,
                "evidence": f.evidence,
                "severity": f.severity.value,
            }
            for f in result.flags
        ],
    )
