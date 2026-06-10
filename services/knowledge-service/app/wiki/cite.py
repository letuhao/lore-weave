"""Wiki citation provenance via the grounding SDK (wiki-llm M4 / §C4).

After generation, the article's body cites a subset of the sources we handed the
LLM (the labels that actually appear in the IR spans). This composes those
ACTUALLY-CITED sources into the `generation_provenance.citations` record (audit +
Phase-2 eval + the FE citation hover-preview) via the SDK's `compose_cites`
(dedup-by-text → rank-by-score → top-K). This is `loreweave_grounding`'s FIRST
live consumer (plan risk #5 — a real-passage smoke rides with M6).

Uncited sources are dropped (they grounded nothing in the final body); authored
canon (glossary, score=None) ranks ahead of scored passages.
"""

from __future__ import annotations

from loreweave_grounding.cites import GroundingCite, compose_cites

from app.wiki.ir import Source, WikiArticleIR

__all__ = ["compose_provenance_cites", "used_cite_ids"]

_KIND_TO_SOURCE_TYPE = {
    "passage": "chapter",
    "glossary": "glossary_entity",
    "kg": "knowledge",
}


def used_cite_ids(ir: WikiArticleIR) -> set[str]:
    """The cite labels that actually appear in the article body (a Source not in
    here grounded nothing in the final text)."""
    used: set[str] = set()
    for b in ir.blocks:
        for s in b.all_spans():
            used.update(s.cites)
    return used


def _source_to_cite(src: Source) -> GroundingCite:
    return GroundingCite(
        source_type=_KIND_TO_SOURCE_TYPE.get(src.kind, src.kind),
        source_id=src.chapter_id or src.cite_id,
        text=src.snippet or "",
        score=src.score,  # None for authored canon (glossary) → ranks first
        chapter_id=src.chapter_id,
        chapter_index=src.chapter_sort_order,
        block_or_line=str(src.block_index) if src.block_index is not None else None,
    )


async def compose_provenance_cites(
    ir: WikiArticleIR, *, top_k: int | None = None,
) -> list[GroundingCite]:
    """Compose the provenance citation list from the article's ACTUALLY-CITED
    sources. ``top_k`` caps the list (default = all cited, deduped). Returns ``[]``
    when nothing is cited (the rule-gate normally prevents that)."""
    used = used_cite_ids(ir)
    base = [_source_to_cite(s) for s in ir.sources if s.cite_id in used]
    if not base:
        return []
    k = top_k if top_k is not None else len(base)
    return await compose_cites(base, providers=[], top_k=k)
