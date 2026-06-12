"""Real contradiction canon-lookup (RAID C3 / F-C12-1).

The C12 contradiction check compares a generated fact against EXISTING authored
canon for the same entity. That canon is the glossary entity's authored
``description`` (the ``source_type='glossary'`` SSOT) — book-scoped. This module
builds the :data:`~app.verify.canon_verify.CanonLookupFn` the assembly injects,
replacing the inert hardcoded ``return []`` (F-C12-1) with a REAL read that:

  * resolves the entity by canonical name within the book and returns its authored
    ``description`` as a :class:`~app.verify.canon_verify.CanonFact`;
  * caches the book's entities ONCE per run (the verifier calls per dimension);
  * DEGRADES honestly — returns ``[]`` when there is no ``book_id`` / no entity /
    no authored canon (a genuine "no canon known", not a false-green), and
    RAISES on a glossary read error so the verifier records ``verify_degraded``
    (a swallowed error would masquerade as "no canon" → false-green).

**Precision limit (documented, extends F-C12-3 / spec R2):** Classical-Chinese
prose has no word boundaries and the service ships no segmenter, so
:func:`extract_canon_terms` is a COARSE heuristic (CJK runs split on common
particles, short fragments kept). Contradiction detection on prose canon is
therefore conservative — it UNDER-fires rather than over-fires, the safe
direction for a check that can feed an auto-reject (C3).
"""

from __future__ import annotations

import re
from uuid import UUID

from app.clients.glossary import GlossaryClient
from app.verify.canon_verify import CanonFact, CanonLookupFn

__all__ = ["extract_canon_terms", "make_glossary_canon_lookup"]

#: Detects whether a string contains any CJK character (→ run the segmenter).
_HAS_CJK = re.compile(r"[一-鿿]")

#: jieba POS tags kept as canon TERMS — PROPER nouns only (place / person / org /
#: other-proper). Generic nouns ('n') + verbs/adjectives are DROPPED: keeping
#: generic common nouns would re-open the C3 false-positive risk (a benign fact
#: mentioning a common noun + a negation would wrongly flag a contradiction →
#: auto-reject). Proper nouns are the SPECIFIC canon tokens a real contradiction
#: negates — consistent with the Latin Capitalized-proper-noun rule below.
_PROPER_NOUN_POS = frozenset({"ns", "nr", "nt", "nz", "nrt", "nrfg", "nsfg"})

#: Lazily-loaded jieba POS segmenter (LE-060) — imported on first extraction so
#: its dictionary cost is paid only when a contradiction canon term is actually
#: needed (rare on sparse canon), not at module/service import time.
_posseg = None


def _segmenter():
    global _posseg
    if _posseg is None:
        import jieba  # noqa: PLC0415 — intentional lazy import (dict-load cost)
        import jieba.posseg as pseg  # noqa: PLC0415
        import logging as _logging
        jieba.setLogLevel(_logging.ERROR)  # silence the one-time dict-build INFO
        _posseg = pseg
    return _posseg

#: Latin words (>=3 chars) — for non-CJK / mixed canon (the platform is
#: multilingual). Short function words are excluded via _LATIN_STOPWORDS.
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
_LATIN_STOPWORDS = frozenset({
    "the", "and", "for", "with", "who", "his", "her", "its", "their", "from",
    "into", "onto", "was", "were", "are", "has", "had", "have", "been", "being",
    "that", "this", "these", "those", "but", "not", "where", "when", "which",
    "whom", "what", "than", "then", "they", "them", "she", "him",
})

#: A CJK proper-noun shorter than this is too generic to be a useful term.
_MIN_TERM = 2
_MAX_TERMS = 8


def extract_canon_terms(text: str, *, entity_name: str) -> tuple[str, ...]:
    """Canon TERMS from authored canon prose — the salient PROPER nouns a
    contradicting fact would have to negate.

    CJK (LE-060): real word segmentation via jieba POS-tagging, keeping ONLY
    proper-noun tags (place/person/org/other-proper) — generic nouns + verbs are
    dropped so a benign fact mentioning a common word + a negation can't
    false-positive a contradiction (the C3 over-fire risk). Latin: Capitalized
    proper-noun-like tokens. EXCLUDES ``entity_name`` (+ its component words) — a
    fact mentioning the entity's own name is not a contradiction signal. Deduped,
    order-preserving, capped. Conservative by design (under-fires)."""
    if not text or not text.strip():
        return ()
    out: list[str] = []
    # Exclude the entity name AND its component words (negating the entity's own
    # name is not a contradiction signal).
    seen: set[str] = {entity_name}
    seen.update(w.lower() for w in _LATIN_WORD.findall(entity_name))
    # ── CJK terms: jieba segmentation, PROPER nouns only (LE-060) ────────────
    if _HAS_CJK.search(text):
        for tok in _segmenter().cut(text):
            word, flag = tok.word, tok.flag
            if (
                flag in _PROPER_NOUN_POS
                and len(word) >= _MIN_TERM
                and word not in seen
                and word not in entity_name  # drop a fragment of the entity name
            ):
                seen.add(word)
                out.append(word)
                if len(out) >= _MAX_TERMS:
                    return tuple(out)
    # ── Latin words: keep only PROPER-NOUN-like (Capitalized) tokens ─────────
    # review-impl MED#1: common lowercase words (traveling, meet, business) make
    # the contradiction heuristic OVER-fire (a benign fact mentioning a common
    # canon word + a negation would wrongly auto-reject). Proper nouns (names,
    # places — Transylvania, Dracula) are the SPECIFIC canon tokens a real
    # contradiction would negate; restricting to Capitalized tokens drops the
    # common-word false-positive surface. (Residual: a sentence-initial common
    # word is capitalized — rare; the human gate remains the backstop, R2.)
    for word in _LATIN_WORD.findall(text):
        if not word[0].isupper():
            continue
        key = word.lower()
        if key in _LATIN_STOPWORDS or key in seen:
            continue
        seen.add(key)
        out.append(word)
        if len(out) >= _MAX_TERMS:
            break
    return tuple(out)


def make_glossary_canon_lookup(
    glossary: GlossaryClient | None, *, book_id: UUID | None
) -> CanonLookupFn:
    """Build the real contradiction :data:`CanonLookupFn` over glossary canon.

    Returns an ``async (entity_name, dimension) -> list[CanonFact]`` that reads the
    entity's authored ``description`` (book-scoped, cached once per run). When
    ``book_id`` or ``glossary`` is absent it returns ``[]`` WITHOUT a fetch (no
    scope → honest degrade). A glossary read error PROPAGATES (so the verifier
    records ``verify_degraded`` — never a false-green). An entity with empty
    authored canon returns ``[]`` (a genuine "no canon known")."""
    # Cache the book's {canonical_name -> description}, populated on first success.
    cache: dict[str, str] | None = None

    async def _lookup(entity_name: str, dimension: str) -> list[CanonFact]:
        nonlocal cache
        if glossary is None or book_id is None:
            return []  # no scope → genuine "no canon" (degrade handled upstream)
        if cache is None:
            # Read error PROPAGATES (not cached) → verifier sets verify_degraded;
            # a later dimension may retry. Only a SUCCESS populates the cache.
            entities = await glossary.list_entities(book_id=book_id)
            cache = {e.name: e.description for e in entities if e.name}
        description = cache.get(entity_name)
        if not description or not description.strip():
            return []  # no authored canon for this entity → cannot contradict
        return [
            CanonFact(
                entity_name=entity_name,
                dimension=dimension,
                assertion=description,
                terms=extract_canon_terms(description, entity_name=entity_name),
            )
        ]

    return _lookup
