"""V3 Verifier — deterministic rule-tier (M1).

Reference-free, high-precision checks over (source, draft) text per block. Quality
GUARANTEES come from these rules + glossary ground-truth, NOT an LLM judge (that is
M2). The checklist is adapted from GalTransl's battle-tested 自動化找錯 and the
design §10 / §2.4.

Pure functions — no I/O. The orchestrator runs this then persists the report.
"""
from __future__ import annotations

import re
from collections import Counter

from ..chunk_splitter import _is_cjk, _SENTENCE_ENDS
from .quality import Issue, IssueReport

_NUM = re.compile(r"\d+")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)  # any unicode "letter" (excl. digits/_/punct)
_CJK_LANGS = frozenset({"zh", "ja", "ko"})
_REPEAT_CAP = 3              # an identical sentence repeated >= this many times = looping
_OMISSION_MIN_SENTENCES = 3  # only judge omission once the source has some structure
_OMISSION_RATIO = 0.6        # draft sentence count below this fraction of source = suspect
# D-V3-TRANSLATION-PROMPT-ECHO: a weak model sometimes COPIES the source under
# [BLOCK N] instead of translating it. Only flag a verbatim echo of a block with
# real translatable content (≥ this many normalized chars + a CJK/letter) so a
# legit pass-through (a number, a symbol, a short proper token) is never churned.
_ECHO_MIN_CHARS = 6


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _is_source_echo(src: str, draft: str) -> bool:
    """The draft is a verbatim copy of the source (untranslated) — high-precision: exact
    after whitespace-normalisation, the source is substantive (≥ _ECHO_MIN_CHARS), and it
    carries a CJK char or a letter (a pure number/symbol block legitimately passes through)."""
    s = _norm(src)
    if len(s) < _ECHO_MIN_CHARS or _norm(draft) != s:
        return False
    return _has_cjk(s) or bool(_LETTER.search(s))


def _lang_is_cjk(code: str) -> bool:
    return (code or "").lower().split("-")[0] in _CJK_LANGS


def _has_cjk(text: str) -> bool:
    return any(_is_cjk(c) for c in text)


def _name_present(name: str, text: str) -> bool:
    """Whole-word-ish presence of a glossary SOURCE name in the source text.

    D-TRANSL-VERIFY-WHOLEWORD (design §10 C.7): a plain ``name in text`` substring
    test made the rule-1 name-compliance check fire spuriously — e.g. "King" inside
    "Kingdom" — which then churned the corrector on a name that was never actually
    present. Non-CJK names now require unicode word boundaries (the match may not be
    flanked by a letter/digit), which kills that class of false positive without any
    new false negatives (a real standalone name still matches).

    CJK names have no whitespace word delimiter, so they keep substring matching
    (paired with the call-site ``len>=2`` guard). Proper CJK morpheme segmentation
    needs a tokenizer this service doesn't run — a documented, narrower limitation
    than the previous all-scripts substring match.
    """
    if not name or not text:
        return False
    if _has_cjk(name):
        return name in text
    # Non-CJK: `[^\W_]` is a unicode letter/digit; the lookarounds forbid the match
    # being part of a longer alphanumeric token (whole-word match, underscore-safe).
    return re.search(rf"(?<![^\W_]){re.escape(name)}(?![^\W_])", text) is not None


def _numbers(text: str) -> list[str]:
    """ASCII digit-runs only (CJK numerals like 三 are intentionally ignored — they
    are routinely rewritten, not dropped)."""
    return sorted(_NUM.findall(text))


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    for ch in text:
        cur.append(ch)
        if ch in _SENTENCE_ENDS:
            s = "".join(cur).strip()
            if s:
                out.append(s)
            cur = []
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


def _looping(text: str) -> bool:
    sents = [s for s in _sentences(text) if len(s) >= 10]
    if not sents:
        return False
    return max(Counter(sents).values()) >= _REPEAT_CAP


def verify_rules(
    source_texts: dict[int, str],
    draft_texts: dict[int, str],
    correction_map: dict[str, str],
    target_lang: str,
) -> IssueReport:
    """Run the deterministic rule-tier over per-block (source, draft) text.

    correction_map: {source_name -> expected target_name} from the glossary
    (build_glossary_context). Empty when there is no glossary (cold start).
    """
    issues: list[Issue] = []
    tgt_cjk = _lang_is_cjk(target_lang)

    for idx, draft in draft_texts.items():
        if not draft or not draft.strip():
            continue
        src = source_texts.get(idx, "")

        # 1. Glossary-name compliance (G3): a glossary source name present in the
        #    source MUST render as its expected target name in the draft.
        for src_name, tgt_name in correction_map.items():
            # len>=2 guard (review-impl MED-1): a single-char source name (e.g. 王)
            # is too often a substring of an unrelated word (国王) → a spurious
            # high-severity flag that M1b would then re-translate on (churn).
            # D-TRANSL-VERIFY-WHOLEWORD: `_name_present` adds unicode word-boundary
            # matching for non-CJK names (the "King" ⊂ "Kingdom" class); CJK keeps
            # substring (no word delimiter) behind the len>=2 guard. `tgt_name not in
            # draft` stays substring on purpose — a whole-word target check would
            # only ADD flags (more churn), and missing a present target is the safe
            # direction here.
            if (src_name and tgt_name and len(src_name) >= 2
                    and _name_present(src_name, src) and tgt_name not in draft):
                issues.append(Issue(
                    idx, "wrong_name", "high",
                    f"'{src_name}' should render as '{tgt_name}'", expected=tgt_name,
                ))

        # 2. Source-script leak: a non-CJK target must not carry CJK characters.
        if not tgt_cjk and _has_cjk(draft):
            issues.append(Issue(
                idx, "untranslated", "high",
                "residual CJK characters in a non-CJK target",
            ))

        # 3. Number preservation: a source number absent from the draft = dropped.
        missing_nums = sorted(set(_numbers(src)) - set(_numbers(draft)))
        if missing_nums:
            issues.append(Issue(
                idx, "number_mismatch", "med",
                f"source numbers missing from draft: {missing_nums}",
            ))

        # 4. Sentence-count omission (coarse completeness signal).
        n_src = len(_sentences(src))
        n_draft = len(_sentences(draft))
        if n_src >= _OMISSION_MIN_SENTENCES and n_draft < _OMISSION_RATIO * n_src:
            issues.append(Issue(
                idx, "omission", "med",
                f"sentence count dropped {n_src} -> {n_draft}",
            ))

        # 5. Repetition / looping.
        if _looping(draft):
            issues.append(Issue(
                idx, "repetition", "high",
                "excessive sentence repetition (model looping)",
            ))

        # 6. Source echo (D-V3-TRANSLATION-PROMPT-ECHO): the model copied the source
        #    verbatim instead of translating. HIGH → the corrector re-translates this
        #    block. Catches echo for ALL target scripts, incl. CJK→CJK where the rule-2
        #    script-leak check can't fire.
        if _is_source_echo(src, draft):
            issues.append(Issue(
                idx, "untranslated", "high",
                "draft is a verbatim copy of the source (untranslated — model echoed)",
            ))

    return IssueReport(issues)
