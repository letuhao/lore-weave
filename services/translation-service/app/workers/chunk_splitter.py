"""
Split chapter text into token-estimated chunks, respecting sentence/paragraph boundaries.

Splitting priority:
  1. Paragraph break (\\n\\n or \\n followed by blank line)
  2. Sentence-ending punctuation (handles CJK and Latin scripts)
  3. Any whitespace
  4. Hard cut at max_chars (last resort — should rarely happen)

Token estimation: CJK-aware heuristic.
  - CJK characters (Chinese, Japanese kanji, Korean): ~1.5 chars/token
  - Hiragana/Katakana: ~1.5 chars/token
  - Latin/Cyrillic/other: ~4.0 chars/token
  - Mixed text: computed per-character for accuracy
"""

# Characters that mark the end of a sentence in any supported language
_SENTENCE_ENDS = frozenset(
    # Latin
    ".!?"
    # CJK
    "。！？…"
    # Vietnamese / Southeast Asian
    "।"
    # Ellipsis variants
    "⋯"
)

# Legacy constant kept for backward compat (split_chapter max_chars calculation)
TOKEN_CHAR_RATIO = 3.5

# CJK chars per token (conservative — real is ~1.5-2.0, we use 1.5 to overestimate)
_CJK_CHARS_PER_TOKEN = 1.5
# Latin/other chars per token
_LATIN_CHARS_PER_TOKEN = 4.0


def _is_cjk(char: str) -> bool:
    """Return True if char is CJK, Hiragana, Katakana, Hangul, or CJK punctuation."""
    cp = ord(char)
    return (
        0x4E00 <= cp <= 0x9FFF        # CJK Unified Ideographs
        or 0x3400 <= cp <= 0x4DBF     # CJK Extension A
        or 0x3000 <= cp <= 0x303F     # CJK Symbols and Punctuation
        or 0x3040 <= cp <= 0x309F     # Hiragana
        or 0x30A0 <= cp <= 0x30FF     # Katakana
        or 0xAC00 <= cp <= 0xD7AF     # Hangul Syllables
        or 0xFF00 <= cp <= 0xFFEF     # Fullwidth Forms
        or 0x20000 <= cp <= 0x2A6DF   # CJK Extension B
    )


def estimate_tokens(text: str) -> int:
    """CJK-aware token count estimate — fast, no model dependency.

    Counts CJK and non-CJK characters separately, applies different
    chars-per-token ratios. This fixes the ~2.3x underestimation bug
    for CJK text that caused context window overflow and hallucination.
    """
    if not text:
        return 0
    cjk = sum(1 for c in text if _is_cjk(c))
    other = len(text) - cjk
    return max(1, int(cjk / _CJK_CHARS_PER_TOKEN + other / _LATIN_CHARS_PER_TOKEN))


def split_chapter(text: str, max_tokens: int) -> list[str]:
    """
    Split text into a list of chunks each with ≤ max_tokens estimated tokens.
    Returns [text] unchanged if the whole text fits in one chunk.
    Returns [] for empty or whitespace-only input.
    """
    text = text.strip()
    if not text:
        return []

    # Use CJK-aware estimate: if text is CJK-heavy, fewer chars fit per token.
    # Conservative: use _CJK_CHARS_PER_TOKEN for the whole text if >30% CJK.
    sample = text[:2000]
    cjk_frac = sum(1 for c in sample if _is_cjk(c)) / max(1, len(sample))
    chars_per_token = _CJK_CHARS_PER_TOKEN if cjk_frac > 0.3 else _LATIN_CHARS_PER_TOKEN
    max_chars = max(1, int(max_tokens * chars_per_token))

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        window = remaining[:max_chars]

        # 1. Prefer paragraph boundary (two or more newlines)
        split = _rfind_paragraph_break(window)

        # 2. Fall back to last sentence-ending punctuation
        if split <= 0:
            split = _rfind_sentence_end(window)

        # 3. Fall back to last whitespace
        if split <= 0:
            split = window.rfind(" ")
            if split > 0:
                split += 1  # include the space in the first chunk

        # 4. Hard split
        if split <= 0:
            split = max_chars

        chunk = remaining[:split].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split:].strip()

    return [c for c in chunks if c]


def _rfind_paragraph_break(text: str) -> int:
    """Return the position just after the last paragraph break, or 0."""
    # Look for \n\n (or \n + optional whitespace + \n)
    pos = len(text) - 1
    while pos > 0:
        if text[pos] == "\n":
            # Scan backwards past any whitespace to find another \n
            j = pos - 1
            while j >= 0 and text[j] in " \t\r":
                j -= 1
            if j >= 0 and text[j] == "\n":
                return pos + 1  # position after the second newline
        pos -= 1
    return 0


def _rfind_sentence_end(text: str) -> int:
    """Return the position just after the last sentence-ending char, or 0."""
    for i in range(len(text) - 1, -1, -1):
        if text[i] in _SENTENCE_ENDS:
            return i + 1
    return 0
