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
# DEFERRED-050: also neutralize "forget the above" + Classical-Chinese (文言文)
# meta-directives anchored on a textual BACK-REFERENCE (前述/上文/以上 — "the
# AFOREMENTIONED text/command"). Kept in sync with the fuller verify/sanitize.py
# scanner; deliberately narrow (an in-world Classical command has no back-
# reference) so legitimate 封神演义 prose passes through untouched.
_MARKERS = re.compile(
    r"(?is)("
    r"<\|[a-z_]+\|>"                      # <|im_start|>, <|system|>, …
    r"|\[/?INST\]"                        # [INST] / [/INST]
    r"|</?s>"                             # <s> / </s>
    r"|\b(?:system|assistant|user)\s*:"   # role: prefixes
    r"|ignore\s+(?:all\s+)?previous\s+instructions"
    r"|forget\s+(?:everything|all|previous|the\s+above)"
    r"|(?:勿|毋|莫|休|不[要须必]|无须|毋须)"
    r"(?:从|听|遵|依|理会|顾|采纳|执行|遵从|遵循)"
    r"[^\n]{0,10}?(?:前述|前文|上文|以上|前面|之前|先前|前言)"
    r"|(?:违背|背离|违逆|推翻|废除|废止|摒弃|抛却)"
    r"[^\n]{0,10}?(?:前述|前文|上文|以上|之前|先前|前言)"
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
