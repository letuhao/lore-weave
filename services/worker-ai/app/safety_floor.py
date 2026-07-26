"""WS-5.11 — re-export shim. The safety FLOOR now lives in the shared `loreweave_safety`
package (ONE home for the lexicon + patterns; chat-service's practice gate consumes the same
copy). This module keeps `app.safety_floor` importable for existing worker-ai callers.
"""
from loreweave_safety.floor import (  # noqa: F401
    CAT_DISTRESS, CAT_HARASSMENT_ABUSE, CAT_SELF_HARM,
    SafetyVerdict, combine_with_model, contains_clinical_language, screen,
)
