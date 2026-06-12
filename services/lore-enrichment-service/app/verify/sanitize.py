"""Injection-defense — SHIM over `loreweave_grounding.sanitize` (mui #3 LE-migrate).

This module's logic was lifted verbatim into the shared `loreweave_grounding`
SDK. It now re-exports the SDK so every existing importer
(`from app.verify.sanitize import neutralize_proposal_text / scan_injection /
_prenormalize / INJECTION_PATTERNS / FICTIONAL_MARKER`) resolves unchanged —
byte-identical behavior, single source of truth. The `globals().update` brings
the private names (`_prenormalize`, etc.) the codebase imports, not just `__all__`.
"""

from __future__ import annotations

from loreweave_grounding import sanitize as _src
from loreweave_grounding.sanitize import (  # explicit public re-export (linters/IDE)
    FICTIONAL_MARKER,
    INJECTION_PATTERNS,
    neutralize_proposal_text,
    scan_injection,
)

# Bring EVERY module attribute (incl. privates like _prenormalize, _INVISIBLE,
# _pattern_hits, _scan_base64_injection) so any existing import site resolves.
globals().update({k: getattr(_src, k) for k in dir(_src) if not k.startswith("__")})

__all__ = [
    "INJECTION_PATTERNS",
    "neutralize_proposal_text",
    "scan_injection",
    "FICTIONAL_MARKER",
]
