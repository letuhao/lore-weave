"""A1 (ML-1) — per-language intent keyword registry.

The query-intent classifier's five keyword categories used to be English-only, so
a zh/ja/ko/vi query matched none and fell to a blanket degrade-open default. This
package holds one module per language (the ML-1 pattern-registry shape) and
compiles each category into ONE union regex for the classifier's hot path.

Union, not langdetect dispatch: the scripts are disjoint (a CJK keyword can never
match ASCII text, and vice-versa), so a single union regex routes each language by
its own vocabulary with **no detection dependency** and **zero effect on English**
(pure-ASCII queries only ever match the English alternatives). Latin-script
languages (en, vi) are `\b`-word-bounded to avoid substring hits ("know" in
"knowledge"); unspaced CJK languages (zh, ja, ko) are matched bare (word
boundaries are meaningless between ideographs).

Uncovered scripts (ar/th/hi/…) match nothing here and are handled by the
classifier's non-ASCII degrade-net — genuine ML-1 degrade-open.
"""

from __future__ import annotations

import re

from app.context.intent.lang import en, ja, ko, vi, zh

__all__ = [
    "HISTORICAL_STRONG",
    "HISTORICAL_WEAK",
    "RECENT",
    "RELATIONAL_KEYWORDS",
    "RELATIONAL_STRONG",
    "get_intent_markers",
]

_LATIN_MODULES = (en, vi)   # space-delimited ⇒ \b-bounded
_CJK_MODULES = (zh, ja, ko)  # unspaced ⇒ bare


def _combine(attr: str) -> re.Pattern[str]:
    """Build one union regex for a category across all languages.

    Latin alternatives share one `\\b(?:…)\\b` group; CJK alternatives are
    appended bare. Empty per-language strings are skipped.
    """
    latin = "|".join(p for p in (getattr(m, attr) for m in _LATIN_MODULES) if p)
    cjk = "|".join(p for p in (getattr(m, attr) for m in _CJK_MODULES) if p)
    parts: list[str] = []
    if latin:
        parts.append(rf"\b(?:{latin})\b")
    if cjk:
        parts.append(cjk)
    return re.compile("|".join(parts), re.IGNORECASE)


HISTORICAL_STRONG = _combine("HISTORICAL_STRONG")
HISTORICAL_WEAK = _combine("HISTORICAL_WEAK")
RECENT = _combine("RECENT")
RELATIONAL_KEYWORDS = _combine("RELATIONAL_KEYWORDS")
RELATIONAL_STRONG = _combine("RELATIONAL_STRONG")


def get_intent_markers(lang: str):
    """Introspection hook (ML-1 registry shape): the raw per-language module for
    `lang`, or English as the fallback. The classifier uses the compiled unions
    above; this exists for tests / tuning to inspect one language's vocabulary."""
    return {"en": en, "zh": zh, "ja": ja, "ko": ko, "vi": vi}.get(lang, en)
