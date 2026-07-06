"""Vietnamese (vi) intent keywords. Latin script (spaced) ⇒ `\\b`-bounded by the
registry, like English. Alternation bodies (lowercase; the compile is IGNORECASE
and diacritics are matched literally)."""

from __future__ import annotations

# Past — ngày xưa (long ago) / nhiều năm trước (years ago) / ban đầu (originally) /
# từng·đã từng (used to) / thuở trước.
HISTORICAL_STRONG = (
    r"ngày xưa|nhiều năm trước|mấy chương trước|ban đầu|"
    r"lúc đầu|thuở trước|đã từng|từng"
)

# Weaker past — trước đây / trước kia / trước đó.
HISTORICAL_WEAK = r"trước đây|trước kia|trước đó"

# Present/near — vừa nãy·vừa mới (just now) / ngay bây giờ·hiện tại (now/currently) /
# chương này (this chapter).
RECENT = (
    r"vừa nãy|vừa mới|vừa xảy ra|vừa|ngay bây giờ|bây giờ|hiện tại|"
    r"chương này|lúc này|đang"
)

# Relational — biết·quen·gặp (know/meet) / quan hệ·giữa·liên hệ (relationship/between) /
# bạn·kẻ thù (friend/enemy) / kết hôn·liên minh·đối thủ (married/allied/rival).
RELATIONAL_KEYWORDS = (
    r"biết|quen|gặp|quan hệ|giữa|liên hệ|cùng nhau|"
    r"bạn bè|bạn|kẻ thù|kết hôn|liên minh|đối thủ|đồng minh"
)

# Explicit relational phrasings.
RELATIONAL_STRONG = (
    r"mối quan hệ giữa|ai biết|ai quen|sự liên hệ giữa|có quan hệ gì"
)
