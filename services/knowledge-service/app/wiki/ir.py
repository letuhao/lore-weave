"""Wiki Article IR — the canonical, render-target-agnostic model (M0 / Phase-1 §C1).

The LLM emits constrained Markdown; ``parse.py`` lifts it into this IR; ``mappers.py``
maps the IR forward to TipTap (the STORED body), Markdown (feedback-gold diffs), or
plaintext (search). The IR is a **generation-stage** model — never stored as-is (TipTap
``body_json`` is the stored form), so only the forward maps exist, no IR-round-trip.

Citations are the **anti-hallucination layer**: every non-trivial :class:`Span` should
carry a cite resolving to a :class:`Source` (a passage / glossary / kg fact WE handed the
LLM). The cite LABELS are OURS — we assign ``P1``.. and pass them in — so a label the LLM
echoes that is NOT in ``sources`` is a hallucinated reference, dropped at parse; a
non-trivial span left with zero resolved cites is marked ``grounded=False`` for the
rule-gate (M3). plan: docs/plans/2026-06-08-wiki-llm-gen-phase1.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BlockType = Literal["lead", "heading", "paragraph", "list", "enriched"]
SourceKind = Literal["passage", "glossary", "kg"]
#: a Span's H0 marker; ``None`` = neutral canon prose.
SourceType = Literal["glossary", "enriched"]


class Source(BaseModel):
    """One citable fact handed to the LLM, labelled by us. ``cite_id`` (``P1``..) is
    echoed inline by the LLM; ``chapter_id`` + ``block_index`` anchor a passage to its
    source for jump-to-source; ``chapter_sort_order`` drives the spoiler horizon;
    ``snippet`` (~160 chars) backs the citation hover-preview."""

    cite_id: str
    kind: SourceKind = "passage"
    chapter_id: str | None = None
    block_index: int | None = None
    chapter_sort_order: int | None = None
    score: float | None = None
    snippet: str | None = None


class Span(BaseModel):
    """An inline run of text with its grounding. ``cites`` are RESOLVED Source ids (a
    label not in ``sources`` is dropped at parse); ``grounded`` is False when a
    non-trivial span resolved to zero cites (the rule-gate surface, M3);
    ``source_type`` marks enriched/quarantined inline material (H0)."""

    text: str
    cites: list[str] = Field(default_factory=list)
    source_type: SourceType | None = None
    grounded: bool = True


class Block(BaseModel):
    """One ordered article block. ``spans`` for text blocks
    (lead/heading/paragraph/quote/enriched); ``items`` (each a ``Span[]`` line) for a
    list. ``source_chapter_max`` = the highest cited-passage ``chapter_sort_order`` in
    this block — the per-block spoiler horizon (article horizon = max over blocks)."""

    type: BlockType
    level: int | None = None
    ordered: bool = False
    spans: list[Span] = Field(default_factory=list)
    items: list[list[Span]] = Field(default_factory=list)
    source_chapter_max: int | None = None

    def all_spans(self) -> list[Span]:
        """Flatten text-spans + list-item-spans (order-preserving)."""
        out = list(self.spans)
        for item in self.items:
            out.extend(item)
        return out


class WikiArticleIR(BaseModel):
    """The whole article. ``blocks`` = the ordered body; ``sources`` = the cite-label
    table (we own it). ``language`` comes from the BookProfile (M1). Generation-stage
    only — mapped forward to TipTap/markdown/plaintext, never stored as-is."""

    schema_version: int = 1
    entity_id: str
    display_name: str
    kind: str = ""
    language: str = "auto"
    blocks: list[Block] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)

    @property
    def spoiler_horizon(self) -> int | None:
        """Article-level spoiler horizon = max block ``source_chapter_max`` (C1/§5.1)."""
        maxes = [b.source_chapter_max for b in self.blocks if b.source_chapter_max is not None]
        return max(maxes) if maxes else None

    @property
    def grounded_claim_count(self) -> int:
        """Count of grounded, cited spans across the body — the rule-gate's
        zero-grounded check (M3 skips an entity whose article has none)."""
        return sum(1 for b in self.blocks for s in b.all_spans() if s.cites and s.grounded)

    def source_by_id(self, cite_id: str) -> Source | None:
        for s in self.sources:
            if s.cite_id == cite_id:
                return s
        return None
