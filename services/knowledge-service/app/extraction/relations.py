"""D-ML-TRIPLE-SVO-SCRIPT — per-language relation-marker triple extraction.

The K15.4 SVO regex (triple_extractor.py) is English-only: it keys on capitalized
subjects + English verb morphology (`[a-z]+ed/-s/-ing`) in strict S-V-O order, so
it yields nothing for zh/ja/ko/vi. This module is the degrade-open complement: a
**high-precision, closed-lexicon** relation extractor that mirrors negation.py —
anchor on entity candidates (script-aware since A2), match an explicit relation
marker, and assign roles by word order.

It is NOT a parser. It emits a triple ONLY when two distinct entity candidates
anchor the relation, so recall is deliberately low and precision high — a
quarantine-grade PRE-SEED (confidence 0.5, pending_validation=True) that lets the
K17 LLM lean on cheap anchors (less LLM work per non-English chapter). Precision
is HIGH, not perfect: a bare keyword can still hit a lexical-ambiguity compound
(vi "yêu cầu"=request vs "yêu"=love — guarded; others exist). That's why triples
stay quarantine-grade — the K17 LLM / K18 validator refine or drop them; the
extractor's job is to avoid the *common* false positive, not every one.

Recall note: role anchoring prefers glossary-backed entities, so coverage is
strongest once the book's glossary is populated; a glossary-free CJK sentence
whose whole run is one span yields no triple (degrade-open).

Word order:
  • SVO (zh, vi) — subject before the marker, object after.
  • SOV (ja, ko) — verb-marker trails both entities; subject = first entity, object
    = the entity nearest the verb (the object slot in `…がAをKILLED`).

Predicates are normalized English verbs (knows/met/killed/…), quarantine-grade —
the K18 validator maps them into the canonical predicate vocabulary, exactly as the
English pattern path emits a raw `verb.lower()`.
"""

from __future__ import annotations

import re

from app.extraction.entity_detector import EntityCandidate
from app.extraction.scripts import HAN, HANGUL, HIRAGANA, KATAKANA

__all__ = ["extract_relation_triples", "RELATION_LANGS"]


# Languages with a relation lexicon (English uses the SVO regex instead).
RELATION_LANGS: frozenset[str] = frozenset({"zh", "ja", "ko", "vi"})
_SOV_LANGS: frozenset[str] = frozenset({"ja", "ko"})

# The SVO-vs-SOV decision must NOT trust langdetect: it confuses CJK on short /
# kanji-heavy input (verified: a Chinese sentence detects as "ko", a kanji-only
# Japanese one as "zh"), which would apply SVO role order to an SOV sentence and
# INVERT subject/object. Script presence is a far stronger signal — kana ⇒ ja,
# hangul ⇒ ko — so we override the lexicon+order by script when it's unambiguous.
_KANA_RE = re.compile(f"[{HIRAGANA}{KATAKANA}]")
_HANGUL_RE = re.compile(f"[{HANGUL}]")
_HAN_RE = re.compile(f"[{HAN}]")


def _effective_lang(sentence: str, lang: str) -> str:
    """Correct the lexicon/word-order language by script (langdetect is
    unreliable for CJK). Any kana ⇒ ja; any hangul ⇒ ko; Han-only (no kana/
    hangul) ⇒ zh — the safe majority, since Han-only text is far more likely
    Chinese than the vanishingly rare kana-free Japanese, and this rescues a
    Chinese sentence that langdetect mislabeled ko/en. No CJK script (e.g. vi
    Latin) ⇒ trust the detected lang."""
    if _KANA_RE.search(sentence):
        return "ja"
    if _HANGUL_RE.search(sentence):
        return "ko"
    if _HAN_RE.search(sentence):
        return "zh"
    return lang


def _c(*pairs: tuple[str, str]) -> tuple[tuple[re.Pattern[str], str], ...]:
    """Compile (marker-regex, predicate) pairs. IGNORECASE is a no-op for CJK
    and correct for vi Latin."""
    return tuple((re.compile(p, re.IGNORECASE), pred) for p, pred in pairs)


# Closed, high-precision relation lexicons. Simplified + Traditional where glyphs
# differ (mirrors patterns/zh.py). Keep compact — the LLM catches the long tail.
_RELATIONS: dict[str, tuple[tuple[re.Pattern[str], str], ...]] = {
    "zh": _c(
        (r"认识|認識", "knows"),
        (r"遇见|遇見|见到|見到|遇到", "met"),
        (r"杀了|杀死|殺了|殺死", "killed"),
        (r"爱上|爱着|愛上|愛著|爱|愛", "loves"),
        (r"恨", "hates"),
        (r"背叛", "betrayed"),
        (r"救了|救出|拯救", "saved"),
        (r"保护|保護", "protects"),
        (r"效忠|服侍|侍奉", "serves"),
        (r"帮助|幫助", "helps"),
    ),
    "vi": _c(
        (r"quen biết|biết", "knows"),
        (r"gặp gỡ|gặp", "met"),
        (r"giết chết|giết", "killed"),
        # "yêu" = love, but "yêu cầu" = request — exclude the common compound so
        # "Nguyễn yêu cầu Trần" doesn't become (loves). A bare keyword lexicon
        # can't catch every lexical ambiguity; the K17 LLM refines the rest.
        (r"yêu(?!\s+cầu)", "loves"),
        (r"ghét|căm ghét", "hates"),
        (r"phản bội", "betrayed"),
        (r"cứu", "saved"),
        (r"bảo vệ", "protects"),
        (r"phục vụ|phò tá", "serves"),
        (r"giúp đỡ|giúp", "helps"),
    ),
    "ja": _c(
        (r"を知って|と知り合", "knows"),
        (r"に会った|と出会った|に出会った", "met"),
        (r"を殺した|を殺して", "killed"),
        (r"を愛して|に恋", "loves"),
        (r"を憎んで|を恨んで", "hates"),
        (r"を裏切った|を裏切って", "betrayed"),
        (r"を救った|を助けた", "saved"),
        (r"を守った|を守って", "protects"),
        (r"に仕えて|に仕えた", "serves"),
    ),
    "ko": _c(
        (r"알고 있|아는|안다", "knows"),
        (r"만났|만나서|마주쳤", "met"),
        (r"죽였|죽이고", "killed"),
        (r"사랑", "loves"),
        (r"미워|증오", "hates"),
        (r"배신", "betrayed"),
        (r"구했|구출", "saved"),
        (r"지켰|보호", "protects"),
        (r"섬겼|모셨", "serves"),
    ),
}


def _entity_spans(sentence: str, candidates: list[EntityCandidate]) -> list[tuple[int, int, str]]:
    """De-noised, non-overlapping entity spans, sorted by start offset.

    Segmenter-less CJK candidate extraction is noisy — for "김철수가 이영희를
    구했다" it surfaces the josa-suffixed runs "김철수가"/"이영희를" AND the verb
    run "구했다" alongside the glossary names. So we DEDUP overlapping spans,
    preferring a glossary-backed candidate, then the shorter surface (the
    josa-stripped/cleaner form), and drop the rest. This keeps one clean
    representative per region so a verb run can't land in a role slot."""
    raw: list[tuple[int, int, str, bool]] = []  # (start, end, name, is_glossary)
    lower = sentence.casefold()
    for cand in candidates:
        needle = cand.name.casefold()
        if not needle:
            continue
        idx = lower.find(needle)
        if idx < 0:
            continue
        raw.append((idx, idx + len(needle), cand.name, "glossary" in cand.signals))
    # Best-first: glossary before non-glossary, then shorter before longer.
    raw.sort(key=lambda s: (not s[3], s[1] - s[0]))
    kept: list[tuple[int, int, str]] = []
    for start, end, name, _ in raw:
        if any(start < ke and se < end for se, ke, _ in kept):  # overlaps a kept span
            continue
        kept.append((start, end, name))
    kept.sort(key=lambda s: s[0])
    return kept


def extract_relation_triples(
    sentence: str,
    lang: str,
    candidates: list[EntityCandidate],
) -> list[tuple[str, str, str]]:
    """Return (subject, predicate, object) triples for one sentence, or [].

    Emits only when two DISTINCT entity candidates anchor a relation marker —
    high precision, degrade-open (no anchors ⇒ no triple, never a wrong one).
    """
    lang = _effective_lang(sentence, lang)
    markers = _RELATIONS.get(lang)
    if not markers:
        return []
    spans = _entity_spans(sentence, candidates)
    if len(spans) < 2:
        return []

    sov = lang in _SOV_LANGS
    seen: set[tuple[str, str, str]] = set()
    out: list[tuple[str, str, str]] = []

    for pattern, predicate in markers:
        for m in pattern.finditer(sentence):
            subj: str | None = None
            obj: str | None = None
            if sov:
                # Verb trails both entities. Entities STRICTLY before the verb
                # (end ≤ marker start — excludes the verb run itself); subject is
                # the earliest, object the one nearest the verb (…がAをVERB).
                before = [s for s in spans if s[1] <= m.start()]
                if len(before) >= 2:
                    subj = before[0][2]
                    obj = before[-1][2]
            else:
                # SVO: subject before the marker, object after.
                preceding = [s for s in spans if s[1] <= m.start()]
                following = [s for s in spans if s[0] >= m.end()]
                if preceding and following:
                    subj = preceding[-1][2]
                    obj = following[0][2]
            if not subj or not obj or subj.casefold() == obj.casefold():
                continue
            triple = (subj, predicate, obj)
            if triple in seen:
                continue
            seen.add(triple)
            out.append(triple)

    return out
