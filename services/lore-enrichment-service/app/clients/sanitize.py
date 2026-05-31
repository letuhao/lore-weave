"""C1 M4 — inbound text neutralization for read clients.

Entity/wiki text read from glossary is untrusted: an author (or an extractor
that ingested a poisoned chapter) could embed prompt-injection instructions in
an entity name/description. C1 is read-only and does NOT itself call an LLM, but
it is the seam where this text ENTERS the enrichment service, so we neutralize
on the way IN — defense in depth ahead of C11/C12 generation.

`neutralize_injection` is conservative: it strips/escapes the common
prompt-injection control markers and zero-width characters while preserving all
legitimate CJK content (封神演义 names like 玉虛宮/碧遊宮/金鰲島/蓬萊/陳塘關 pass through
untouched — only ASCII control/markup tokens are affected). It never raises and
never returns None, so a degraded read still yields safe, typed text.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["neutralize_injection"]

# Zero-width / bidi-control chars used to smuggle hidden instructions.
_INVISIBLE = dict.fromkeys(
    [
        0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2028, 0x2029,
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0xFEFF,
        0x2066, 0x2067, 0x2068, 0x2069,
    ],
    None,
)

# Common injection control markers (chat-template + role-spoofing tokens).
_MARKERS = re.compile(
    r"(?is)("
    r"<\|[a-z_]+\|>"                      # <|im_start|>, <|system|>, …
    r"|\[/?INST\]"                        # [INST] / [/INST]
    r"|</?s>"                             # <s> / </s>
    r"|\b(?:system|assistant|user)\s*:"   # role: prefixes
    r"|ignore\s+(?:all\s+)?previous\s+instructions"
    r")"
)


def neutralize_injection(text: str | None) -> str:
    """Return a safe, typed-string form of untrusted entity/wiki text.

    - None → "" (never propagate None into generation later).
    - Strips zero-width / bidi control characters.
    - Normalizes to NFC (so visually-identical CJK forms compare equal and
      hidden combining tricks collapse).
    - Replaces injection control markers with a visible, inert placeholder so
      the content is preserved for the human reviewer but cannot act as an
      instruction.
    """
    if not text:
        return ""
    # Drop invisibles, then NFC-normalize (CJK-safe — NFC is the canonical
    # composed form Chinese text already uses).
    cleaned = text.translate(_INVISIBLE)
    cleaned = unicodedata.normalize("NFC", cleaned)
    cleaned = _MARKERS.sub("[neutralized]", cleaned)
    return cleaned
