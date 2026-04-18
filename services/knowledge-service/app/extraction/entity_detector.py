"""K15.2 — entity candidate extractor (two-pass, pattern-based).

Port of MemPalace's `entity_detector.py` idea per KSA §5.1. Pure
function, no I/O, no Neo4j. Feeds the Pass 1 quarantine pipeline:
candidate names with confidence scores that K15.7 will write as
`:Entity` nodes with `pending_validation=true`.

**Two-pass algorithm (KSA §5.1):**

  Pass A — candidate collection. Scan text for:
    - Capitalized tokens / phrases (English heuristic)
    - Quoted names ("..." / '...' / curly / CJK 「...」)
    - Exact glossary-name matches (word-bounded, case-insensitive)

  Pass B — signal scoring. For each candidate accumulate:
    - Base confidence (0.30)
    - Source signals (glossary 0.45 / quoted 0.25 / verb-adjacent
      0.15 / bare capitalized 0.10)
    - Frequency bonus (+0.05 per repeat beyond the first, capped
      at 0.20)
    Final confidence = min(1.0, sum of contributions).
    Glossary matches land around 0.95, bare singleton capitalized
    words around 0.40.

**English-first scope.** The capitalized-token heuristic is a Latin-
script concept: CJK has no case, Vietnamese mixes diacritics, and
Arabic has neither. K15.2 handles non-Latin text via the glossary-
match path only. K15.3 per-language pattern sets are the home for
script-specific candidate detectors — do NOT grow this module to
cover them; keep it as the English + glossary baseline.

**What this module deliberately does NOT do:**
  - Canonicalize names — caller does that at write time via
    `entity_canonical_id` (K15.1 / app/db/neo4j_repos/canonical.py)
  - Decide entity `kind` authoritatively — `kind_hint` is a weak
    guess ("character" default). K17 LLM extractor refines.
  - Filter hypothetical / counterfactual sentences — that's the
    caller's job via K15.3 `SKIP_MARKERS` before invoking this.
  - Extract triples / relations / facts — K15.4, K15.5.
  - Write to Neo4j — K15.7.

Reference: KSA §5.1, §5.0, K15.2 plan in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import BaseModel, Field

__all__ = [
    "EntityCandidate",
    "COMMON_NOUN_STOPWORDS",
    "extract_entity_candidates",
]


# ── Tunables (keep conservative per KSA §5.1 quarantine model) ──────

_BASE_CONFIDENCE = 0.30
_WEIGHT_GLOSSARY = 0.45
_WEIGHT_QUOTED = 0.25
_WEIGHT_VERB_ADJACENT = 0.15
_WEIGHT_CAPITALIZED = 0.10
_FREQUENCY_BONUS_PER_REPEAT = 0.05
_FREQUENCY_BONUS_CAP = 0.20


# Common capitalized non-entities. Sentence-start "The", pronouns,
# generic "the character/man/woman" phrases that regex otherwise
# picks up. Exhaustive enough for Track 1; K17 LLM catches anything
# we miss at Pass 2.
COMMON_NOUN_STOPWORDS: frozenset[str] = frozenset(
    word.lower()
    for word in (
        # Articles & determiners at sentence start
        "The", "A", "An", "This", "That", "These", "Those",
        # Pronouns
        "I", "You", "He", "She", "It", "We", "They",
        "Me", "Him", "Her", "Us", "Them",
        "My", "Your", "His", "Hers", "Its", "Our", "Their",
        # Generic referents
        "The Character", "The Man", "The Woman", "The Boy", "The Girl",
        "The King", "The Queen", "The Prince", "The Princess",
        "The Lord", "The Lady", "The Master", "The Servant",
        "The Hero", "The Villain", "The Narrator", "The Author",
        "The Protagonist", "The Antagonist",
        # Common sentence-openers
        "But", "And", "Or", "So", "Yet", "For", "Nor",
        "If", "When", "While", "Because", "Although", "Though",
        "However", "Therefore", "Thus", "Hence", "Moreover",
        # Time / place generic
        "Today", "Tomorrow", "Yesterday", "Now", "Then", "Here", "There",
    )
)


# Capitalized word or phrase: one or more Capitalized tokens in a row.
# `[A-Z][\w'-]*` matches a capitalized token with optional apostrophes
# and hyphens ("O'Neill", "Jean-Luc"). `(?:\s+[A-Z][\w'-]*)*` chains
# multi-word proper nouns ("Commander Zhao", "Water Kingdom").
# We re-scan for shorter prefixes in a second pass so "Commander Zhao"
# and "Zhao" both get counted.
_CAPITALIZED_PHRASE_RE = re.compile(r"\b[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*\b")

# Quoted names — four quote families. The CJK corner brackets 「」
# and full-width quotes “” appear in Japanese/Chinese text; keeping
# them here means glossary-free CJK can still surface quoted names.
_QUOTED_NAME_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r'"([^"\n]{1,64})"'),
    re.compile(r"'([^'\n]{1,64})'"),
    re.compile(r"\u201c([^\u201c\u201d\n]{1,64})\u201d"),  # “ ”
    re.compile(r"\u2018([^\u2018\u2019\n]{1,64})\u2019"),  # ‘ ’
    re.compile(r"\u300c([^\u300c\u300d\n]{1,64})\u300d"),  # 「 」
    re.compile(r"\u300e([^\u300e\u300f\n]{1,64})\u300f"),  # 『 』
)

# Verb-adjacency heuristic. If a capitalized phrase is followed by
# a lowercase verb-ish token ("Kai killed", "Zhao smiled"), that is
# a stronger signal than a bare name floating in isolation. We keep
# this coarse — any lowercase token that looks verb-like ([a-z]+ed,
# [a-z]+s, or a small closed list of irregular verbs).
_VERB_ADJACENT_RE = re.compile(
    r"\b([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*)\s+"
    r"(?:[a-z]+ed|[a-z]+s|[a-z]+ing|"
    r"is|was|were|are|has|had|did|said|went|came|saw|knew|took)\b"
)


# ── Output model ────────────────────────────────────────────────────


class EntityCandidate(BaseModel):
    """A single candidate surfaced by the pattern detector.

    `name` is the original display form (case preserved) — the
    caller is expected to run it through `canonicalize_entity_name`
    at write time. `signals` is kept for debugging / tuning / unit
    tests; downstream writers can ignore it.
    """

    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    kind_hint: str | None = None
    signals: dict[str, float] = Field(default_factory=dict)


# ── Candidate accumulator ───────────────────────────────────────────


class _Accumulator:
    """Per-candidate signal bag during Pass A scanning.

    Keyed by a case-folded normalization of the surface form so
    'Kai' and 'kai' collapse into one row; the first-seen display
    form wins as the `name` field for debugging clarity.

    `counted_spans` deduplicates `bump_count` calls across passes
    by `(start, end)` character offset. Without this, a single
    textual mention that's matched by multiple passes (e.g., a
    glossary name AND the capitalized phrase regex) would inflate
    the frequency counter. K15.2-R2/I1.
    """

    __slots__ = ("display", "signals", "count", "counted_spans")

    def __init__(self, display: str) -> None:
        self.display: str = display
        self.signals: dict[str, float] = {}
        self.count: int = 0
        self.counted_spans: set[tuple[int, int]] = set()

    def add_signal(self, name: str, weight: float) -> None:
        # Take the max if the same signal fires twice (e.g., two
        # quote pairs around the same name — one quoted-signal
        # contribution, not two).
        prev = self.signals.get(name, 0.0)
        if weight > prev:
            self.signals[name] = weight

    def bump_count_for_span(self, span: tuple[int, int]) -> None:
        """Register a textual mention at `span`. Idempotent per
        span — repeated calls with the same span are no-ops, so
        multiple passes over the same mention only count once."""
        if span in self.counted_spans:
            return
        self.counted_spans.add(span)
        self.count += 1


def _fold(name: str) -> str:
    return name.strip().casefold()


def _iter_tokens_if_all_caps_run(
    phrase: str, span: tuple[int, int],
) -> list[tuple[str, tuple[int, int]]]:
    """D-K15.5-01 — split ALL-UPPERCASE multi-token runs.

    Returns the original (phrase, span) untouched unless every token
    in the phrase is all-uppercase AND the phrase has more than one
    token. In that case, returns each token with its absolute offsets
    inside the source text.

    A single-token all-caps match like "NASA" stays as-is — the
    failure mode this fix targets is yelled sentences, not single-
    word acronyms which are typically legitimate proper nouns.
    """
    if " " not in phrase:
        return [(phrase, span)]
    tokens = phrase.split(" ")
    # Require at least one alpha char in each token — a stray hyphen
    # or apostrophe alone shouldn't be called all-upper.
    if not all(
        any(ch.isalpha() for ch in tok) and tok == tok.upper()
        for tok in tokens
    ):
        return [(phrase, span)]

    # Rebuild absolute spans per token by walking the phrase.
    start0 = span[0]
    out: list[tuple[str, tuple[int, int]]] = []
    cursor = 0
    for tok in tokens:
        # Find next occurrence of tok after cursor inside `phrase`.
        # split(" ") on single-space joins guarantees the order and
        # offsets are stable.
        idx = phrase.index(tok, cursor)
        tok_start = start0 + idx
        out.append((tok, (tok_start, tok_start + len(tok))))
        cursor = idx + len(tok)
    return out


# ── Public API ──────────────────────────────────────────────────────


def extract_entity_candidates(
    text: str,
    *,
    glossary_names: Iterable[str] | None = None,
) -> list[EntityCandidate]:
    """Scan text for entity candidates with confidence scores.

    Args:
        text: raw input — a chat turn, chapter paragraph, or
            arbitrary prose. Caller is responsible for any
            hypothetical / counterfactual filtering upstream;
            this function does not inspect sentence modality.
        glossary_names: optional set of known entity display
            names. Exact word-bounded matches (case-insensitive)
            get the highest signal weight, ensuring the
            "scoring ranks glossary matches highest" acceptance
            criterion from K15.2.

    Returns:
        List of `EntityCandidate` sorted by confidence descending,
        then by first-seen position ascending. Candidates whose
        folded form lands in `COMMON_NOUN_STOPWORDS` are dropped.
        Empty input → empty list.
    """
    if not text:
        return []

    # K15.2-R2/I2: glossary iteration must be deterministic. A set
    # would be hash-order iterated, and when two glossary candidates
    # tie on confidence the tie-break falls to `insertion_order`,
    # which would then vary across runs. Sort + dedupe via a list.
    glossary_list: list[str] = sorted({n for n in (glossary_names or ()) if n})
    acc: dict[str, _Accumulator] = {}
    insertion_order: dict[str, int] = {}

    def _get(display: str) -> _Accumulator | None:
        folded = _fold(display)
        if not folded or folded in COMMON_NOUN_STOPWORDS:
            return None
        if folded not in acc:
            acc[folded] = _Accumulator(display)
            insertion_order[folded] = len(insertion_order)
        return acc[folded]

    # Pass A1 — glossary exact matches (highest-weight signal).
    # Run this first so the folded key is seeded by the glossary
    # spelling, not by a downstream regex capture.
    #
    # Boundary class note: we use explicit `[A-Za-z0-9_]` lookarounds
    # rather than `\b` or `(?<!\w)`. Python's `\w` is Unicode-aware,
    # so for a CJK glossary entry like "凯" inside "凯笑了", the
    # lookbehind would see "笑" as a `\w` char and reject every
    # match. Restricting the boundary to ASCII word chars means:
    #   - "Kai" inside "Kairos" → "r" is ASCII-word → rejected (good)
    #   - "凯" inside "凯笑了"   → "笑" is NOT ASCII-word → accepted
    for gname in glossary_list:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(gname)}(?![A-Za-z0-9_])",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            entry = _get(match.group())
            if entry is None:
                continue
            entry.add_signal("glossary", _WEIGHT_GLOSSARY)
            entry.bump_count_for_span(match.span())

    # Pass A2 — quoted names. Strip inner whitespace; reject if the
    # captured group is empty after strip or if it would collide
    # with a stopword.
    #
    # K15.2-R2/I1: bump count here using `bump_count_for_span` on
    # the inner group's span. For Latin quoted names, the capitalized
    # pass will also match the same text and try to bump — the span
    # dedup set absorbs the duplicate. For CJK quoted names, the
    # capitalized pass never matches, so this is the only place
    # their mentions get counted — without this, CJK quoted names
    # would always have count=0 regardless of mention frequency.
    for pattern in _QUOTED_NAME_RES:
        for match in pattern.finditer(text):
            quoted = match.group(1).strip()
            if not quoted:
                continue
            entry = _get(quoted)
            if entry is None:
                continue
            entry.add_signal("quoted", _WEIGHT_QUOTED)
            entry.bump_count_for_span(match.span(1))

    # Pass A3 — capitalized phrases + verb-adjacency scan.
    # We walk two regexes over the same text: `_CAPITALIZED_PHRASE_RE`
    # finds every capitalized phrase for frequency + base signal,
    # then `_VERB_ADJACENT_RE` promotes the subset that precedes a
    # verb-ish token.
    verb_adjacent: set[str] = set()
    for match in _VERB_ADJACENT_RE.finditer(text):
        verb_adjacent.add(_fold(match.group(1)))

    for match in _CAPITALIZED_PHRASE_RE.finditer(text):
        # D-K15.5-01: a match where every token is ALL-uppercase
        # (e.g. "KAI DOES NOT KNOW ZHAO") is almost always a
        # yelled/stylized sentence, not a multi-word proper noun.
        # Fusing the whole span hides real entity boundaries and
        # breaks downstream negation/SVO anchoring. Split such runs
        # into their individual tokens so "KAI" and "ZHAO" each
        # become candidates; stopwords like "DOES", "NOT", "KNOW"
        # fall out via the normal `_get()` filter.
        for sub_phrase, sub_span in _iter_tokens_if_all_caps_run(
            match.group(), match.span(),
        ):
            entry = _get(sub_phrase)
            if entry is None:
                continue
            # K15.2-R1 / R2-I1: `bump_count_for_span` is idempotent
            # per (start, end), so a Latin-script name already counted
            # by the glossary pass or quoted pass is silently ignored
            # here. Replaces the R1 `"glossary" not in signals` gate,
            # which handled glossary overlap but not quoted overlap.
            entry.bump_count_for_span(sub_span)
            entry.add_signal("capitalized", _WEIGHT_CAPITALIZED)
            if _fold(sub_phrase) in verb_adjacent:
                entry.add_signal("verb_adjacent", _WEIGHT_VERB_ADJACENT)

    # Pass B — score + materialize. Drop candidates that collected
    # zero signals (defensive — _get filters stopwords so this is
    # rare, but a zero-signal row could sneak in via a glossary
    # entry whose text match got stopword-folded).
    results: list[tuple[int, EntityCandidate]] = []
    for folded, entry in acc.items():
        if not entry.signals:
            continue
        freq_bonus = min(
            _FREQUENCY_BONUS_CAP,
            max(0, entry.count - 1) * _FREQUENCY_BONUS_PER_REPEAT,
        )
        confidence = min(
            1.0,
            _BASE_CONFIDENCE + sum(entry.signals.values()) + freq_bonus,
        )
        signals = dict(entry.signals)
        if freq_bonus > 0:
            signals["frequency"] = freq_bonus
        candidate = EntityCandidate(
            name=entry.display,
            confidence=round(confidence, 4),
            kind_hint="character",  # weak default; K17 refines
            signals=signals,
        )
        results.append((insertion_order[folded], candidate))

    # Sort by confidence desc, then by first-seen asc (stable).
    results.sort(key=lambda pair: (-pair[1].confidence, pair[0]))
    return [candidate for _, candidate in results]
