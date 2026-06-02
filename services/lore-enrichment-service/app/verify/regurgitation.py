"""Output regurgitation guard (copyright-safety layer ③).

Spec: docs/specs/2026-06-03-copyright-safety-idea-not-derivative.md

Re-cook (and any grounded technique) re-contextualises REAL source material into
the 商周/封神 setting. Copyright protects EXPRESSION, not facts/ideas — so the OUTPUT
must use the uncopyrightable fact layer and be FRESH expression, never reproducing
the source's protected prose (a derivative-work / reproduction liability). The input
license check (default-deny) is the FIRST line; this is the OUTPUT-side complement
courts actually test (substantial similarity): it detects when generated content
reproduces substantial verbatim/near-verbatim expression from the grounding source
— catching LLM memorisation AND a mislabeled-license source the input check trusted.

Pure + deterministic + CHARACTER-based (CJK has no word boundaries). No model, no
I/O, trivially unit-testable. Annotation only — the verifier feeds the result into
a flag; H0 (never writes back / canonises). Conservative on the AUTO-REJECT side so
legitimate fact-reuse + shared proper nouns (玉虛宮/元始天尊) never trip it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

__all__ = [
    "RegurgitationResult",
    "longest_common_substring_len",
    "char_ngram_containment",
    "detect_regurgitation",
    "LCS_REJECT",
    "LCS_FLAG",
    "OVERLAP_FLAG",
    "NGRAM_N",
]

#: A contiguous shared run >= this ⟹ EGREGIOUS verbatim copy (a whole sentence) →
#: auto-reject. High enough that fact-reuse / shared proper nouns never reach it.
LCS_REJECT: int = 24
#: A contiguous shared run >= this ⟹ ADVISORY (surfaced to the human gate, NOT
#: auto-rejected — a re-cook legitimately re-uses some phrasing, esp. from PD).
LCS_FLAG: int = 12
#: n-gram CONTAINMENT (fraction of the output's distinct n-grams found in the
#: source) >= this ⟹ ADVISORY near-verbatim paraphrase.
OVERLAP_FLAG: float = 0.40
#: Character shingle size for the containment metric.
NGRAM_N: int = 8
#: The containment metric only applies to content at least this long — below it a
#: short fact has too few shingles for the ratio to be meaningful (a brief factual
#: statement that happens to be a substring of the source would falsely read as
#: 100% contained). Short content is governed by the verbatim-run (LCS) metric
#: alone, which cannot over-fire on it (a <LCS_FLAG-char fact can't reach the run
#: threshold). Long generated prose (re-cook dimensions are hundreds of chars) is
#: well above this, so the paraphrase signal still works where it matters.
MIN_OVERLAP_LEN: int = 40

#: Whitespace is stripped before comparison (CJK output rarely has spaces; an
#: evader inserting spaces shouldn't dodge the verbatim-run check). Punctuation is
#: KEPT — it is part of the copied expression.
_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub("", text or "")


def longest_common_substring_len(a: str, b: str) -> int:
    """Length of the longest CONTIGUOUS substring shared by ``a`` and ``b``.

    Rolling-row DP, O(len(a)·len(b)) time / O(len(b)) space — the inputs are a
    generated dimension (hundreds of chars) and one source excerpt, so this is
    cheap. The strongest verbatim-copy signal."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, start=1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _shingles(text: str, n: int) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


def char_ngram_containment(output: str, source: str, n: int = NGRAM_N) -> float:
    """Fraction of the OUTPUT's distinct n-char shingles that also appear in the
    SOURCE — a directional containment (how much of the output is found in the
    source), the near-verbatim-paraphrase signal. 0.0 when the output is empty."""
    out_sh = _shingles(output, n)
    if not out_sh:
        return 0.0
    src_sh = _shingles(source, n)
    if not src_sh:
        return 0.0
    return len(out_sh & src_sh) / len(out_sh)


@dataclass(frozen=True)
class RegurgitationResult:
    """The verbatim/near-verbatim overlap of generated content vs the source.

    ``max_lcs``  — longest contiguous shared run (chars) across all excerpts.
    ``overlap``  — max n-gram containment across all excerpts (0..1).
    ``severity`` — ``"high"`` (egregious → auto-reject), ``"medium"`` (advisory), or
                   ``None`` (clean).
    ``flagged``  — severity is not None.
    ``evidence`` — a short human-readable reason (the matched run / overlap %)."""

    max_lcs: int
    overlap: float
    severity: str | None
    evidence: str

    @property
    def flagged(self) -> bool:
        return self.severity is not None


def detect_regurgitation(
    content: str, excerpts: Sequence[str]
) -> RegurgitationResult:
    """Compare generated ``content`` against the grounding ``excerpts`` (the real
    source material) and classify the worst overlap.

    EGREGIOUS (``high`` → auto-reject): a contiguous shared run ≥ :data:`LCS_REJECT`
    (a whole sentence copied verbatim). ADVISORY (``medium`` → human gate): a run ≥
    :data:`LCS_FLAG` OR n-gram containment ≥ :data:`OVERLAP_FLAG`. Otherwise clean.
    Conservative: shared proper nouns / short idioms (2–4 chars) never reach the
    advisory threshold, so normal fact-reuse is not flagged."""
    c = _normalize(content)
    if not c:
        return RegurgitationResult(0, 0.0, None, "")
    max_lcs = 0
    max_overlap = 0.0
    for ex in excerpts:
        e = _normalize(ex)
        if not e:
            continue
        lcs = longest_common_substring_len(c, e)
        if lcs > max_lcs:
            max_lcs = lcs
        ov = char_ngram_containment(c, e)
        if ov > max_overlap:
            max_overlap = ov

    # Containment is only meaningful on long-enough content (a short factual
    # statement that is a substring of the source would falsely read 100%-contained).
    overlap_applies = len(c) >= MIN_OVERLAP_LEN
    if max_lcs >= LCS_REJECT:
        sev: str | None = "high"
        ev = (
            f"输出与授权来源逐字重合 {max_lcs} 字（疑似直接复制原文表达，"
            f"非再创作）— 版权风险，自动拒绝"
        )
    elif max_lcs >= LCS_FLAG or (overlap_applies and max_overlap >= OVERLAP_FLAG):
        sev = "medium"
        ev = (
            f"输出与来源有显著重合（最长逐字 {max_lcs} 字，n-gram 重合 "
            f"{max_overlap:.0%}）— 建议人工复核是否过度借用原文表达"
        )
    else:
        sev = None
        ev = ""
    return RegurgitationResult(max_lcs, round(max_overlap, 3), sev, ev)
