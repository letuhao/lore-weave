"""K15.5 — pattern-based negation fact extractor.

Per KSA §4.2. Pure function, no I/O. Scans text for negation
markers from K15.3 per-language pattern sets and emits
quarantine-grade `NegationFact` records (`confidence=0.5`,
`pending_validation=True`) that will be written as
`:Fact {type: 'negation'}` nodes by K15.7.

**Algorithm:**

  Step 1 — sentence split via K15.3 `split_by_language`.
  Step 2 — per sentence, detect language and fetch its
           `NEGATION_MARKERS` from K15.3.
  Step 3 — scan for any marker hit. On hit, find:
             - Subject: nearest preceding entity candidate whose
               span ends before the marker start.
             - Object:  nearest following entity candidate whose
               span starts after the marker end. Falls back to a
               short trailing NP if no entity found.
  Step 4 — emit `NegationFact`. Skip sentences where no subject
           can be anchored (a bare "is unaware" with no named
           entity nearby is not a useful fact).

**Why anchor on entity candidates.** K15.2 already has robust
entity detection with glossary + capitalized + quoted signals.
Reusing its output means the negation extractor doesn't duplicate
NER logic; it just picks the closest candidate to the marker.

**English-first object fallback.** When no entity follows the
marker (e.g., "Kai does not know the answer"), we capture the
trailing NP via a simple regex — not perfect, but the KSA §4.2
guidance is "80% coverage is fine". K17 LLM refines.

**CJK support.** K15.3 provides CJK negation markers (`不知道`,
`没见过`, etc.) and K15.2 handles CJK via glossary-only. For
mixed-script input, `split_by_language` routes each sentence to
its own pattern set; CJK sentences with no glossary anchors will
silently skip (subject cannot be resolved).

**What this module deliberately does NOT do:**
  - Double-negative handling ("never not knew") — K17 LLM
  - Modal-scoped negation ("would not have known") — filtered
    upstream by SKIP_MARKERS as counterfactual
  - Write to Neo4j — K15.7
  - Fact-type discrimination beyond `type='negation'` — K18

Reference: KSA §4.2, K15.5 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, Field

from app.extraction.entity_detector import (
    EntityCandidate,
    extract_entity_candidates,
)
from app.extraction.patterns import (
    get_patterns,
    split_by_language,
)

__all__ = [
    "NegationFact",
    "extract_negations",
]


# ── Tunables ─────────────────────────────────────────────────────────

_QUARANTINE_CONFIDENCE = 0.5

# Stop-words the trailing-NP fallback must not enter. Mirrors K15.4
# `_OBJ_STOP_WORDS`: conjunctions fuse clauses, prepositions fuse
# adverbial PPs, manner adverbs fuse the PP that follows them.
# K15.5-R1/I1: probe `"Kai does not know the answer of the riddle"`
# captured `"answer of the"`, and `"is unaware of the plot"` captured
# a pure PP as object. Same negative-lookahead gate fixes both.
_NP_STOP_WORDS = (
    "and", "or", "but", "nor", "yet", "so",
    "into", "onto", "upon", "at", "on", "in", "with",
    "from", "to", "by", "for", "of", "about", "through",
    "over", "under", "across", "against", "between", "toward", "towards",
    "slowly", "quickly", "silently", "carefully", "suddenly", "softly",
    "loudly", "calmly", "barely", "hardly", "finally", "already",
)
_NP_STOP = r"(?:" + r"|".join(_NP_STOP_WORDS) + r")"

# Trailing-NP fallback for the object slot when no entity candidate
# follows the negation marker. Captures up to 3 word tokens,
# optionally preceded by an article, rejecting any token that starts
# with a stop-word (conjunction / preposition / manner adverb).
_TRAILING_NP_RE = re.compile(
    r"(?:the\s+|a\s+|an\s+)?"
    rf"((?!{_NP_STOP}\b)[\w'-]+"
    rf"(?:\s+(?!{_NP_STOP}\b)[\w'-]+){{0,2}})"
)


# ── Output model ────────────────────────────────────────────────────


class NegationFact(BaseModel):
    """A single negation fact surfaced by the pattern detector.

    `subject` and `object_` are display forms (case preserved);
    canonicalization is caller's job at write time. `marker` is
    the exact negation phrase that fired, kept for debugging and
    K17 LLM cross-check. `fact_type` is always "negation" — the
    field exists so the downstream K15.7 writer can dispatch to
    the right `:Fact` kind.
    """

    subject: str
    marker: str
    object_: str | None = Field(default=None, alias="object")
    confidence: float = Field(ge=0.0, le=1.0)
    pending_validation: bool = True
    fact_type: str = "negation"
    sentence: str

    model_config = {"populate_by_name": True}


# ── Public API ──────────────────────────────────────────────────────


def extract_negations(
    text: str,
    *,
    glossary_names: Iterable[str] | None = None,
    sentence_candidates: Mapping[str, list[EntityCandidate]] | None = None,
) -> list[NegationFact]:
    """Scan text for negation facts with quarantine confidence.

    Args:
        text: raw input — a chat turn, chapter paragraph, etc.
        glossary_names: optional known entity display names, forwarded
            to `extract_entity_candidates` for per-sentence anchoring.
        sentence_candidates: **P-K15.8-01** optional pre-built
            per-sentence candidate lookup. When a sentence (verbatim,
            as produced by `split_by_language`) is a key here, the
            entry is reused instead of re-invoking the entity
            detector. Paired with the identical parameter on
            `extract_triples` so orchestrators build the map once
            per text body.

    Returns:
        List of `NegationFact` in first-seen order. Sentences where
        no negation marker fires, or where no subject can be anchored,
        are silently skipped. Empty input → empty list.
    """
    if not text or not text.strip():
        return []

    glossary_list = list(glossary_names or ())
    sentences = split_by_language(text)
    out: list[NegationFact] = []

    for sentence, lang in sentences:
        patterns = get_patterns(lang)
        if not patterns.negation:
            continue

        # Collect every negation marker hit in this sentence.
        marker_hits: list[tuple[int, int, str]] = []
        for pattern in patterns.negation:
            for match in pattern.finditer(sentence):
                marker_hits.append((match.start(), match.end(), match.group()))

        if not marker_hits:
            continue

        # Entity candidates once per sentence — anchors for subject/object.
        if sentence_candidates is not None and sentence in sentence_candidates:
            candidates = sentence_candidates[sentence]
        else:
            candidates = extract_entity_candidates(
                sentence, glossary_names=glossary_list
            )
        candidate_spans = _entity_spans(sentence, candidates)

        for m_start, m_end, marker_text in marker_hits:
            subject = _nearest_preceding_entity(candidate_spans, m_start)
            if subject is None:
                # No anchorable subject → skip. A bare "is unaware"
                # with no named entity is not a useful fact.
                continue

            obj = _nearest_following_entity(candidate_spans, m_end)
            if obj is None:
                obj = _fallback_trailing_np(sentence, m_end)

            out.append(
                NegationFact(
                    subject=subject,
                    marker=marker_text.strip(),
                    object=obj,
                    confidence=_QUARANTINE_CONFIDENCE,
                    pending_validation=True,
                    sentence=sentence,
                )
            )

    return out


# ── Internal helpers ────────────────────────────────────────────────


def _entity_spans(
    sentence: str, candidates: list[EntityCandidate]
) -> list[tuple[int, int, str]]:
    """Map each EntityCandidate to its first occurrence span in
    `sentence`. K15.2 returns candidates without span info, so we
    re-locate each by case-insensitive substring search. Multiple
    mentions of the same candidate get one span (the first).

    Returns spans sorted by start offset — callers walk this list
    directionally to find nearest-before / nearest-after.
    """
    spans: list[tuple[int, int, str]] = []
    lower = sentence.casefold()
    for cand in candidates:
        needle = cand.name.casefold()
        if not needle:
            continue
        idx = lower.find(needle)
        if idx < 0:
            continue
        spans.append((idx, idx + len(needle), cand.name))
    spans.sort(key=lambda s: s[0])
    return spans


def _nearest_preceding_entity(
    spans: list[tuple[int, int, str]], cutoff: int
) -> str | None:
    """Return the display name of the entity whose span ends at or
    before `cutoff`, preferring the latest (nearest to cutoff)."""
    best: str | None = None
    for _, end, name in spans:
        if end <= cutoff:
            best = name
        else:
            break
    return best


def _nearest_following_entity(
    spans: list[tuple[int, int, str]], cutoff: int
) -> str | None:
    """Return the display name of the first entity whose span
    starts at or after `cutoff`."""
    for start, _, name in spans:
        if start >= cutoff:
            return name
    return None


def _fallback_trailing_np(sentence: str, start: int) -> str | None:
    """Grab a short NP immediately after the negation marker when
    no entity candidate follows. Returns None if the tail is empty
    or contains no letter-like tokens.
    """
    tail = sentence[start:].lstrip()
    if not tail:
        return None
    match = _TRAILING_NP_RE.match(tail)
    if match is None:
        return None
    np = match.group(1).strip().rstrip(".,;:!?")
    return np or None
