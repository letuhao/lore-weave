"""
Split chapter text into token-estimated chunks, respecting sentence/paragraph boundaries.

Splitting priority:
  1. Paragraph break (\\n\\n or \\n followed by blank line)
  2. Sentence-ending punctuation (handles CJK and Latin scripts)
  3. Any whitespace
  4. Hard cut at max_chars (last resort — should rarely happen)

Token estimation: 1 token ≈ TOKEN_CHAR_RATIO characters.
This is a conservative estimate (actual ratio varies by model and language):
  - English / Latin: ~4 chars/token
  - CJK (Chinese/Japanese/Korean): ~1.5-2 chars/token
  - Mixed: ~3.5 chars/token (default)
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

# Conservative chars-per-token ratio for mixed CJK/Latin text
TOKEN_CHAR_RATIO = 3.5


def estimate_tokens(text: str) -> int:
    """Rough token count estimate — fast, no model dependency."""
    return max(1, int(len(text) / TOKEN_CHAR_RATIO))


def split_chapter(text: str, max_tokens: int) -> list[str]:
    """
    Split text into a list of chunks each with ≤ max_tokens estimated tokens.
    Returns [text] unchanged if the whole text fits in one chunk.
    Returns [] for empty or whitespace-only input.
    """
    text = text.strip()
    if not text:
        return []

    max_chars = max(1, int(max_tokens * TOKEN_CHAR_RATIO))

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
