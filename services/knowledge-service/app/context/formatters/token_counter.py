"""Token estimator.

D-T2-01: swapped from `len/4` heuristic to tiktoken's cl100k_base
encoding. The old heuristic undercounts CJK by ~3-7× (a 10-char
Chinese string estimated at 2 tokens actually consumes ~14 with
GPT-4's tokenizer), so budgets were over-promised for CJK content.
cl100k_base matches GPT-4 / Claude-3.x tokenization closely enough
for budget enforcement.

Handles None and non-string input defensively — the caller never has
to wrap this in a try/except.

Fallback: if tiktoken can't be imported (dev env without the dep,
sandboxed test), we log once at import time and use `len/4`. Track 1
paths must still run.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["estimate_tokens"]


try:
    import tiktoken

    _encoder = tiktoken.get_encoding("cl100k_base")
except Exception:  # tiktoken missing, network-less install, etc.
    _encoder = None
    logger.warning(
        "tiktoken unavailable — falling back to len/4 heuristic "
        "for token counting. CJK content will be under-budgeted."
    )


def estimate_tokens(text: str | None) -> int:
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    if _encoder is None:
        # Fallback — the old len/4 heuristic. Preserved only for the
        # tiktoken-missing case; not the expected path.
        return max(1, len(text) // 4)
    return max(1, len(_encoder.encode(text)))
