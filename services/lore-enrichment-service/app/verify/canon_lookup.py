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

#: Maximal CJK runs; everything else is a delimiter.
_CJK_RUN = re.compile(r"[一-鿿]+")

#: Latin words (>=3 chars) — for non-CJK / mixed canon (the platform is
#: multilingual). Short function words are excluded via _LATIN_STOPWORDS.
_LATIN_WORD = re.compile(r"[A-Za-z]{3,}")
_LATIN_STOPWORDS = frozenset({
    "the", "and", "for", "with", "who", "his", "her", "its", "their", "from",
    "into", "onto", "was", "were", "are", "has", "had", "have", "been", "being",
    "that", "this", "these", "those", "but", "not", "where", "when", "which",
    "whom", "what", "than", "then", "they", "them", "she", "him",
})

#: Common Classical/modern grammatical particles used as crude split points so a
#: CJK run like 蓬萊位于东海 yields the salient tokens (蓬萊, 东海) rather than one
#: opaque blob. Not a real segmenter — a conservative approximation.
_PARTICLE_CHARS = set("之的了也其以而與与和及或在乃為为是位於于有與则即将且故所被把")

#: Fragments at/below this length are kept as candidate canon terms (a longer run
#: is too specific to re-match in a contradicting fact); 2 is the CJK floor.
_MIN_TERM, _MAX_TERM = 2, 4
_MAX_TERMS = 8


def extract_canon_terms(text: str, *, entity_name: str) -> tuple[str, ...]:
    """Best-effort canon TERMS from authored canon prose (coarse, CJK-aware).

    Splits each maximal CJK run on common particles and keeps short (2–4 char)
    fragments — candidate salient nouns a contradicting fact would have to negate.
    EXCLUDES ``entity_name`` (a fact mentioning the entity's own name is not a
    contradiction signal). Deduped, order-preserving, capped. Coarse by design
    (no segmenter) → contradiction stays conservative (under-fires)."""
    if not text or not text.strip():
        return ()
    out: list[str] = []
    # Exclude the entity name AND its component words (negating the entity's own
    # name is not a contradiction signal).
    seen: set[str] = {entity_name}
    seen.update(w.lower() for w in _LATIN_WORD.findall(entity_name))
    # ── CJK terms: split runs on common particles, keep short fragments ──────
    for run in _CJK_RUN.findall(text):
        buf = ""
        fragments: list[str] = []
        for ch in run:
            if ch in _PARTICLE_CHARS:
                if buf:
                    fragments.append(buf)
                buf = ""
            else:
                buf += ch
        if buf:
            fragments.append(buf)
        for frag in fragments:
            if _MIN_TERM <= len(frag) <= _MAX_TERM and frag not in seen:
                seen.add(frag)
                out.append(frag)
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
