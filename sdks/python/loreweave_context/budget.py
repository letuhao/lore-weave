"""Task-elastic budget math (Context Budget Law D3 / T2), lifted into the kernel so the
Planner owns it. Pure arithmetic — no I/O, no provider SDK. chat-service's
`token_budget.compute_target` re-exports this for backward compatibility.
"""
from __future__ import annotations

# The soft target band as pure fractions of the model's context window — no absolute token
# cap on either end, so both ends scale with whatever window compute_target is actually
# called with. Two prior versions pinned an absolute cap (6K/32K, then 6K/200K) that went
# flat past some window size — every model above that size got the identical target
# regardless of how much bigger its real window was (a 1M-context model was clamped to the
# same number as a 267K one). `surface_max` tracks the ~50-80%-of-window band agentic
# harnesses use for a compaction trigger (Claude Code ~83.5%, general guidance 50-80%); 0.75
# also matches this codebase's own flat-mode fallback trigger (`compact_light_task_weight`
# off -> 0.75×window, see stream_service.py).
_TARGET_FLOOR_FRAC = 0.10
_TARGET_MAX_FRAC = 0.75


def compute_target(context_length: int | None, *, task_weight: float = 1.0) -> int | None:
    """The task-elastic soft budget target for a window. None when the window is unknown.
    `floor = 0.1×window`, `surface_max = 0.75×window`; target interpolates floor→surface_max
    by task_weight (clamped to [0,1])."""
    if not context_length or context_length <= 0:
        return None
    floor = int(_TARGET_FLOOR_FRAC * context_length)
    surface_max = int(_TARGET_MAX_FRAC * context_length)
    # NaN-safe (T2 review COSMETIC-2): a Planner bug producing a NaN task_weight must fail
    # SAFE = roomy (surface_max), never be silently masked as "lean" (floor) which would
    # over-compact. `nan != nan` is the portable NaN test.
    tw = 1.0 if task_weight != task_weight else min(1.0, max(0.0, task_weight))
    return int(floor + tw * (surface_max - floor))


def scale_by_window(flat_default: int, context_length: int | None, *, tuned_window: int = 200_000) -> int:
    """Scale a token/char budget that was tuned as a flat default against a
    `tuned_window`-sized model, so a caller with a genuinely larger context_length gets
    a proportionally bigger budget instead of the same flat number regardless of window
    (the exact bug class `compute_target`'s absolute-cap removal fixed, applied to the
    many smaller sub-budgets across the codebase — tool-surface hot-seed, steering,
    single-tool-result caps — that were each tuned as a flat constant against a mid-size
    window). Never smaller than `flat_default`: a model with a smaller or unknown window
    keeps today's already-deployed behavior; this only ever grows the budget."""
    if not context_length or context_length <= 0:
        return flat_default
    return max(flat_default, int(flat_default / tuned_window * context_length))
