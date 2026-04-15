"""Vietnamese marker patterns for K15.3 pattern extraction.

Raw regex strings — compiled with re.IGNORECASE by the package
`_compile_all` helper. Latin script with diacritics; `\b` word
boundaries work since Vietnamese uses spaces.
"""

from __future__ import annotations

DECISION_MARKERS: tuple[str, ...] = (
    r"\bchúng ta dùng\b",
    r"\bquyết định\b",
    r"\bchọn\b",
    r"\bthay vì\b",
    r"\bđổi sang\b",
    r"\bsẽ dùng\b",
)

PREFERENCE_MARKERS: tuple[str, ...] = (
    r"\btôi thích\b",
    r"\btôi muốn\b",
    r"\bluôn dùng\b",
    r"\bkhông bao giờ dùng\b",
    r"\bưa thích\b",
    r"\bghét\b",
)

MILESTONE_MARKERS: tuple[str, ...] = (
    r"\bhoạt động\b",
    r"\bxong\b",
    r"\bhoàn thành\b",
    r"\bkết thúc chương\s+\d+\b",
    r"\bcuối cùng\b",
    r"\bđã xong\b",
)

NEGATION_MARKERS: tuple[str, ...] = (
    r"\bkhông biết\b",
    r"\bchưa gặp\b",
    r"\bkhông hề\b",
    r"\bchưa bao giờ\b",
    r"\bkhông phải\b",
    r"\bkhông thể\b",
)

SKIP_MARKERS: tuple[str, ...] = (
    r"\bnếu\b",
    r"\bgiả sử\b",
    r"\bcó lẽ\b",
    r"\bnói rằng\b",
    r"\btưởng tượng\b",
    r"\bcho là\b",
)
