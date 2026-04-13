"""Shared stopword sets for context-builder text processing.

Centralised here so the candidate extractor (selectors/glossary.py)
and the cross-layer dedup (formatters/dedup.py) can't drift apart.

Two distinct sets live here because they serve different purposes:

  * STOPPHRASES_LOWER — tokens that should NOT be treated as proper-noun
    candidates even when they're capitalized at the start of a sentence
    ("Tell me about Kai" → "Tell" is filtered, "Kai" survives). Tuned
    for chat-style input where sentence-initial verbs masquerade as
    names. Used by extract_candidates().

  * KEYWORD_STOPWORDS_LOWER — tokens that don't carry enough signal to
    count as evidence of cross-layer overlap ("the", "this", "would",
    etc.). Tuned to filter the noise in keyword-overlap dedup. Used by
    filter_entities_not_in_summary().

The two sets overlap (`the`, `this`, `that`, etc.) but the candidate
extractor needs more conversational verbs / pronouns ("tell", "what",
"who"), and the dedup needs more abstract function words ("with",
"could", "much"). A single union would give worse results in both
sites.

CJK_PARTICLES is the small set of Chinese function words used to
re-split long CJK runs in extract_candidates. Without a real segmenter
(jieba) this is a best-effort heuristic — documented limitation.
"""

__all__ = [
    "STOPPHRASES_LOWER",
    "KEYWORD_STOPWORDS_LOWER",
    "CJK_PARTICLES",
]


# ── Used by candidate extraction (proper-noun heuristic) ──────────────────
STOPPHRASES_LOWER: frozenset[str] = frozenset(
    {
        "i", "the", "a", "an", "tell", "me", "about", "what", "who",
        "where", "when", "why", "how", "is", "are", "was", "were",
        "do", "does", "did", "can", "could", "should", "would",
        "this", "that", "these", "those", "my", "your", "his", "her",
        "their", "our", "they", "them", "mr", "mrs", "ms",
    }
)


# ── Used by L1/glossary dedup (keyword overlap heuristic) ─────────────────
KEYWORD_STOPWORDS_LOWER: frozenset[str] = frozenset(
    {
        "this", "that", "these", "those", "with", "from", "into",
        "have", "having", "been", "being", "their", "them", "they",
        "would", "could", "should", "will", "were", "where", "what",
        "when", "about", "also", "just", "only", "some", "such",
        "then", "than", "much", "very", "even", "most", "more", "less",
        "which",
    }
)


# ── CJK particles used as soft segment separators ─────────────────────────
CJK_PARTICLES: str = "的是了在和与及或把被这那就也都还很"
