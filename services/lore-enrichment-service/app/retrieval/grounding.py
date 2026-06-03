"""Grounding COMPOSITION (de-bias C2 / slice 0c).

The P1 pipeline used to ground ONLY on the per-project ``source_corpus`` (an embed
search). For an *extracted* book that corpus is usually empty, so generation had
nothing to cite and skipped the gap — even though the platform already holds a rich
digest of the book (glossary authored canon + knowledge-service passages/facts).

This module COMPOSES grounding from multiple providers — **entity-tight first
(glossary canon), breadth last (knowledge ``build_context`` passages)** — on top of
the existing corpus search, deduped + top-K. It does NOT re-ingest chapters; it
reuses what extraction already produced.

H0 unchanged: grounding is EVIDENCE the generator cites, never canon. A provider
that errors / has nothing degrades to ``[]`` (Q6) — it never raises into the
pipeline, and an entity with truly nothing known still produces no grounding (so
generation legitimately skips it).
"""

from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable

from app.retrieval.strategy import GroundingRef
from app.strategies.base import StrategyContext

logger = logging.getLogger("lore_enrichment.grounding")

__all__ = [
    "GroundingProviderFn",
    "compose_grounding",
    "make_glossary_canon_provider",
    "make_knowledge_context_provider",
    "parse_context_passages",
]

#: A grounding provider: (entity canonical_name, missing-dimension labels, context)
#: → extra grounding refs. Async so a real impl can hit a client; MUST NOT raise
#: (degrade to ``[]`` on any failure — the composer treats a provider as best-effort).
GroundingProviderFn = Callable[
    [str, list[str], StrategyContext], Awaitable[list[GroundingRef]]
]


def _excerpt_key(text: str) -> str:
    """Dedup key: collapse whitespace + lowercase a prefix so two providers that
    surface the same passage (corpus + knowledge-context) don't double-count."""
    return re.sub(r"\s+", " ", (text or "")).strip().lower()[:160]


async def compose_grounding(
    base: list[GroundingRef],
    providers: list[GroundingProviderFn],
    *,
    canonical_name: str,
    missing_labels: list[str],
    context: StrategyContext,
    top_k: int,
) -> list[GroundingRef]:
    """Merge ``base`` (the corpus search refs) with each provider's refs.

    Deterministic: union → dedup by normalized excerpt (first occurrence wins, so
    a higher-priority earlier provider keeps its ref) → stable sort by score
    descending (ties keep insertion order) → top-K. Each provider is best-effort:
    an exception is logged + skipped (Q6), never propagated. Pass providers in
    PRIORITY order (entity-tight before breadth)."""
    merged: list[GroundingRef] = list(base)
    for provider in providers:
        try:
            merged.extend(await provider(canonical_name, missing_labels, context))
        except Exception:  # noqa: BLE001 — a grounding provider is best-effort (Q6)
            logger.warning(
                "grounding provider failed for %s (skipped)", canonical_name,
                exc_info=True,
            )
    # dedup by excerpt, first occurrence wins (base + earlier providers prioritized)
    seen: set[str] = set()
    deduped: list[GroundingRef] = []
    for ref in merged:
        key = _excerpt_key(ref.excerpt)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    # stable sort by score desc; Python's sort is stable so ties keep order
    deduped.sort(key=lambda r: -r.score)
    return deduped[:top_k]


# ── glossary authored-canon provider (entity-tight) ────────────────────────────

def make_glossary_canon_provider(
    glossary, book_id, *, canon_score: float = 1.0
) -> GroundingProviderFn:
    """Provider: the entity's authored ``short_description`` (glossary canon) as one
    grounding ref. Entity-tight + clean. ``glossary``/``book_id`` absent → no-op.
    Caches the book's {name: description} once per provider instance."""
    cache: dict[str, str] | None = None

    async def _provider(canonical_name, _missing, _context) -> list[GroundingRef]:
        nonlocal cache
        if glossary is None or book_id is None:
            return []
        if cache is None:
            entities = await glossary.list_entities(book_id=book_id)
            cache = {e.name: e.description for e in entities if e.name}
        desc = (cache.get(canonical_name) or "").strip()
        if not desc:
            return []
        return [GroundingRef(
            corpus_id="glossary:canon", chunk_id=f"canon:{canonical_name}",
            chunk_index=0, excerpt=desc, score=round(canon_score, 6),
        )]

    return _provider


# ── knowledge build_context provider (breadth) ─────────────────────────────────

_PASSAGE_RE = re.compile(
    r'<passage\b[^>]*\bscore="(?P<score>[0-9.]+)"[^>]*>(?P<text>.*?)</passage>',
    re.DOTALL,
)
_XML_UNESCAPE = {"&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'", "&amp;": "&"}


def parse_context_passages(context_str: str) -> list[tuple[str, float]]:
    """Extract ``(text, score)`` from the ``<passages>`` block of a knowledge
    ``build_context`` string (format: ``<passage source_id=… score="0.85">text
    </passage>``). Returns [] when there is no passages block (Mode-2 static, or an
    extraction-disabled project). XML-unescaped + whitespace-trimmed."""
    out: list[tuple[str, float]] = []
    for m in _PASSAGE_RE.finditer(context_str or ""):
        text = m.group("text").strip()
        for esc, ch in _XML_UNESCAPE.items():
            text = text.replace(esc, ch)
        text = text.strip()
        if not text:
            continue
        try:
            score = float(m.group("score"))
        except (TypeError, ValueError):
            score = 0.0
        out.append((text, score))
    return out


def make_knowledge_context_provider(
    build_context_fn, *, max_passages: int = 5
) -> GroundingProviderFn:
    """Provider: knowledge-service ``build_context`` L3 passages as breadth grounding.

    ``build_context_fn`` is an async ``(message, context) -> context_str`` seam
    (bound to ``KnowledgeClient.build_context`` by the book's user/project). The
    query is the entity name + its missing-dimension labels (same shape as the
    corpus query). Degrade-safe: a down/empty/404 knowledge read → ``[]``."""
    async def _provider(canonical_name, missing_labels, context) -> list[GroundingRef]:
        if build_context_fn is None:
            return []
        message = (canonical_name + " " + " ".join(missing_labels)).strip()
        ctx_str = await build_context_fn(message, context)
        passages = parse_context_passages(ctx_str)[:max_passages]
        return [
            GroundingRef(
                corpus_id="knowledge:context", chunk_id=f"kctx:{i}",
                chunk_index=i, excerpt=text, score=round(score, 6),
            )
            for i, (text, score) in enumerate(passages)
        ]

    return _provider
