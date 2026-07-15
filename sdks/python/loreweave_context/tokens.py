"""Script-aware token estimation (Context Budget Law A1-A2), the kernel's foundational
budget primitive. A flat ``chars/4`` under-counts CJK/Vietnamese 4-8x (the POC is VN
"Ma Nữ Nghịch Thiên" + Chinese "万古神帝"); this estimates by unicode script class. Pure
stdlib, provider-agnostic — the measured provider `promptTokens` stays ground truth; this
is the PRE-SEND projection the Compiler/CompactionStrategy budget against.

Moved into the kernel in T3.3 (was chat-service `token_budget`); re-exported there for
backward compatibility with its many callers.
"""
from __future__ import annotations

# tokens-per-character factors by script class (empirical BPE approximations; the goal
# is "not 4-8x wrong for CJK/VN", not exactness — the provider usage is ground truth).
_F_CJK = 1.05          # Han / Kana / Hangul — roughly one token per glyph (often 1-2)
_F_VIETNAMESE = 0.55   # Latin + Vietnamese diacritics tokenize far denser than English
_F_LATIN = 0.25        # ASCII letters/digits — the classic chars/4
_F_OTHER = 0.45        # everything else (symbols, other scripts) — a middle guess


def _char_factor(cp: int) -> float:
    # CJK Unified + Ext-A, Kana, Hangul, CJK symbols/compat — the dense scripts.
    if (
        0x4E00 <= cp <= 0x9FFF      # CJK Unified Ideographs
        or 0x3400 <= cp <= 0x4DBF   # CJK Ext-A
        or 0x3040 <= cp <= 0x30FF   # Hiragana + Katakana
        or 0xAC00 <= cp <= 0xD7AF   # Hangul syllables
        or 0xF900 <= cp <= 0xFAFF   # CJK compat ideographs
        or 0x3000 <= cp <= 0x303F   # CJK symbols/punct
        or 0x20000 <= cp <= 0x2FA1F  # CJK Ext-B..F + compat supplement
    ):
        return _F_CJK
    # Vietnamese: Latin Extended Additional (precomposed VN vowels) + combining marks.
    if 0x1EA0 <= cp <= 0x1EFF or 0x0300 <= cp <= 0x036F or cp in (0x0110, 0x0111):
        return _F_VIETNAMESE
    # ASCII letters/digits/space/punct + Latin-1/Extended-A (accented European).
    if cp < 0x0250:
        return _F_LATIN
    return _F_OTHER


def estimate_tokens(text: str | None) -> int:
    """Script-aware token estimate for a string. Not exact — but not 4-8x wrong on
    CJK/Vietnamese the way ``len(text)//4`` is."""
    if not text:
        return 0
    total = 0.0
    for ch in text:
        total += _char_factor(ord(ch))
    # small per-message structural overhead (role/formatting tokens); floor at 1.
    return max(1, round(total))


def split_to_token_budget(text: str | None, budget: int) -> list[str]:
    """Split ``text`` into consecutive slices, each estimated at ≤ ``budget`` tokens
    (script-aware — the SAME ``_char_factor`` the estimator uses, so a consumer that must
    hard-split an over-window message never re-derives the ratio, and a CJK slice is cut
    ~4x shorter in chars than a Latin one). O(n), single pass.

    Guarantees: no character is dropped; a slice is closed as soon as adding the next char
    would exceed ``budget`` (except a lone char whose factor alone already ≥ budget — it
    becomes its own over-budget slice rather than being lost). Returns ``[]`` for empty
    text; returns the whole text as one slice for a non-positive budget."""
    if not text:
        return []
    if budget <= 0:
        return [text]
    slices: list[str] = []
    start = 0
    acc = 0.0
    for i, ch in enumerate(text):
        f = _char_factor(ord(ch))
        if acc + f > budget and i > start:
            slices.append(text[start:i])
            start = i
            acc = 0.0
        acc += f
    if start < len(text):
        slices.append(text[start:])
    return slices


def estimate_messages_tokens(messages: list[dict] | None) -> int:
    """Estimate the input tokens for a chat `messages` array (role + content)."""
    if not messages:
        return 0
    total = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):  # content parts (text blocks)
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total += estimate_tokens(part["text"])
        # Assistant tool-call turns carry the weight in tool_calls (function name +
        # arguments JSON), often with content=None — count them or a tool-heavy turn
        # is badly under-estimated (matters on the resume / tool-loop path).
        for tc in (m.get("tool_calls") or []):
            fn = tc.get("function") or {}
            total += estimate_tokens(fn.get("name"))
            total += estimate_tokens(fn.get("arguments"))
        total += 4  # per-message role/delimiter overhead (OpenAI-style)
    return total
