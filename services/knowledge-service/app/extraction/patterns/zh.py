"""Chinese marker patterns for K15.3 pattern extraction.

Raw regex strings — CJK has no word boundaries (no spaces), so
these are literal substring patterns without `\b`. Compiled with
re.IGNORECASE by the package helper (no-op for CJK). Covers
both Simplified and Traditional where the glyphs coincide.
"""

from __future__ import annotations

DECISION_MARKERS: tuple[str, ...] = (
    r"我们决定",
    r"我们選擇",
    r"决定使用",
    r"改用",
    r"而不是",
    r"选择",
)

PREFERENCE_MARKERS: tuple[str, ...] = (
    r"我喜欢",
    r"我偏好",
    r"总是用",
    r"从不用",
    r"我想要",
    r"我討厭",
)

MILESTONE_MARKERS: tuple[str, ...] = (
    r"可以了",
    r"完成了",
    r"第\s*\d+\s*章完",
    r"终于",
    r"做完了",
    r"搞定",
)

NEGATION_MARKERS: tuple[str, ...] = (
    r"不知道",
    r"没见过",
    r"从未",
    r"不是",
    r"没有",
    r"无法",
)

SKIP_MARKERS: tuple[str, ...] = (
    r"如果",
    r"假如",
    r"假设",
    r"据说",
    r"听说",
    r"也许",
)
