"""English marker patterns for K15.3 pattern extraction.

Raw regex strings — compiled with re.IGNORECASE by the package
`_compile_all` helper. Keep each tuple to 6-10 entries per KSA
§5.4 coverage policy (80% is fine; LLM Pass 2 catches the rest).
"""

from __future__ import annotations

DECISION_MARKERS: tuple[str, ...] = (
    r"\blet'?s use\b",
    r"\bwe decided\b",
    r"\bwe'?ll go with\b",
    r"\bgoing with\b",
    r"\binstead of\b",
    r"\bswitched to\b",
    r"\bdecided to\b",
    r"\bchose\b",
)

PREFERENCE_MARKERS: tuple[str, ...] = (
    r"\bI prefer\b",
    r"\bI like\b",
    r"\balways use\b",
    r"\bnever use\b",
    r"\bprefer(?:red|s)?\b",
    r"\bfavou?rite\b",
    r"\bI want\b",
    r"\bI hate\b",
)

MILESTONE_MARKERS: tuple[str, ...] = (
    r"\bit works\b",
    r"\bfinished chapter\s+\d+\b",
    r"\bcompleted\b",
    r"\bdone with\b",
    r"\bshipped\b",
    r"\breached\b",
    r"\bfinally\b",
    r"\bat last\b",
)

NEGATION_MARKERS: tuple[str, ...] = (
    r"\bdoes not know\b",
    r"\bdoesn'?t know\b",
    r"\bis unaware\b",
    r"\bnever met\b",
    r"\bhas no idea\b",
    r"\bcannot\b",
    r"\bisn'?t\b",
    r"\bwas never\b",
)

SKIP_MARKERS: tuple[str, ...] = (
    r"\bif\b",
    r"\bwould have\b",
    r"\bcould have\b",
    r"\bmight have\b",
    r"\bsuppose\b",
    r"\bimagine\b",
    r"\bsaid that\b",
    r"\bclaimed\b",
    r"\ballegedly\b",
)
