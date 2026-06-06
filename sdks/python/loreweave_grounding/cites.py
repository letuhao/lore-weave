"""Unified grounding citation + composition (mui #3 grounding port).

`GroundingCite` is the service-agnostic evidence shape the four consumers'
divergent structs (lore-enrichment GroundingRef, knowledge L3Passage,
composition lore-dict, glossary evidence row) all map onto via the adapters.
`merge_cites` / `compose_cites` lift lore-enrichment's `compose_grounding`
dedup-higher-score → stable-sort-by-score-desc → top-K algorithm, generalized to
the unified shape (a `None` score = authored canon, which ranks first).
"""

from __future__ import annotations

import logging
import re
from itertools import chain
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

logger = logging.getLogger("loreweave_grounding.cites")

__all__ = [
    "GroundingCite",
    "CiteProviderFn",
    "merge_cites",
    "compose_cites",
    "from_glossary_evidence",
    "from_l3_passage",
    "from_grounding_ref",
]


class GroundingCite(BaseModel):
    """One piece of grounding evidence, unified across consumers.

    ``score`` is ``None`` for AUTHORED canon (glossary — no relevance rank); a
    float in [0,1] for retrieved/scored evidence. Authored canon ranks ahead of
    any scored cite in `merge_cites`."""

    source_type: str            # "chapter" | "glossary_entity" | "chat_message" | "corpus" | "knowledge" | "manual"
    source_id: str
    text: str
    score: float | None = None
    chapter_id: str | None = None
    chapter_index: int | None = None
    block_or_line: str | None = None


#: A provider yields extra cites for the current context. Nullary thunk so the
#: SERVICE closes over its own args (entity name, query, clients) — the SDK owns
#: only the merge/dedup/rank algorithm, not the I/O. MUST NOT raise (best-effort).
CiteProviderFn = Callable[[], Awaitable[list[GroundingCite]]]


def _excerpt_key(text: str) -> str:
    """Dedup key: collapse whitespace + lowercase a prefix so two providers that
    surface the same passage don't double-count."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()[:160]


def _score_num(score: float | None) -> float:
    """None (authored canon) ranks highest; floats rank by value."""
    return float("inf") if score is None else score


def merge_cites(
    *cite_lists: list[GroundingCite],
    top_k: int,
    dedup_key: Callable[[GroundingCite], str] | None = None,
) -> list[GroundingCite]:
    """Union → dedup by key (keep the HIGHER-score cite; authored canon/None wins)
    → stable sort by score descending → top-K. Deterministic; ties keep insertion
    order (Python's sort is stable). Mirrors lore-enrichment `compose_grounding`."""
    key_fn = dedup_key or (lambda c: _excerpt_key(c.text))
    best: dict[str, GroundingCite] = {}
    order: list[str] = []
    for cite in chain.from_iterable(cite_lists):
        key = key_fn(cite)
        if not key:
            continue
        prev = best.get(key)
        if prev is None:
            best[key] = cite
            order.append(key)
        elif _score_num(cite.score) > _score_num(prev.score):
            best[key] = cite
    deduped = [best[k] for k in order]
    deduped.sort(key=lambda c: -_score_num(c.score))
    return deduped[:top_k]


async def compose_cites(
    base: list[GroundingCite],
    providers: list[CiteProviderFn],
    *,
    top_k: int,
    dedup_key: Callable[[GroundingCite], str] | None = None,
) -> list[GroundingCite]:
    """Merge ``base`` with each provider's cites. Each provider is best-effort:
    an exception is logged + skipped (degrade), never propagated. Pass providers
    in PRIORITY order (entity-tight before breadth). Then `merge_cites`."""
    collected: list[list[GroundingCite]] = [list(base)]
    for provider in providers:
        try:
            collected.append(await provider())
        except Exception:  # noqa: BLE001 — a grounding provider is best-effort
            logger.warning("grounding provider failed (skipped)", exc_info=True)
    return merge_cites(*collected, top_k=top_k, dedup_key=dedup_key)


# ── adapters: each consumer's existing shape → GroundingCite ───────────────────


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from an object attr OR a dict key (consumers pass either)."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def from_glossary_evidence(row: Any) -> GroundingCite:
    """glossary `/evidences` row (authored canon — no score)."""
    return GroundingCite(
        source_type="glossary_entity",
        source_id=str(_get(row, "attr_value_id") or _get(row, "evidence_id") or ""),
        text=_get(row, "original_text") or _get(row, "text") or "",
        score=None,
        chapter_id=_get(row, "chapter_id"),
        chapter_index=_get(row, "chapter_index"),
        block_or_line=_get(row, "block_or_line"),
    )


def from_l3_passage(p: Any) -> GroundingCite:
    """knowledge `L3Passage` (retrieved, scored)."""
    return GroundingCite(
        source_type=_get(p, "source_type") or "chapter",
        source_id=str(_get(p, "source_id") or ""),
        text=_get(p, "text") or "",
        score=_get(p, "score"),
        chapter_index=_get(p, "chapter_index"),
    )


def from_grounding_ref(r: Any) -> GroundingCite:
    """lore-enrichment `GroundingRef` (corpus/canon/context, scored).

    Maps the synthetic corpus_id (``glossary:canon`` / ``knowledge:context``) to a
    source_type; a real corpus UUID stays ``corpus``. The ref's excerpt → text;
    its score is kept as-is (lore-enrichment scores canon 1.0, not None).

    `knowledge:context` cites carry only a synthetic chunk_id (lore-enrichment's
    provider discarded the real source_id upstream), so they map to a neutral
    ``"knowledge"`` source_type — NOT ``"chapter"``, which would falsely assert a
    chapter source_id a consumer might try to resolve (review-impl MED-1)."""
    corpus_id = str(_get(r, "corpus_id") or "")
    if corpus_id.startswith("glossary"):
        source_type = "glossary_entity"
    elif corpus_id.startswith("knowledge"):
        source_type = "knowledge"
    else:
        source_type = "corpus"
    return GroundingCite(
        source_type=source_type,
        source_id=str(_get(r, "chunk_id") or corpus_id),
        text=_get(r, "excerpt") or "",
        score=_get(r, "score"),
        chapter_index=_get(r, "chunk_index"),
    )
