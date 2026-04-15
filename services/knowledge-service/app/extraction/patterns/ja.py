"""Japanese marker patterns for K15.3 pattern extraction.

Raw regex strings — Japanese mixes kanji/hiragana/katakana with no
word boundaries. Patterns are literal substrings. Compiled with
re.IGNORECASE (no-op for kana/kanji).
"""

from __future__ import annotations

DECISION_MARKERS: tuple[str, ...] = (
    r"決めた",
    r"決定した",
    r"使うことにした",
    r"ではなく",
    r"に変えた",
    r"選んだ",
)

PREFERENCE_MARKERS: tuple[str, ...] = (
    r"好き",
    r"嫌い",
    r"いつも使う",
    r"絶対に使わない",
    r"欲しい",
    r"好む",
)

MILESTONE_MARKERS: tuple[str, ...] = (
    r"できた",
    r"完成した",
    r"終わった",
    r"第\s*\d+\s*章完",
    r"ついに",
    r"やっと",
)

NEGATION_MARKERS: tuple[str, ...] = (
    r"知らない",
    r"会ったことがない",
    r"ではない",
    r"わからない",
    r"できない",
    r"ありません",
)

SKIP_MARKERS: tuple[str, ...] = (
    r"もし",
    r"仮に",
    r"たとえば",
    r"と言った",
    r"らしい",
    r"そうだ",
)
