"""Output regurgitation guard (copyright-safety layer ③) — service-agnostic.

Lifted verbatim from lore-enrichment-service `app/verify/regurgitation.py`
(mui #3 grounding-port consolidation). Copyright protects EXPRESSION, not
facts/ideas — generated output must be FRESH expression, never reproducing the
source's protected prose. Detects substantial verbatim/near-verbatim overlap.
Pure + deterministic + CHARACTER-based (CJK has no word boundaries). No model,
no I/O. Conservative on the AUTO-REJECT side so shared proper nouns / short
idioms never trip it.
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
    "LCS_FRACTION",
    "LCS_FLAG",
    "OVERLAP_FLAG",
    "NGRAM_N",
]

#: Contiguous shared run >= this is PART of the auto-reject test (paired with the
#: fraction below) — long enough that fact-reuse / shared proper nouns never reach it.
LCS_REJECT: int = 24
#: …AND that verbatim run covers >= this FRACTION of the whole output ⟹ auto-reject.
LCS_FRACTION: float = 0.75
#: A contiguous shared run >= this ⟹ ADVISORY (surfaced to the human gate).
LCS_FLAG: int = 12
#: n-gram CONTAINMENT >= this ⟹ ADVISORY near-verbatim paraphrase.
OVERLAP_FLAG: float = 0.40
#: Character shingle size for the containment metric.
NGRAM_N: int = 8
#: The containment metric only applies to content at least this long.
MIN_OVERLAP_LEN: int = 40

#: Whitespace is stripped before comparison; punctuation is KEPT.
_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub("", text or "")


def longest_common_substring_len(a: str, b: str) -> int:
    """Length of the longest CONTIGUOUS substring shared by ``a`` and ``b``.

    Rolling-row DP, O(len(a)·len(b)) time / O(len(b)) space."""
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
    SOURCE — a directional containment. 0.0 when the output is empty."""
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
    ``evidence`` — a short human-readable reason."""

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
    """Compare generated ``content`` against the grounding ``excerpts`` and
    classify the worst overlap.

    EGREGIOUS (``high`` → auto-reject): a contiguous run ≥ :data:`LCS_REJECT`
    covering ≥ :data:`LCS_FRACTION` of the output. ADVISORY (``medium``): a run ≥
    :data:`LCS_FLAG` OR containment ≥ :data:`OVERLAP_FLAG`. Otherwise clean."""
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

    overlap_applies = len(c) >= MIN_OVERLAP_LEN
    lcs_fraction = max_lcs / len(c)
    if max_lcs >= LCS_REJECT and lcs_fraction >= LCS_FRACTION:
        sev: str | None = "high"
        ev = (
            f"输出几乎整体复制授权来源原文表达（最长逐字 {max_lcs} 字，"
            f"占输出 {lcs_fraction:.0%}）— 非再创作，版权风险，自动拒绝"
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
