"""Rough token estimator.

Track 1 uses a len/4 heuristic — good enough for budget enforcement
when the budgets themselves are approximate. Track 2 switches to
tiktoken for accurate counts, at which point this module becomes a
thin shim around `tiktoken.encoding_for_model().encode(text)`.

Handles None and non-string input defensively — the caller never has
to wrap this in a try/except.
"""

__all__ = ["estimate_tokens"]


def estimate_tokens(text: str | None) -> int:
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    # 1 token ≈ 4 characters for English (OpenAI cl100k_base rule of thumb).
    # CJK undercounts at ~0.75 tokens per character but we accept that
    # for Track 1 — budgets are 1000+ tokens so a 30 % error is survivable.
    return max(1, len(text) // 4)
