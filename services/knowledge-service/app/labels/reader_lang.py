"""KG-ML — shared reader-language param hygiene for KG read surfaces.

The optional ``?language=`` hint on a localizing read (raw-search M4, graph-view
C7) is validated against a lenient BCP-47-ish shape (mirrors book-service M3
``langTagRe``). A malformed value is IGNORED — the caller falls through to the
stored reader-language preference rather than silently disabling localization.
"""

from __future__ import annotations

import re

__all__ = ["LANG_TAG_RE", "clean_lang_param"]

LANG_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$")


def clean_lang_param(language: str | None) -> str | None:
    """Trim + validate an inbound ``?language=`` value. Returns the cleaned tag,
    or ``None`` for empty/malformed (so the caller resolves the stored
    reader-language preference instead)."""
    pref = (language or "").strip() or None
    if pref and not LANG_TAG_RE.match(pref):
        return None
    return pref
