"""Korean marker patterns for K15.3 pattern extraction.

Raw regex strings — Korean uses spaces between eojeol but `\b`
is unreliable around Hangul, so patterns are literal substrings.
Compiled with re.IGNORECASE (no-op for Hangul).
"""

from __future__ import annotations

DECISION_MARKERS: tuple[str, ...] = (
    r"결정했다",
    r"쓰기로 했다",
    r"대신에",
    r"바꿨다",
    r"선택했다",
    r"사용하기로",
)

PREFERENCE_MARKERS: tuple[str, ...] = (
    r"좋아한다",
    r"싫어한다",
    r"항상 쓴다",
    r"절대 안 쓴다",
    r"원한다",
    r"선호한다",
)

MILESTONE_MARKERS: tuple[str, ...] = (
    r"작동한다",
    r"완료했다",
    r"끝났다",
    r"제\s*\d+\s*장 완",
    r"드디어",
    r"마침내",
)

NEGATION_MARKERS: tuple[str, ...] = (
    r"모른다",
    r"만난 적 없다",
    r"아니다",
    r"없다",
    r"못한다",
    r"안 된다",
)

SKIP_MARKERS: tuple[str, ...] = (
    r"만약",
    r"가정하면",
    r"아마",
    r"라고 말했다",
    r"한다고 한다",
    r"상상해",
)
