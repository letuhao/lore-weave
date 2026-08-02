"""
Split chapter text into token-estimated chunks, respecting sentence/paragraph boundaries.

Splitting priority:
  1. Paragraph break (\\n\\n or \\n followed by blank line)
  2. Sentence-ending punctuation (handles CJK and Latin scripts)
  3. Any whitespace
  4. Hard cut at max_chars (last resort — should rarely happen)

Token estimation: the KERNEL's script-aware estimator (`loreweave_context.estimate_tokens`),
not a local heuristic. S11 — this module used to carry its own two-class version (CJK 1.5
chars/token, everything else 4.0) which measured 0.68-0.70x of tiktoken `o200k_base` on both
Chinese and Vietnamese, i.e. it UNDER-counted by roughly a third on exactly the scripts this
service translates. Vietnamese had no class at all and was counted at the Latin ratio.

`split_chapter` now derives its chars-per-token from that same estimator rather than from a
separate pair of constants, so the window it cuts and the budget it is cut against cannot
drift apart. The old constants survive only as the empty-sample fallback and for
backward-compatible imports.
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
    """Script-aware token estimate — the KERNEL's, not a fourth local copy.

    S11. This module's own version counted two classes, CJK and "other", and its docstring
    claimed to have fixed "the ~2.3x underestimation bug for CJK text that caused context
    window overflow and hallucination". MEASURED against tiktoken `o200k_base` it had not:

        text          chars   tiktoken   this module   ratio
        Vietnamese      205         73            51   0.70x
        Chinese          35         34            23   0.68x
        English         134         28            33   1.18x

    So a chunk the splitter believed was 2000 tokens really reached the model at ~2900 — a
    43% overflow, which is the SAME failure the CJK fix was written for, still open on both
    dense scripts. Vietnamese was the worse case for a structural reason: this module has no
    Vietnamese class at all, so a language whose diacritics tokenize far denser than English
    was counted at the LATIN ratio — in the service that translates Vietnamese novels.

    `loreweave_context.estimate_tokens` carries the third class (CJK 1.05, Vietnamese 0.55,
    Latin 0.25, other 0.45) and is the kernel's pre-send projection, so counting here now
    agrees with what the packer and the compaction strategy count elsewhere. Under-counting
    is the dangerous direction — it overflows a window — and this moves every script toward
    the measurement rather than away from it.

    The name stays put deliberately: five modules import `chunk_splitter.estimate_tokens`,
    and re-pointing them one by one is churn that would let two conventions coexist for the
    duration. One body, one edit, every consumer.
    """
    from loreweave_context import estimate_tokens as _kernel_estimate

    return _kernel_estimate(text)


def split_chapter(text: str, max_tokens: int) -> list[str]:
    """
    Split text into a list of chunks each with ≤ max_tokens estimated tokens.
    Returns [text] unchanged if the whole text fits in one chunk.
    Returns [] for empty or whitespace-only input.
    """
    text = text.strip()
    if not text:
        return []

    # Chars-per-token MEASURED from this text with the same estimator the chunks will be
    # judged by — not read off a separate pair of constants.
    #
    # S11: those constants (CJK 1.5, Latin 4.0) used to be shared with `estimate_tokens`, so
    # sizing and counting agreed by accident. Once the estimator moved to the kernel they
    # would have DIVERGED: a 100-token budget still cut 150 CJK chars, which the kernel counts
    # as 158 — 58% over the budget the caller asked for. Two conventions inside one module is
    # the exact defect this slice is closing, and it would have arrived as a side effect of
    # closing it elsewhere.
    #
    # Deriving the ratio also fixes the sampling: the old rule was a 30% CJK threshold applied
    # to the WHOLE text, so a chapter 29% CJK was sized entirely at the Latin ratio. A
    # per-character estimate has no cliff.
    sample = text[:2000]
    sample_tokens = estimate_tokens(sample)
    chars_per_token = (len(sample) / sample_tokens) if sample_tokens else _LATIN_CHARS_PER_TOKEN
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
