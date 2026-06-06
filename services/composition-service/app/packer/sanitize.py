"""Prompt-injection guard for untrusted pack inputs (§13 SEC3).

`<lore>` (retrieved KG passages) and `<guide>` (author free-text) originate from
ARBITRARY book/imported text — they can carry "ignore previous instructions…"
payloads or forged block tags. Easy to miss because the lore is "ours", but it
is untrusted. We **tag, not delete** (the enrichment `sanitize.py` lesson):
neutralise directive-looking spans so the model reads them as quoted data, and
escape angle brackets so injected text can't forge our `<canon>`/`<guide>`
assembly delimiters. `<guide>` is also length-bounded.
"""

from __future__ import annotations

import re

# Directive-style phrases that a jailbreak payload uses. Case-insensitive.
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore (?:all |the |your |previous |above |prior |any )*"
        r"(?:instructions?|prompts?|rules?|context)",
        r"disregard (?:all |the |your |previous |above |prior )*"
        r"(?:instructions?|prompts?|rules?)",
        r"forget (?:everything|all|the above|previous|prior)",
        r"you are now\b",
        r"new (?:instructions?|system prompt|rules?)\s*:",
        r"system\s*prompt",
    ]
]

GUIDE_MAX_LEN = 2000


def neutralize(text: str) -> str:
    """Escape assembly-delimiter chars + tag injection directives (no deletion)."""
    if not text:
        return ""
    # 1. Fullwidth-escape angle brackets so injected text can't forge our
    #    `<block>` delimiters (assemble.py uses them structurally).
    text = text.replace("<", "＜").replace(">", "＞")
    # 2. Wrap directive spans in brackets so the model reads them as data, not
    #    commands. Tag-not-delete: the span survives (no info loss), but inert.
    for pat in _INJECTION_PATTERNS:
        text = pat.sub(lambda m: f"⟦{m.group(0)}⟧", text)
    return text


def sanitize_lore(text: str) -> str:
    """Neutralise a retrieved lore/passage string before assembly."""
    return neutralize(text)


def sanitize_guide(text: str, max_len: int = GUIDE_MAX_LEN) -> str:
    """Bound + neutralise the author's free-text steer."""
    return neutralize((text or "")[:max_len])
