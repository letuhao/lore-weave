"""Output regurgitation guard — SHIM over `loreweave_grounding.regurgitation`
(mui #3 LE-migrate).

Logic lifted verbatim into the shared SDK; this re-exports it so existing
importers (`detect_regurgitation`, the thresholds, the helpers) resolve
unchanged. `globals().update` brings privates (`_normalize`, `MIN_OVERLAP_LEN`,
`_WS`) too, so a byte-identical single source of truth.
"""

from __future__ import annotations

from loreweave_grounding import regurgitation as _src
from loreweave_grounding.regurgitation import (  # explicit public re-export
    LCS_FLAG,
    LCS_FRACTION,
    LCS_REJECT,
    NGRAM_N,
    OVERLAP_FLAG,
    RegurgitationResult,
    char_ngram_containment,
    detect_regurgitation,
    longest_common_substring_len,
)

globals().update({k: getattr(_src, k) for k in dir(_src) if not k.startswith("__")})

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
