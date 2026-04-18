"""K15.4 — pattern-based SVO triple extractor.

Per KSA §5.1. Pure function, no I/O. Scans text for clean
Subject-Verb-Object sentences and emits quarantine-grade triples
(`confidence=0.5`, `pending_validation=True`) that the K17 LLM
Pass 2 will refine or K18 validator will promote / drop.

**Algorithm:**

  Step 1 — sentence split via K15.3 `split_by_language` (CJK-aware).
  Step 2 — per sentence, skip if any K15.3 SKIP_MARKER fires for
           the detected language. Covers hypothetical / counterfactual
           / reported-speech filtering.
  Step 3 — English SVO regex scan:
             (Subject:capitalized phrase) (verb) (Object:NP)
           Verb forms: past (-ed), plural (-s), gerund (-ing),
           and a small closed list of irregular verbs.
  Step 4 — cross-reference Subject + Object against
           `extract_entity_candidates(sentence)`. A candidate
           must either match an entity surface form OR start with
           a capital letter AND not be a stopword. This rejects
           bare adjective-noun captures and article-only matches.

**English-first scope.** SVO pattern matching is a Latin-script
concept; CJK lacks capital-letter signals and verb inflection.
K15.4 handles non-English text via the skip-marker filter only
(the triple pattern will simply not match CJK sentences). K17
LLM extractor is the multilingual fallback.

**What this module deliberately does NOT do:**
  - Canonicalize subject/object (caller handles via K15.1)
  - Resolve pronouns — "he killed Zhao" falls out because "he" is
    lowercase and rejected by the capitalized-phrase regex
  - Score predicate semantics — K17 LLM does that
  - Write to Neo4j — K15.7

Reference: KSA §5.1, K15.4 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from pydantic import BaseModel, Field

from app.extraction.entity_detector import (
    COMMON_NOUN_STOPWORDS,
    EntityCandidate,
    extract_entity_candidates,
)
from app.extraction.patterns import (
    detect_primary_language,
    get_patterns,
    split_by_language,
)

__all__ = [
    "Triple",
    "extract_triples",
]


# ── Tunables ─────────────────────────────────────────────────────────

# Pattern-based triples land at mid-confidence per the KSA §5.1
# quarantine model — low enough that K18 validator treats them as
# provisional, high enough that a supporting K17 LLM hit can promote.
_QUARANTINE_CONFIDENCE = 0.5

# Auxiliary verbs that must never surface as the predicate of a
# pattern-extracted triple. The generic `[a-z]+s` / `[a-z]+ed`
# alternations in `_VERB` will still match them ("is" matches
# `[a-z]+s`, "had" matches `[a-z]+ed`-ish paths), so a post-match
# rejection is the reliable fence. Pattern path skips these; K17
# LLM handles passive / progressive / perfect tenses. K15.4-R2/I1.
_AUXILIARY_VERBS = frozenset(
    {"is", "was", "were", "are", "has", "have", "had", "did", "do", "does", "be", "been", "being"}
)


# ── Output model ────────────────────────────────────────────────────


class Triple(BaseModel):
    """A single SVO triple surfaced by the pattern detector.

    `subject` and `object_` are display forms (case preserved);
    canonicalization is caller's job at write time. `pending_validation`
    is always True — pattern-based triples never skip quarantine.
    `sentence` preserves the source span for K17 LLM cross-check and
    for the K18 validator's "evidence text" surfacing.
    """

    subject: str
    predicate: str
    object_: str = Field(alias="object")
    confidence: float = Field(ge=0.0, le=1.0)
    pending_validation: bool = True
    sentence: str

    model_config = {"populate_by_name": True}


# ── SVO regex ───────────────────────────────────────────────────────

# Subject: capitalized word or multi-word phrase (same shape as
# `_CAPITALIZED_PHRASE_RE` in entity_detector).
_SUBJ = r"(?P<subj>[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*)"

# Verb: past tense (-ed), 3p singular (-s), gerund (-ing), OR a
# closed list of common irregulars. The `\s+` after demands at
# least one space so "Kai" alone doesn't swallow into verb slot.
# Note: `said` is present because we need to RECOGNIZE it so the
# SVO shape matches; the SKIP_MARKERS filter drops reported speech
# upstream before this regex runs.
# Verb alternation — main verbs only. Auxiliaries (is/was/were/are/
# has/had/did) are deliberately EXCLUDED: they lead passive /
# progressive / perfect constructions where the literal auxiliary
# is not the semantic verb. K15.4-R2/I1 found that accepting "was"
# as a main verb produced `(Kai, was, killed)` from "Kai was killed
# by Drake" — inverting agent and patient. Tense-aware parsing is
# K17 LLM's job; the pattern path just skips these.
_VERB = (
    r"(?P<verb>"
    r"(?:[a-z]+ed|[a-z]+s|[a-z]+ing)"
    # Closed list of common irregular verbs. Keep compact (~40) per
    # KSA coverage policy; K17 LLM catches the rest.
    r"|said|went|came|saw|knew|took|gave|met|told"
    r"|killed|fought|loved|hated|drew|grew|threw|blew|flew|struck"
    r"|made|got|caught|held|led|left|lost|paid|sent"
    r"|set|sat|slept|spoke|stood|taught|thought|wore|wrote|ran"
    r")"
)

# Words that must never START an object NP. Includes conjunctions
# (would fuse two clauses: "Kai walked and Drake followed"),
# prepositions (would fuse adverbial PPs: "walked into the room"),
# and common -ly adverbs (same PP problem: "walked slowly into...").
# Without this gate, intransitive verbs produce confidently-wrong
# triples with adverbial modifiers masquerading as objects.
# K15.4-R1/I1, R1/I2.
_OBJ_STOP_WORDS = (
    "and", "or", "but", "nor", "yet", "so",
    "into", "onto", "upon", "at", "on", "in", "with",
    "from", "to", "by", "for", "of", "about", "through",
    "over", "under", "across", "against", "between", "toward", "towards",
    "slowly", "quickly", "silently", "carefully", "suddenly", "softly",
    "loudly", "calmly", "barely", "hardly", "finally", "already",
)
_OBJ_STOP = r"(?:" + r"|".join(_OBJ_STOP_WORDS) + r")"

# Object: optional article + word phrase (up to 3 tokens). Each
# token position has a negative lookahead rejecting `_OBJ_STOP_WORDS`
# so the object cannot start with or continue past a conjunction /
# preposition / manner adverb.
#
# Note: no IGNORECASE on the compiled pattern — the whole regex must
# treat `[A-Z]` in the subject as strictly uppercase, otherwise
# greedy multi-cap fusion swallows lowercase "is"/"was" into
# the subject capture (e.g. "Kai is fighting" → subj="Kai is").
_OBJ = (
    r"(?P<obj>"
    r"(?:the\s+|a\s+|an\s+)?"
    rf"(?!{_OBJ_STOP}\b)[\w'-]+"
    rf"(?:\s+(?!{_OBJ_STOP}\b)[\w'-]+){{0,2}}"
    r")"
)

_SVO_RE = re.compile(rf"\b{_SUBJ}\s+{_VERB}\s+{_OBJ}\b")

# Post-match filter: object must contain at least one letter and
# must not be a bare stopword / pronoun / article.
_OBJ_STRIP_LEADING_ARTICLE_RE = re.compile(
    r"^(?:the|a|an)\s+", re.IGNORECASE
)


# ── Public API ──────────────────────────────────────────────────────


def extract_triples(
    text: str,
    *,
    glossary_names: Iterable[str] | None = None,
    sentence_candidates: Mapping[str, list[EntityCandidate]] | None = None,
) -> list[Triple]:
    """Scan text for SVO triples with quarantine confidence.

    Args:
        text: raw input — a chat turn, chapter paragraph, etc.
        glossary_names: optional set of known entity display names.
            Forwarded to `extract_entity_candidates` for per-sentence
            entity surface validation of subjects/objects.
        sentence_candidates: **P-K15.8-01** optional pre-built
            per-sentence candidate lookup. When a sentence (verbatim,
            as produced by `split_by_language`) is a key here, the
            entry is reused instead of re-invoking the entity
            detector. Callers that also run `extract_negations` on
            the same text benefit from building this once and
            passing it to both. Absent key → detector fallback.

    Returns:
        List of `Triple`, in first-seen order. Empty input or text
        whose sentences all match SKIP_MARKERS → empty list.
    """
    if not text or not text.strip():
        return []

    glossary_list = list(glossary_names or ())
    sentences = split_by_language(text)
    out: list[Triple] = []

    for sentence, lang in sentences:
        if _is_skippable(sentence, lang):
            continue

        # Entity candidates for this sentence — used to validate
        # subject/object aren't bare common nouns that slipped past
        # the SVO regex's capitalized-phrase gate.
        if sentence_candidates is not None and sentence in sentence_candidates:
            candidates = sentence_candidates[sentence]
        else:
            candidates = extract_entity_candidates(
                sentence, glossary_names=glossary_list
            )
        entity_forms = {c.name.casefold() for c in candidates}

        for match in _SVO_RE.finditer(sentence):
            subj = match.group("subj").strip()
            verb = match.group("verb").strip()
            obj_raw = match.group("obj").strip()
            obj = _OBJ_STRIP_LEADING_ARTICLE_RE.sub("", obj_raw).strip()

            # K15.4-R2/I1: auxiliary verbs leading passive / progressive /
            # perfect constructions would invert agent and patient
            # ("Kai was killed by Drake" → (Kai, was, killed) is wrong).
            # Drop the whole triple; K17 LLM handles these.
            if verb.casefold() in _AUXILIARY_VERBS:
                continue

            if not _is_valid_subject(subj, entity_forms):
                continue
            if not _is_valid_object(obj, entity_forms):
                continue
            if subj.casefold() == obj.casefold():
                # "Kai saw Kai" — self-reference is almost always a
                # regex-fusion artifact ("Kai saw Kai's shadow" split
                # on the apostrophe-s). Drop conservatively.
                continue

            out.append(
                Triple(
                    subject=subj,
                    predicate=verb.lower(),
                    object=obj,
                    confidence=_QUARANTINE_CONFIDENCE,
                    pending_validation=True,
                    sentence=sentence,
                )
            )

    return out


# ── Internal helpers ────────────────────────────────────────────────


def _is_skippable(sentence: str, lang: str) -> bool:
    """True if any SKIP_MARKER for `lang` fires on `sentence`.

    Unsupported language falls back to English patterns via
    `get_patterns`, which is the conservative choice — an English
    "if" filter applied to French prose is a no-op most of the
    time, not a false drop.
    """
    patterns = get_patterns(lang)
    return any(p.search(sentence) for p in patterns.skip)


def _is_valid_subject(subj: str, entity_forms: set[str]) -> bool:
    """Subject must be a real entity candidate or a capitalized
    non-stopword phrase. Rejects bare articles, pronouns, and
    sentence-start capitalization false-positives."""
    folded = subj.casefold()
    if not folded:
        return False
    if folded in COMMON_NOUN_STOPWORDS:
        return False
    if folded in entity_forms:
        return True
    # Fallback: capitalized head + not a stopword. The regex already
    # required a leading capital, so this is a belt-and-braces check.
    return subj[:1].isupper()


def _is_valid_object(obj: str, entity_forms: set[str]) -> bool:
    """Object is more permissive than subject — common nouns are
    legal ("Kai entered the hall"). We only reject empties,
    stopwords, and pure pronouns. `entity_forms` is NOT required
    for objects; many valid SVOs have a common-noun object."""
    folded = obj.casefold()
    if not folded:
        return False
    if folded in COMMON_NOUN_STOPWORDS:
        return False
    # Reject pure pronouns / articles even if they weren't stripped
    # by the leading-article filter above.
    if folded in {"he", "she", "it", "they", "him", "her", "them"}:
        return False
    # Must contain at least one letter (not pure digits / symbols)
    return any(ch.isalpha() for ch in obj)
