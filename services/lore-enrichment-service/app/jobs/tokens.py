"""Token-metering primitives (RAID C1 / DEFERRED-052) — the in-branch mirror of
the PLATFORM token convention (provider-registry ``internal/billing/estimate.go``).

The per-job cost-cap is denominated in REAL tokens (PO ruling, audit C1): the
GENERATION leg harvests the LLM ``usage`` SSE frame (``input_tokens`` +
``output_tokens`` + ``reasoning_tokens``, reasoning folded into output); the
EMBED leg has no provider count (``/internal/embed`` returns only vectors) so it
is ESTIMATED from the query text with the SAME script-aware char divisor the
platform uses. A per-job :class:`UsageMeter` accumulates the seam-level usage and
the runner reconciles the cap against the meter's per-gap delta.

This module owns ONLY the token arithmetic + the estimate convention — NO I/O,
NO model names, NO currency. It is the single in-branch source of the platform's
char→token formula so retrieval (embed estimate), generation (usage fallback),
and the cost model all agree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "CJK_DIVISOR",
    "LATIN_DIVISOR",
    "NON_ASCII_SHARE_THRESHOLD",
    "TokenUsage",
    "estimate_tokens",
    "UsageMeter",
]

# ── platform char→token convention (mirror billing/estimate.go) ───────────────
# Divisors sit AT or BELOW the real chars-per-token ratio for their script, so
# dividing by them OVER-estimates the token count — the safe direction for a
# guardrail bound. LoreWeave is a multilingual novel platform; the demo corpus
# (封神演义 / 山海经) is CJK, which tokenizes at ~1 token per character.
CJK_DIVISOR: float = 1.0  # CJK / Thai / Devanagari: ~1 token per char
LATIN_DIVISOR: float = 3.5  # ASCII / Latin scripts: ~4 chars per token
#: A text whose non-ASCII rune share is at/above this fraction is treated as
#: CJK-heavy → the CJK divisor (over-estimating is the safe default, per design).
NON_ASCII_SHARE_THRESHOLD: float = 0.2


def estimate_tokens(text: str) -> int:
    """Worst-case token count for ``text`` using the platform's script-aware
    divisor: ``ceil(chars / 1.0)`` when the non-ASCII rune share ≥ 0.2 (CJK),
    else ``ceil(chars / 3.5)`` (Latin). Empty → 0.

    Mirrors provider-registry ``estimateInputTokens`` so the in-branch embed
    estimate + generation fallback agree with the platform's billing math.
    """
    chars = len(text)
    if chars <= 0:
        return 0
    non_ascii = sum(1 for c in text if ord(c) > 127)
    divisor = (
        CJK_DIVISOR
        if (non_ascii / chars) >= NON_ASCII_SHARE_THRESHOLD
        else LATIN_DIVISOR
    )
    return math.ceil(chars / divisor)


@dataclass(frozen=True)
class TokenUsage:
    """A token spend: input + output tokens (reasoning is folded into output by
    the harvesting seam, matching how the platform bills reasoning)."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        """The total billable tokens (input + output)."""
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class UsageMeter:
    """Accumulates :class:`TokenUsage` across the seam calls of ONE job run.

    The embed seam + the generation seam each ``add`` their usage as they run;
    the runner snapshots :attr:`total_tokens` before a gap and reads it after,
    so the delta is that gap's real token spend (which it reconciles against the
    cost-cap).

    **Sequential-safe ONLY.** The runner processes gaps strictly one at a time
    (it ``await``\\s each ``run_gap`` fully before the next), so a before/after
    delta isolates a single gap. If gaps are ever processed concurrently this
    meter must be made per-gap-scoped (the global accumulator would conflate
    overlapping gaps' spend).
    """

    def __init__(self) -> None:
        self._usage = TokenUsage()

    def add(self, usage: TokenUsage) -> None:
        """Record one seam call's token usage."""
        self._usage = self._usage + usage

    @property
    def usage(self) -> TokenUsage:
        """The accumulated usage so far."""
        return self._usage

    @property
    def total_tokens(self) -> int:
        """The accumulated total tokens so far (input + output)."""
        return self._usage.total
