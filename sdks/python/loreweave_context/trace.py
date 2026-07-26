"""Context Budget Law **compile trace** — the per-turn telemetry the Inspector GUI reads
(spec §11 / §12a). A `TraceSpan` is ONE decision the Planner or Compiler made while building
a turn's context: a tier gated/included/compacted/serialized some category, with a signed token
`delta`. The ORDERED list of spans is the "Compile trace — Planner → Compiler" waterfall; their
summed savings reconstruct `raw_tokens` (the naive-concat baseline) from `compiled_tokens`.

Pure-Python, provider-agnostic (no SDK, no model literal) — every kernel consumer (chat now;
roleplay/composition later) emits the SAME shape, so the one Inspector works for all of them
(spec §12a payoff). The shape here is the frozen contract mirrored in
`contracts/context-trace.contract.json`.
"""
from __future__ import annotations

from dataclasses import dataclass

# The tier vocabulary the Law defines (T0 wire-hygiene … T6 compaction). A span's tier
# says WHICH law tier made the decision; the Inspector renders it as the `T0`–`T6` tag.
TIERS: tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4", "T5", "T6")
PHASES: tuple[str, ...] = ("planner", "compiler")


@dataclass(frozen=True)
class TraceSpan:
    """One Planner/Compiler decision. `delta` is signed by CONVENTION:
      < 0  tokens SAVED (dropped / gated / compacted / collapsed / wire-trimmed),
      > 0  tokens INCLUDED (grounding pulled, chapter whitelisted, summary materialized),
      = 0  neutral (a check that fired but moved nothing, e.g. "under target — OK").
    `is_error` marks a reject/self-correcting-error span (e.g. an oversized result rejected).
    `category` is one of the allocation categories (system/blocks/skills/grounding/history/
    summary/tools/results/chapter/reasoning) so the Inspector can color the span's dot."""

    phase: str          # "planner" | "compiler"
    tier: str           # one of TIERS
    category: str       # an allocation category (Inspector color dot)
    action: str         # human-readable action_text (what the tier did)
    delta: int = 0      # signed token delta (see convention above)
    is_error: bool = False

    def to_payload(self) -> dict:
        return {
            "phase": self.phase,
            "tier": self.tier,
            "category": self.category,
            "action": self.action,
            "delta": int(self.delta),
            "is_error": bool(self.is_error),
        }


class TraceAccumulator:
    """Collects `TraceSpan`s across one turn's assembly, IN ORDER. The consumer adds a span
    at each tier decision site; at emit time the payload (`to_payload`) becomes the frame's
    `trace[]` and `saved()` reconstructs the naive-concat baseline:
    ``raw_tokens = compiled_tokens + saved()``.

    Deliberately tiny + side-effect-free: a dropped `.add(...)` silently loses one span but
    never breaks the turn (telemetry is advisory), and the accumulator holds no I/O."""

    def __init__(self) -> None:
        self._spans: list[TraceSpan] = []

    def add(
        self,
        phase: str,
        tier: str,
        category: str,
        action: str,
        delta: int = 0,
        *,
        is_error: bool = False,
    ) -> None:
        self._spans.append(
            TraceSpan(
                phase=phase,
                tier=tier,
                category=category,
                action=action,
                delta=int(delta or 0),
                is_error=bool(is_error),
            )
        )

    @property
    def spans(self) -> list[TraceSpan]:
        return list(self._spans)

    def saved(self) -> int:
        """Total tokens SAVED this turn = Σ of the magnitudes of the negative deltas.
        This is the amount a naive concat would have carried on top of `compiled`."""
        return sum(-s.delta for s in self._spans if s.delta < 0)

    def to_payload(self) -> list[dict]:
        return [s.to_payload() for s in self._spans]


def reduction_pct(raw_tokens: int, compiled_tokens: int) -> float | None:
    """`1 - compiled/raw` in [0,1], rounded to 4dp. None when raw is unknown/≤0 (the
    Inspector renders '—'). raw==compiled (nothing cut) → 0.0 (honest, not a fake headline)."""
    if not raw_tokens or raw_tokens <= 0:
        return None
    return round(max(0.0, 1.0 - compiled_tokens / raw_tokens), 4)
