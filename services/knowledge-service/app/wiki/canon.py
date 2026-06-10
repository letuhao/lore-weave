"""Wiki canon-lookup for the contradiction check (wiki-llm M4 / §C10).

Builds the SDK `CanonVerifier`'s injected `CanonLookupFn` — the (entity_name,
dimension) → authored-canon read its contradiction check compares a generated
article against. The canon is the entity's glossary **`short_description`** (the
authored canonical-content column, ≤500 chars), which the M2 context already
fetched, so the lookup closes over the context brief — no extra glossary call.

`extract_canon_terms` (ported from lore-enrichment `verify/canon_lookup.py`,
LE-060) pulls the salient PROPER nouns a contradicting fact would have to negate:
CJK via jieba POS-tagging (proper-noun tags ONLY — generic nouns/verbs dropped so
a benign fact mentioning a common word + a negation can't false-positive), Latin
via Capitalized tokens. Conservative by design — it UNDER-fires (the safe
direction for a check that can feed an auto-reject).
"""

from __future__ import annotations

import re

from loreweave_grounding.verify import CanonFact, CanonLookupFn

from app.wiki.context import EntityBrief

__all__ = ["extract_canon_terms", "make_canon_lookup"]

#: Detects whether a string contains any CJK character (→ run the segmenter).
_HAS_CJK = re.compile(r"[一-鿿]")

#: jieba POS tags kept as canon TERMS — PROPER nouns only (place/person/org/
#: other-proper). Generic nouns + verbs/adjectives are DROPPED (keeping common
#: nouns re-opens the false-positive risk: a benign fact mentioning a common noun
#: + a negation would wrongly flag a contradiction → auto-reject).
_PROPER_NOUN_POS = frozenset({"ns", "nr", "nt", "nz", "nrt", "nrfg", "nsfg"})

#: Lazily-loaded jieba POS segmenter — imported on first extraction so its dict
#: cost is paid only when a contradiction term is actually needed (rare on sparse
#: canon), not at module/service import time.
_posseg = None


def _segmenter():
    global _posseg
    if _posseg is None:
        import jieba  # noqa: PLC0415 — intentional lazy import (dict-load cost)
        import jieba.posseg as pseg  # noqa: PLC0415
        import logging as _logging  # noqa: PLC0415

        jieba.setLogLevel(_logging.ERROR)  # silence the one-time dict-build INFO
        _posseg = pseg
    return _posseg


#: Latin words (>=3 chars) — for non-CJK / mixed canon. Short function words
#: excluded via _LATIN_STOPWORDS.
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

    CJK: jieba POS-tagging, proper-noun tags only. Latin: Capitalized tokens.
    EXCLUDES ``entity_name`` (+ its component words) — a fact mentioning the
    entity's own name is not a contradiction signal. Deduped, order-preserving,
    capped. Conservative (under-fires)."""
    if not text or not text.strip():
        return ()
    out: list[str] = []
    seen: set[str] = {entity_name}
    seen.update(w.lower() for w in _LATIN_WORD.findall(entity_name))
    # ── CJK terms: jieba segmentation, PROPER nouns only ─────────────────────
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
    # ── Latin words: keep only Capitalized (proper-noun-like) tokens ─────────
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


def make_canon_lookup(brief: EntityBrief) -> CanonLookupFn:
    """Build the contradiction `CanonLookupFn` over the entity's authored canon.

    The canon is the entity's glossary ``short_description`` (already in the M2
    brief — glossary's canonical-content column). Dimension-agnostic: every
    section of the article is checked against the SAME entity canon (the article
    is about ONE entity). An entity with no authored canon → ``[]`` (a genuine
    "no canon known", which lets nothing contradict — NOT a degraded read, so the
    verifier does not false-fail). Never raises (no I/O — the canon is in hand)."""
    canon_text = (brief.short_description or "").strip()

    async def _lookup(entity_name: str, dimension: str) -> list[CanonFact]:
        if not canon_text:
            return []
        return [
            CanonFact(
                entity_name=brief.name,
                dimension=dimension,
                assertion=canon_text,
                terms=extract_canon_terms(canon_text, entity_name=brief.name),
            )
        ]

    return _lookup
