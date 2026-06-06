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
_CJK_LANGS = frozenset({"zh", "ja", "ko"})
_REPEAT_CAP = 3              # an identical sentence repeated >= this many times = looping
_OMISSION_MIN_SENTENCES = 3  # only judge omission once the source has some structure
_OMISSION_RATIO = 0.6        # draft sentence count below this fraction of source = suspect


def _lang_is_cjk(code: str) -> bool:
    return (code or "").lower().split("-")[0] in _CJK_LANGS


def _has_cjk(text: str) -> bool:
    return any(_is_cjk(c) for c in text)


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
            # Whole-word / conditional CJK matching is the proper fix (deferred —
            # ties to the V2 auto_correct substring issue, design §10 C.7).
            if (src_name and tgt_name and len(src_name) >= 2
                    and src_name in src and tgt_name not in draft):
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

    return IssueReport(issues)
