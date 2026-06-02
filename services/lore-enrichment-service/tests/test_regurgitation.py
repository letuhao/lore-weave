"""Copyright-safety layer ③ — output regurgitation guard (pure detector).

Spec: docs/specs/2026-06-03-copyright-safety-idea-not-derivative.md

Pins the verbatim/near-verbatim overlap detector: an EGREGIOUS contiguous copy
flags HIGH (→ C3 auto-reject), softer overlap flags MEDIUM (advisory), and normal
fact-reuse / shared proper nouns stay clean (no false-positive on legitimate
re-contextualisation).
"""

from __future__ import annotations

from app.verify.regurgitation import (
    LCS_FLAG,
    LCS_REJECT,
    char_ngram_containment,
    detect_regurgitation,
    longest_common_substring_len,
)

# A realistic public-domain-style source excerpt (the seeded 蓬萊 evidence).
SRC = "蓬萊海島，海外仙家之地，僅於斬蛟龍一語中略見其名，自上古即為修真之所。"


def test_lcs_basic():
    assert longest_common_substring_len("", "x") == 0
    assert longest_common_substring_len("abcdef", "zzcdezz") == 3  # "cde"
    assert longest_common_substring_len("蓬萊海島仙家", "海外蓬萊海島之地") == 4  # 蓬萊海島


def test_containment_directional():
    assert char_ngram_containment("", SRC) == 0.0
    assert char_ngram_containment(SRC, SRC) == 1.0  # identical → full containment
    assert char_ngram_containment("完全不同的一段全新文字描述内容", SRC) == 0.0


def test_wholesale_verbatim_copy_is_high():
    # The output is ALMOST ENTIRELY a verbatim copy of the source (a long run covering
    # most of the output) → HIGH (a derivative-work liability) → C3 auto-rejects.
    copied = "此宫之事：" + SRC  # output is ~88% the source sentence verbatim
    res = detect_regurgitation(copied, [SRC])
    assert res.severity == "high" and res.flagged
    assert res.max_lcs >= LCS_REJECT


def test_short_but_complete_copy_is_high():
    # A short output that is the ENTIRE source verbatim is still a wholesale copy
    # (the run covers 100% of the output) → HIGH, even below the overlap-metric's
    # min length (the auto-reject uses the run/length fraction, not n-gram overlap).
    res = detect_regurgitation(SRC, [SRC])
    assert res.severity == "high"


def test_single_copied_sentence_in_original_output_is_advisory_not_high():
    # ④-calibration: ONE copied sentence inside a largely-ORIGINAL output → a long
    # verbatim run (high LCS) but a SMALL fraction of the output → ADVISORY (the human
    # approval gate decides — it may be a legitimate short attributed quote), NOT
    # auto-reject.
    original = (
        "玉虛宮者，東海之上一處仙山也，雲霞繚繞，羽客往還，"
        "層樓疊閣，金玉為階，世人罕至其境，唯傳說中偶見其名，歷代真仙輪值鎮守於此。"
    )  # ~50 chars of fresh prose
    embedded = original + SRC  # SRC (~35 chars) appended → high LCS, small fraction
    res = detect_regurgitation(embedded, [SRC])
    assert res.max_lcs >= LCS_REJECT       # the long verbatim run IS present
    assert res.severity == "medium"        # …but it is NOT most of the output → advisory


def test_moderate_overlap_is_advisory_not_high():
    # A 12–23 char shared run → MEDIUM advisory (human gate), NOT auto-reject.
    partial = "玉虛宮乃" + SRC[:14] + "，另有别说，气象万千，云霞缭绕。"  # ~14-char run
    res = detect_regurgitation(partial, [SRC])
    assert res.severity == "medium"
    assert LCS_FLAG <= res.max_lcs < LCS_REJECT


def test_fresh_expression_with_shared_proper_nouns_is_clean():
    # Legitimate re-contextualisation: shares only the proper noun 蓬萊 + fact-level
    # ideas, but FRESH prose → no substantial verbatim run, low overlap → clean.
    fresh = "蓬萊者，东海之上一处仙山也；云气蒸腾，常有羽客往还，世人罕知其详。"
    res = detect_regurgitation(fresh, [SRC])
    assert res.severity is None and not res.flagged


def test_empty_inputs_are_clean():
    assert detect_regurgitation("", [SRC]).severity is None
    assert detect_regurgitation(SRC, []).severity is None
    assert detect_regurgitation(SRC, ["   "]).severity is None


def test_whitespace_insertion_does_not_evade():
    # An evader spacing out a verbatim copy must still be caught (whitespace is
    # stripped before comparison).
    spaced = " ".join(SRC)  # every char separated by a space
    res = detect_regurgitation(spaced, [SRC])
    assert res.severity == "high"
