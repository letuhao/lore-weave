"""loreweave_safety — the platform SAFETY FLOOR (WS-5.11, spec 08 Gate-3).

ONE home for the deterministic distress/harassment/self-harm floor + the clinical deny-list,
so every consumer (worker-ai weekly reflection, chat-service practice gate) screens IDENTICALLY.
A second copy of a safety lexicon is a drift this repo must not ship.
"""
from loreweave_safety.floor import (  # noqa: F401
    CAT_DISTRESS, CAT_HARASSMENT_ABUSE, CAT_SELF_HARM,
    SafetyVerdict, combine_with_model, contains_clinical_language, screen,
)

__all__ = [
    "screen", "combine_with_model", "contains_clinical_language", "SafetyVerdict",
    "CAT_SELF_HARM", "CAT_DISTRESS", "CAT_HARASSMENT_ABUSE",
]
