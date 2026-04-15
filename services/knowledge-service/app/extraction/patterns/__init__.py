"""K15.3 — per-language pattern sets + language dispatch.

Per KSA §5.4, the pattern extractor loads different regex sets
per language and runs them against the detected primary language
of the input text. This package holds one module per supported
language plus the dispatch glue.

**Public surface:**
    - `Language` — closed enum of supported languages
    - `PatternSet` — frozen container for the five marker tuples
    - `get_patterns(lang)` — returns the `PatternSet` for a given
      language, falling back to English for anything unsupported
    - `detect_primary_language(text)` — ISO 639-1 of the dominant
      language, "mixed" when ambiguous, "en" on error
    - `split_by_language(text)` — sentence-level language split
      for mixed-language chapters; each chunk can be fed to the
      extractor with its own pattern set

**Five marker types (KSA §5.1):**
    DECISION   — "let's use", "we decided"
    PREFERENCE — "I prefer", "always use"
    MILESTONE  — "it works", "finished chapter N"
    NEGATION   — "does not know", "is unaware" (feeds L2 <negative>)
    SKIP       — hypothetical / counterfactual / reported speech
                 (callers must drop sentences matching any SKIP
                 pattern before running the triple extractor)

**Coverage policy.** KSA notes "don't perfection the patterns;
80% coverage is fine, LLM extractor catches the rest in Pass 2."
Keep each language module compact — 6-10 patterns per category.
Bulk imports of idiom lists will drift with language evolution
and waste regex compilation time.

**Determinism.** `langdetect` uses a probabilistic classifier
whose output depends on a random seed. We seed it at import time
so `detect_primary_language("same text")` is reproducible across
runs (tests, metrics, deployments). Without the seed, a
borderline sentence could flip languages on restart.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

# langdetect seed MUST be set before the first classification call
# or output is non-reproducible. Import-time seeding means even a
# race between `detect_primary_language` and app init is safe.
from langdetect import DetectorFactory, detect_langs, LangDetectException

from app.extraction.patterns import en, ja, ko, vi, zh

DetectorFactory.seed = 0

logger = logging.getLogger(__name__)

__all__ = [
    "Language",
    "SUPPORTED_LANGUAGES",
    "PatternSet",
    "get_patterns",
    "detect_primary_language",
    "split_by_language",
]


Language = Literal["en", "vi", "zh", "ja", "ko"]

SUPPORTED_LANGUAGES: tuple[Language, ...] = ("en", "vi", "zh", "ja", "ko")


@dataclass(frozen=True)
class PatternSet:
    """Compiled pattern bundle for one language.

    Every field is a tuple of compiled regex objects — tuples,
    not lists, so the instance is hashable and the per-language
    modules can share compiled patterns across calls without a
    module-level mutation risk.
    """

    language: Language
    decision: tuple[re.Pattern[str], ...]
    preference: tuple[re.Pattern[str], ...]
    milestone: tuple[re.Pattern[str], ...]
    negation: tuple[re.Pattern[str], ...]
    skip: tuple[re.Pattern[str], ...]


def _compile_all(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    # re.IGNORECASE is safe for CJK (no-op) and correct for Latin.
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


_PATTERN_SETS: dict[str, PatternSet] = {
    "en": PatternSet(
        language="en",
        decision=_compile_all(en.DECISION_MARKERS),
        preference=_compile_all(en.PREFERENCE_MARKERS),
        milestone=_compile_all(en.MILESTONE_MARKERS),
        negation=_compile_all(en.NEGATION_MARKERS),
        skip=_compile_all(en.SKIP_MARKERS),
    ),
    "vi": PatternSet(
        language="vi",
        decision=_compile_all(vi.DECISION_MARKERS),
        preference=_compile_all(vi.PREFERENCE_MARKERS),
        milestone=_compile_all(vi.MILESTONE_MARKERS),
        negation=_compile_all(vi.NEGATION_MARKERS),
        skip=_compile_all(vi.SKIP_MARKERS),
    ),
    "zh": PatternSet(
        language="zh",
        decision=_compile_all(zh.DECISION_MARKERS),
        preference=_compile_all(zh.PREFERENCE_MARKERS),
        milestone=_compile_all(zh.MILESTONE_MARKERS),
        negation=_compile_all(zh.NEGATION_MARKERS),
        skip=_compile_all(zh.SKIP_MARKERS),
    ),
    "ja": PatternSet(
        language="ja",
        decision=_compile_all(ja.DECISION_MARKERS),
        preference=_compile_all(ja.PREFERENCE_MARKERS),
        milestone=_compile_all(ja.MILESTONE_MARKERS),
        negation=_compile_all(ja.NEGATION_MARKERS),
        skip=_compile_all(ja.SKIP_MARKERS),
    ),
    "ko": PatternSet(
        language="ko",
        decision=_compile_all(ko.DECISION_MARKERS),
        preference=_compile_all(ko.PREFERENCE_MARKERS),
        milestone=_compile_all(ko.MILESTONE_MARKERS),
        negation=_compile_all(ko.NEGATION_MARKERS),
        skip=_compile_all(ko.SKIP_MARKERS),
    ),
}


def get_patterns(lang: str) -> PatternSet:
    """Return the compiled pattern set for `lang`, falling back
    to English for unsupported codes.

    Unsupported codes are not an error: a Vietnamese novelist
    writing a French aside should still get a best-effort pass
    (English patterns — which cover a lot of "said"/"if"/"would"
    false-positive markers that transfer across Latin-script
    languages). Track 2 may add more languages; until then the
    fallback is a soft landing, not a failure.
    """
    return _PATTERN_SETS.get(lang, _PATTERN_SETS["en"])


# langdetect returns codes like "zh-cn" / "zh-tw" — normalize to
# the two-letter bucket used by our pattern modules.
_LANGDETECT_TO_INTERNAL: dict[str, str] = {
    "zh-cn": "zh",
    "zh-tw": "zh",
}


def _normalize_lang(code: str) -> str:
    return _LANGDETECT_TO_INTERNAL.get(code, code)


def detect_primary_language(text: str) -> str:
    """Return the dominant language code for `text`.

    Returns one of `SUPPORTED_LANGUAGES`, or:
      - "mixed" if no single language has ≥70% probability
      - "en" on error (empty input, no features, library crash)

    **Deterministic.** DetectorFactory.seed = 0 at import time.
    Calling with identical input returns identical output across
    interpreter restarts, which matters for test stability and
    for metrics that hash the detected language.
    """
    if not text or not text.strip():
        return "en"
    try:
        langs = detect_langs(text)
    except LangDetectException:
        return "en"
    if not langs:
        return "en"
    primary = _normalize_lang(langs[0].lang)
    if len(langs) > 1 and langs[0].prob < 0.7:
        return "mixed"
    return primary if primary in SUPPORTED_LANGUAGES else "en"


# Sentence splitter. Two alternations:
#   1. After a Latin terminator (.!?) or newline, require whitespace —
#      avoids splitting inside "3.14" or "e.g." mid-word.
#   2. After a CJK full-width terminator (。！？), split unconditionally —
#      CJK prose has no inter-sentence whitespace, so requiring it
#      would silently merge every Chinese/Japanese sentence into one
#      chunk and hide minority languages from per-sentence dispatch.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\n])\s+|(?<=[。！？])")


def split_by_language(text: str) -> list[tuple[str, str]]:
    """Split `text` into `(sentence, language)` pairs.

    Each sentence is classified independently so a mixed-language
    paragraph routes to the right patterns per line. Empty or
    whitespace-only chunks are dropped.

    Caller uses this when `detect_primary_language(text) == "mixed"`
    to fan out to per-language extraction instead of forcing a
    single pattern set onto the whole paragraph.
    """
    if not text:
        return []
    chunks = _SENTENCE_SPLIT_RE.split(text)
    out: list[tuple[str, str]] = []
    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            continue
        out.append((stripped, detect_primary_language(stripped)))
    return out
