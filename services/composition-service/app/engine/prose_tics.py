"""T17 — deterministic detection of repetitive prose constructions ("tics").

WHY THIS EXISTS. A 2026-09-06 human-sim run reviewed five chapters through a four-lens Workflow.
Three of the four recurring defects closed reliably when the model was asked to fix them. The
fourth did not: the ``không phải X, mà là Y`` antithesis and ``sự``-stacked abstract nouns survived <!-- doc-language-gate: ok -- the Vietnamese construction is the literal subject here -- it is the pattern this module detects, and naming it in English would not identify what it matches -->
two independent, increasingly specific correction attempts — and the second attempt reproduced the
exact flagged construction *inside brand-new content written to remove it*. That is strong evidence
it is not addressable by instructing the writer model, and the run's report recorded it as the one
demonstrated limit of its review-and-revise loop.

WHY DETERMINISTIC, AND NOT A JUDGE PROMPT. ``critic.py``'s own header records the reason: its rubric
deliberately avoids English illustrative phrases because *"those bias a CJK/VN judge to English"*.
A tic detector needs to quote the exact construction in the target language, which is precisely the
input that biases the judge. A regex has no such failure mode, costs nothing, returns positions, and
— unlike a judge — can be proven to fire on the construction and NOT on ordinary prose.

WHY DENSITY AND NOT PRESENCE, which is the whole difficulty. ``sự`` is an ordinary, high-frequency <!-- doc-language-gate: ok -- the Vietnamese construction is the literal subject here -- it is the pattern this module detects, and naming it in English would not identify what it matches -->
Vietnamese word; ``không phải … mà là`` is a perfectly good sentence a careful author writes on <!-- doc-language-gate: ok -- the Vietnamese construction is the literal subject here -- it is the pattern this module detects, and naming it in English would not identify what it matches -->
purpose. A detector that fired on every occurrence would flag all Vietnamese prose ever written and
would therefore tell a reader nothing (NV-7 — "the check fires on EVERYTHING, so firing means
nothing"). What the run actually observed was a RATE: the construction appearing in all five scenes
of a chapter, several times per scene. So the rules measure occurrences per 1000 words against a
threshold, and the threshold is the claim.

SCOPE IS DECLARED, NOT ASSUMED. Per the multilingual standard, a Vietnamese pattern must not sit in
a language-agnostic path pretending to be universal. ``COVERED_LANGUAGES`` says exactly which
languages have rules; every other language returns no findings and says why, rather than silently
reporting clean prose it never examined.
"""
# doc-language-gate: ok -- the Vietnamese constructions ARE this module's subject: they are the literal patterns it detects, so paraphrasing them into English would destroy the specification and the tests. Scoped to this file.

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.engine.finding import Locator

#: Languages with a rule set. Anything else is NOT analysed — and reports that, rather than
#: returning an empty finding list a caller would read as "clean".
COVERED_LANGUAGES: frozenset[str] = frozenset({"vi"})


@dataclass(frozen=True)
class TicFinding:
    """One construction, with enough detail for a human to check the call."""

    rule: str
    #: Occurrences found.
    count: int
    #: Occurrences per 1000 words — the number the threshold is applied to.
    per_1000: float
    #: The rate above which this rule reports. Included so a reader can judge the JUDGEMENT.
    threshold_per_1000: float
    #: A few verbatim excerpts, so the finding can be verified rather than trusted.
    examples: tuple[str, ...]
    #: Character offsets of the FIRST occurrence in the analysed text. The repo's finding-locator
    #: gate caught this class carrying a finding it could not place — and it was right: the
    #: detector already had every match position and was discarding them, so a reader was handed
    #: a rate and told to go looking. `(0, 0)` only when no span was recorded.
    first_span: tuple[int, int] = (0, 0)

    @property
    def locator(self) -> Locator:
        """WHERE this tic is — the first occurrence, so a reader can jump straight to it.

        A rate is a claim about a whole passage, but a rate alone is not actionable: the author
        has to find an instance before they can judge it. `Locator.nowhere` is reserved for the
        case nothing could be placed, which for a regex over its own input should not happen.
        """
        start, end = self.first_span
        if end > start:
            return Locator.span(start, end, quote=self.examples[0] if self.examples else "")
        return Locator.nowhere(
            quote=self.examples[0] if self.examples else "",
            why="no span recorded for this occurrence",
        )

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "count": self.count,
            "per_1000": round(self.per_1000, 2),
            "threshold_per_1000": self.threshold_per_1000,
            "examples": list(self.examples),
            "locator": self.locator.describe() if hasattr(self.locator, "describe")
            else {"start": self.first_span[0], "end": self.first_span[1]},
        }


@dataclass(frozen=True)
class TicReport:
    language: str
    analysed: bool
    words: int
    findings: tuple[TicFinding, ...]
    #: Why nothing was analysed, when `analysed` is False. Never silent.
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "analysed": self.analysed,
            "words": self.words,
            "findings": [f.as_dict() for f in self.findings],
            "reason": self.reason,
        }


# ── Vietnamese ───────────────────────────────────────────────────────────────
#
# Thresholds are set from the measured run, not invented. The chapter the report called the
# DOMINANT case carried the antithesis in 5 of 5 scenes at roughly 1700 words — several per
# thousand. Ordinary prose uses the construction occasionally and must not be flagged, so the
# thresholds sit above "an author used this deliberately" and below "this is a verbal habit".

#: "không phải X, mà là Y" and its close variants ("chẳng phải …, mà là …", "… mà là" with an
#: intervening clause). The bounded gap matters: unbounded, it would join two unrelated sentences
#: a paragraph apart and manufacture matches.
_VI_ANTITHESIS = re.compile(
    r"(?:không|chẳng)\s+phải\b[^.!?;]{0,120}?,?\s*mà\s+(?:là|chỉ|còn)\b",
    re.IGNORECASE,
)

#: "sự " + a following word — Vietnamese abstract-noun formation. Individually unremarkable;
#: stacked, it is the flattening the report describes. Rate-judged for exactly that reason.
#:
#: `[^\W\d_]` rather than `\p{L}`: Python's `re` has no Unicode property escapes, and the
#: double-negative class is the standard equivalent — any character that is alphanumeric but
#: neither a digit nor an underscore, i.e. a letter, with `re.UNICODE` making that include
#: Vietnamese diacritics.
_VI_ABSTRACT_NOUN = re.compile(r"\bsự\s+[^\W\d_]+", re.IGNORECASE | re.UNICODE)

#: (rule id, pattern, occurrences-per-1000-words ABOVE which it reports)
#:
#: CALIBRATION, and it is a judgement the tests pin from both sides. The antithesis threshold
#: started at 1.5 and was WRONG: a single deliberate use in a 440-word passage is 2.3 per 1000, so
#: 1.5 punished an author for writing one good sentence. `test_occasional_deliberate_use_is_NOT_flagged`
#: caught it before commit. 4.0 means roughly seven occurrences in a 1700-word chapter — the
#: measured shape of the run's dominant case (the construction in 5 of 5 scenes, several per scene)
#: and far above anything a deliberate stylistic choice produces.
#:
#: These numbers are the claim. Moving one is a product judgement about where habit begins, and
#: both tests should move with it.
_VI_RULES: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("vi.antithesis_khong_phai_ma_la", _VI_ANTITHESIS, 4.0),
    ("vi.abstract_noun_su_stacking", _VI_ABSTRACT_NOUN, 12.0),
)

_RULES_BY_LANGUAGE: dict[str, tuple[tuple[str, re.Pattern[str], float], ...]] = {
    "vi": _VI_RULES,
}


def _word_count(text: str) -> int:
    """Vietnamese is space-separated, so `split()` is right for every covered language today.

    Deliberately NOT generalised to spaceless scripts: `COVERED_LANGUAGES` has no such language,
    and writing an unused CJK branch here would be a claim of coverage that no test exercises.
    """
    return len(text.split())


def detect_prose_tics(text: str, language: str | None) -> TicReport:
    """Rate-judge `text` against the rule set for `language`.

    Returns a report that always states whether it actually analysed anything. A caller must be
    able to tell "no tics found" from "this language has no rules" — conflating them is the same
    silent-empty-result defect this remediation exists to close.
    """
    lang = (language or "").lower().split("-")[0]
    body = (text or "").strip()
    words = _word_count(body)

    if lang not in COVERED_LANGUAGES:
        return TicReport(
            language=lang, analysed=False, words=words, findings=(),
            reason=(
                f"no tic rules for language {lang!r}; "
                f"covered: {', '.join(sorted(COVERED_LANGUAGES))}"
            ),
        )
    if words < 100:
        # A rate over a handful of words is noise: one occurrence in 40 words is 25 per 1000.
        return TicReport(
            language=lang, analysed=False, words=words, findings=(),
            reason=f"passage too short to rate ({words} words; 100 needed)",
        )

    # NFC first: Vietnamese is routinely stored in either normalisation form, and a decomposed
    # "sự" would not match a composed pattern — a detector that silently misses half its corpus.
    body = unicodedata.normalize("NFC", body)

    findings: list[TicFinding] = []
    for rule_id, pattern, threshold in _RULES_BY_LANGUAGE[lang]:
        hits = list(pattern.finditer(body))
        if not hits:
            continue
        matches = [m.group(0).strip() for m in hits]
        per_1000 = len(matches) * 1000.0 / words
        if per_1000 <= threshold:
            continue
        findings.append(TicFinding(
            rule=rule_id,
            count=len(matches),
            per_1000=per_1000,
            threshold_per_1000=threshold,
            examples=tuple(matches[:5]),
            first_span=(hits[0].start(), hits[0].end()),
        ))
    return TicReport(language=lang, analysed=True, words=words, findings=tuple(findings))

# doc-language-gate: end
