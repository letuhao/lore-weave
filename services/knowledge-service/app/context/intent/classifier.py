"""K18.2a — Query intent classifier.

Routes user queries into one of 5 intent classes before L2/L3 selection
runs. Encodes ContextHub lesson L-CH-07: hard query clusters cannot be
fixed by ranking alone — intent must be routed before retrieval.

Pure function, no I/O, no LLM. Target <15ms p95 on messages <500 chars.
Selector code downstream (K18.3) reads IntentResult.hop_count and
recency_weight to pick different Cypher templates and candidate pools.

Priority-order cascade (first match wins, traceable via `signals`):
  1. RELATIONAL       — 2+ named entities + relational keyword
  2. HISTORICAL       — strong past-temporal anchor
  3. RECENT_EVENT     — present/near-past anchor
  4. SPECIFIC_ENTITY  — exactly one named entity, no temporal anchor
  5. GENERAL          — fallback

Limitation: extraction of proper nouns defers to K4.3
`extract_candidates`, which is case-sensitive. Lowercase queries like
"tell me about kai" surface as GENERAL, not SPECIFIC_ENTITY. Fix belongs
in K4.3, not here.

Multilingual routing (A1 / ML-1):
The five keyword regexes are compiled per-language in `app/context/intent/lang/`
(en/zh/ja/ko/vi, unioned — disjoint scripts, so English stays byte-identical).
A zh/ja/ko/vi query now matches its OWN relational/historical/recent vocabulary
and routes through the same priority cascade — real intent, not a blanket
default. A **degrade-net** remains (`_has_non_ascii`): an UNCOVERED non-ASCII
script (ar/th/hi/…) — or a covered-language query with no keyword and no entity
— degrades OPEN to RELATIONAL/2-hop instead of the narrow GENERAL. The net now
sits in place of GENERAL (after SPECIFIC_ENTITY), so a real signal or a named
entity always wins first. English (pure-ASCII) never enters the net.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.context.intent.lang import (
    HISTORICAL_STRONG as _HISTORICAL_STRONG,
    HISTORICAL_WEAK as _HISTORICAL_WEAK,
    RECENT as _RECENT,
    RELATIONAL_KEYWORDS as _RELATIONAL_KEYWORDS,
    RELATIONAL_STRONG as _RELATIONAL_STRONG,
)
from app.context.selectors.glossary import extract_candidates

__all__ = ["Intent", "IntentResult", "classify"]


class Intent(str, Enum):
    SPECIFIC_ENTITY = "specific_entity"
    RECENT_EVENT = "recent_event"
    HISTORICAL = "historical"
    RELATIONAL = "relational"
    GENERAL = "general"


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    entities: tuple[str, ...]
    signals: tuple[str, ...]
    hop_count: int
    recency_weight: float


# The five intent-keyword regexes are compiled per-language in
# app/context/intent/lang/ (en/zh/ja/ko/vi unioned; A1 / ML-1) and imported
# above. English alternatives are byte-identical to the originals, so pure-ASCII
# routing is unchanged; zh/ja/ko/vi queries now match their own vocabulary.

# Sentence-start / interrogative words that extract_candidates (K4.3)
# mis-tags as proper nouns because they happen to be capitalized at
# position 0. Also includes the temporal anchors from the regexes
# above so "Before" / "Long" / "Originally" never survive as an
# "entity" when they're really just part of the temporal phrasing.
_FALSE_POSITIVE_ENTITY_WORDS = frozenset(
    w.lower()
    for w in (
        # Temporal anchors (mirror the regex vocabulary)
        "Before", "After", "Long", "Originally", "Previously",
        "Years", "Chapters", "Earlier", "Recently",
        "Just", "Right", "Currently", "Now",
        # Sentence-start interrogatives / fillers that escape K4.3
        # because K4.3's own stopword list is tuned for mid-sentence
        # use, not position 0.
        "Who", "What", "Where", "When", "Why", "How",
        "Tell", "Describe", "Explain", "Summarize",
        "Are", "Is", "Do", "Did", "Does", "Can", "Should", "Have", "Has",
    )
)


def _is_false_positive_entity(candidate: str) -> bool:
    """True if `candidate` is almost certainly a K4.3 false positive
    (sentence-start capitalized word that is not a real proper noun)."""
    return candidate.lower() in _FALSE_POSITIVE_ENTITY_WORDS


def _has_non_ascii(message: str) -> bool:
    """A non-ASCII *letter* — a CJK / Vietnamese / Korean / … SCRIPT, the signal
    that the English-only regexes above cannot route this query (ML-5 degrade-open
    escape-hatch, mirrors chat-service `entity_presence._has_non_ascii`). Must be
    `.isalpha()`: an em-dash `—`, curly quote, or `…` in an otherwise English
    sentence is non-ASCII PUNCTUATION and must NOT trip the multilingual rule."""
    return any(ord(ch) > 0x7F and ch.isalpha() for ch in message)


def classify(message: str) -> IntentResult:
    """Classify a user message into an Intent.

    Guarantees:
      - Deterministic: same input → same output.
      - No I/O, no network, no LLM.
      - Returns GENERAL on empty/whitespace input.
    """
    if not message or not message.strip():
        return IntentResult(
            intent=Intent.GENERAL,
            entities=(),
            signals=(),
            hop_count=1,
            recency_weight=1.0,
        )

    raw_entities = tuple(extract_candidates(message))
    # K4.3 false-positives sentence-initial capitalized words like
    # "Before", "Long", "Originally" — exactly the words our regexes
    # use as temporal anchors. Filter any entity that collides with a
    # temporal/relational keyword so the priority cascade sees only
    # *real* proper nouns. Otherwise "Before the fall, who ruled?"
    # slips through to SPECIFIC_ENTITY because "Before" is an entity.
    entities = tuple(
        e for e in raw_entities
        if not _is_false_positive_entity(e)
    )
    signals: list[str] = []

    # Record every pattern hit for debuggability — priority cascade
    # below decides which one wins, but we surface all of them so
    # future eval runs can inspect near-misses (L-CH-08: debug
    # counters must not lie).
    historical_strong = _HISTORICAL_STRONG.search(message)
    historical_weak = _HISTORICAL_WEAK.search(message)
    recent = _RECENT.search(message)
    relational_strong = _RELATIONAL_STRONG.search(message)
    relational_kw = _RELATIONAL_KEYWORDS.search(message)

    if historical_strong:
        signals.append(f"historical_strong:{historical_strong.group(0).lower()}")
    if historical_weak:
        signals.append(f"historical_weak:{historical_weak.group(0).lower()}")
    if recent:
        signals.append(f"recent:{recent.group(0).lower()}")
    if relational_strong:
        signals.append(f"relational_strong:{relational_strong.group(0).lower()}")
    if relational_kw:
        signals.append(f"relational_kw:{relational_kw.group(0).lower()}")
    if entities:
        signals.append(f"entities:{len(entities)}")

    # 1. RELATIONAL wins first.
    # Strong phrasing needs ≥1 entity (the other half implied, e.g.
    # "Who knows Kai?") — without any entity, "connection between good
    # and evil" is general philosophy, not a relational graph query.
    # Otherwise need ≥2 entities + a relational keyword so "What does
    # Kai know?" (1 entity + `know`) stays SPECIFIC_ENTITY.
    if (relational_strong and len(entities) >= 1) or (
        len(entities) >= 2 and relational_kw
    ):
        return IntentResult(
            intent=Intent.RELATIONAL,
            entities=entities,
            signals=tuple(signals),
            hop_count=2,
            recency_weight=1.0,
        )

    # 2. HISTORICAL (strong anchor) wins even with entities present.
    if historical_strong:
        return IntentResult(
            intent=Intent.HISTORICAL,
            entities=entities,
            signals=tuple(signals),
            hop_count=1,
            recency_weight=-1.0,
        )

    # 3. RECENT_EVENT — present-tense anchor.
    if recent:
        return IntentResult(
            intent=Intent.RECENT_EVENT,
            entities=entities,
            signals=tuple(signals),
            hop_count=1,
            recency_weight=2.0,
        )

    # 4. HISTORICAL (weak anchor) — only when no entity anchors the query
    # to a specific subject. "Before the battle, what happened?" is
    # historical; "What did Kai do before the battle?" is specific.
    if historical_weak and not entities:
        return IntentResult(
            intent=Intent.HISTORICAL,
            entities=entities,
            signals=tuple(signals),
            hop_count=1,
            recency_weight=-1.0,
        )

    # 5. SPECIFIC_ENTITY — ≥1 named entity, no temporal/relational signal. Runs
    # BEFORE the multilingual net now that zh/ja/ko/vi keywords route via the
    # cascade above: a non-English query with a clear entity ("告诉我关于凯" →
    # tell me about Kai) is SPECIFIC_ENTITY, not hijacked to RELATIONAL.
    if entities:
        return IntentResult(
            intent=Intent.SPECIFIC_ENTITY,
            entities=entities,
            signals=tuple(signals),
            hop_count=1,
            recency_weight=1.0,
        )

    # 5b. Multilingual degrade-net (ML-1 degrade-open). The per-language keyword
    # sets cover en/zh/ja/ko/vi, but an UNCOVERED non-ASCII script (ar/th/hi/…)
    # — or a covered-language query with no keyword + no entity — would otherwise
    # fall to the narrow 1-hop GENERAL. Instead degrade OPEN to RELATIONAL/2-hop
    # so it still gets multi-hop routing. Placed in place of GENERAL (not before
    # SPECIFIC_ENTITY) so real signals win first. English (pure-ASCII) never
    # enters this branch → byte-identical. Shrinks further as keyword coverage grows.
    if _has_non_ascii(message):
        return IntentResult(
            intent=Intent.RELATIONAL,
            entities=entities,
            signals=tuple(signals) + ("multilingual_degrade_open",),
            hop_count=2,
            recency_weight=1.0,
        )

    # 6. GENERAL — fallback.
    return IntentResult(
        intent=Intent.GENERAL,
        entities=entities,
        signals=tuple(signals),
        hop_count=1,
        recency_weight=1.0,
    )
