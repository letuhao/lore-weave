"""Token estimator.

D-T2-01: swapped from `len/4` heuristic to a tiktoken BPE encoding (the
old heuristic undercounts CJK by ~3-7×, so budgets were over-promised).

M3 (2026-07-07): swapped the encoding **cl100k_base → o200k_base**. cl100k
(GPT-4-turbo / Claude-3.x era) tokenizes CJK at ~1.6-2.5 tokens/char, which
**over-counts by ~40%** against the models the platform actually serves —
GPT-4o (o200k), and modern local models (gemma/qwen, ~1 tok/CJK-char). The
M3 pull-mode measurement caught this live: a wangu (Chinese) Mode-3 block the
gateway tokenized at ~3636 tokens was estimated at ~5091 under cl100k, so the
Inspector's per-turn numbers were inflated for non-Latin books AND CJK books
were trimmed to a smaller REAL budget than Latin ones (the enforcer compares
this estimate to `mode3_token_budget`). o200k is a better proxy for both the
GPT-4o family and modern local tokenizers; English counts are ~unchanged
(o200k ≈ cl100k for Latin). Still an approximation — no single tokenizer
matches every served model — but a materially more accurate default.

Handles None and non-string input defensively — the caller never has
to wrap this in a try/except.

Fallback chain: o200k_base → cl100k_base (older tiktoken without o200k) →
`len/4` (tiktoken absent entirely). Track 1 paths must still run.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["estimate_tokens"]


try:
    import tiktoken

    try:
        _encoder = tiktoken.get_encoding("o200k_base")
    except Exception:
        # Older tiktoken without the GPT-4o encoding — fall back to cl100k
        # (still far better than len/4, just ~40% high on CJK).
        _encoder = tiktoken.get_encoding("cl100k_base")
        logger.warning(
            "tiktoken o200k_base unavailable — using cl100k_base "
            "(over-counts CJK ~40%). Upgrade tiktoken for accurate CJK budgets."
        )
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
