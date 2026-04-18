"""Cross-layer deduplication between L1 summary and glossary entries.

When a project-level summary (L1) mentions an entity that the glossary
selector also returned, the glossary entry is redundant — the summary
is richer authored prose, and re-stating the short_description wastes
tokens. K4.12 drops those duplicate glossary entries.

We use a keyword-overlap heuristic, not semantic similarity:

  1. Tokenize L1 summary into lowercased words ≥ 4 chars (skip
     pronouns / stopwords).
  2. For each glossary entity, compute a match score: how many
     distinct ≥4-char tokens from its cached_name + aliases +
     short_description appear in the L1 token set.
  3. If the score crosses a threshold (default 2 tokens), treat the
     entity as "already covered" and drop it.

Pinned entities are kept regardless — the user explicitly marked them
as always-include.

This is intentionally conservative: it's better to leave a redundant
entry in than to drop one the summary only glancingly mentions.
"""

import re
from typing import Iterable

from app.clients.glossary_client import GlossaryEntityForContext
from app.context.formatters.stopwords import KEYWORD_STOPWORDS_LOWER

__all__ = ["filter_entities_not_in_summary", "filter_facts_not_in_summary"]


# Match Unicode word characters. \w in Python's `re` covers Latin
# letters + digits + underscore + accented letters. For CJK we fall
# back to 2-char runs via a separate path below.
_TOKEN_RE = re.compile(r"[\w]{4,}", re.UNICODE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

# Stopwords come from the shared module so dedup and candidate
# extraction can't drift independently.
_STOPWORDS_LOWER = KEYWORD_STOPWORDS_LOWER


def _tokenize(text: str) -> set[str]:
    """Return a set of ≥4-char lowercase word tokens from `text`.

    Includes CJK 2+ char runs too so Chinese names in the summary
    count as keywords for Chinese glossary entries.
    """
    if not text:
        return set()
    tokens: set[str] = set()
    for m in _TOKEN_RE.finditer(text):
        tok = m.group(0).lower()
        if tok not in _STOPWORDS_LOWER:
            tokens.add(tok)
    for m in _CJK_RE.finditer(text):
        tokens.add(m.group(0))
    return tokens


def _entity_keywords(e: GlossaryEntityForContext) -> set[str]:
    parts = [e.cached_name or "", e.short_description or "", *e.cached_aliases]
    combined = " ".join(parts)
    return _tokenize(combined)


def filter_entities_not_in_summary(
    entities: Iterable[GlossaryEntityForContext],
    summary_text: str | None,
    *,
    min_overlap: int = 2,
) -> list[GlossaryEntityForContext]:
    """Return entities whose keywords are NOT sufficiently covered by
    the summary. Pinned entities are always kept.

    `min_overlap`: number of distinct tokens that must overlap before
    an entity is considered "duplicated by the summary". 2 is
    conservative — a lone shared word like the character's name isn't
    enough; a short description that also repeats makes it enough.
    """
    summary_tokens = _tokenize(summary_text or "")
    if not summary_tokens:
        # No summary (or summary had no useful keywords) → keep everything.
        return list(entities)

    kept: list[GlossaryEntityForContext] = []
    for e in entities:
        if e.is_pinned:
            kept.append(e)
            continue
        overlap = _entity_keywords(e) & summary_tokens
        if len(overlap) >= min_overlap:
            # Summary already covers this entity — drop the glossary row.
            continue
        kept.append(e)
    return kept


def filter_facts_not_in_summary(
    fact_texts: Iterable[str],
    summary_text: str | None,
    *,
    min_overlap: int = 2,
) -> list[str]:
    """K18.4 — drop fact strings already expressed by the L1 summary.

    Takes raw fact-sentence strings (e.g. "Arthur trusts Lancelot",
    "Morgana does not know Merlin") and returns those whose token
    overlap with the summary is below `min_overlap`.

    Threshold matches the entity version's default (2 distinct
    ≥4-char tokens). Note the ≥4-char filter in `_tokenize` — short
    names like "Kai" (3 chars) don't count toward overlap, so the
    threshold only triggers when the summary reproduces enough of
    the fact's longer content words to make the L2 row redundant.

    Order is preserved so the L2 selector's ranking stays intact.
    """
    summary_tokens = _tokenize(summary_text or "")
    if not summary_tokens:
        return list(fact_texts)

    kept: list[str] = []
    for fact in fact_texts:
        overlap = _tokenize(fact) & summary_tokens
        if len(overlap) >= min_overlap:
            continue
        kept.append(fact)
    return kept
