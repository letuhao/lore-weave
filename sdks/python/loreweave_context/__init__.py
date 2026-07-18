"""loreweave_context — the shared Context Budget Law Planner/Compiler kernel.

Extracts prompt-assembly + planning out of chat-service so it can be reused (roleplay,
composition) and so the Planner policy is a swappable, A/B-testable seam. Pure-Python: it
imports NO provider SDK (LLM/embeddings are injected ports) — provider-gate clean.

T3.1 ships the assembly renderer (`build_system_message`); later slices add CompilePlan /
Planner / Compiler / CompactionStrategy. See docs/plans/2026-07-04-t3-context-kernel.md.
"""
from loreweave_context.budget import compute_target, scale_by_window
from loreweave_context.compaction import (
    CompactionReport,
    CompactionStrategy,
    compact_messages,
)
from loreweave_context.plan import CompilePlan, Planner
from loreweave_context.system_message import build_system_message
from loreweave_context.tokens import (
    estimate_messages_tokens,
    estimate_tokens,
    split_to_token_budget,
)
from loreweave_context.trace import (
    PHASES,
    TIERS,
    TraceAccumulator,
    TraceSpan,
    reduction_pct,
)

__all__ = [
    "build_system_message",
    "compute_target",
    "scale_by_window",
    "CompilePlan",
    "Planner",
    "estimate_tokens",
    "estimate_messages_tokens",
    "split_to_token_budget",
    "compact_messages",
    "CompactionReport",
    "CompactionStrategy",
    "TraceSpan",
    "TraceAccumulator",
    "reduction_pct",
    "TIERS",
    "PHASES",
]
