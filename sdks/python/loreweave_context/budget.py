"""Task-elastic budget math (Context Budget Law D3 / T2), lifted into the kernel so the
Planner owns it. Pure arithmetic — no I/O, no provider SDK. chat-service's
`token_budget.compute_target` re-exports this for backward compatibility.
"""
from __future__ import annotations

# The soft target band as fractions of (and caps on) the model's context window. A grounding
# turn sits near `surface_max`; a status-op near `floor`. Raise `_TARGET_MAX_CAP` if a
# heavy-context task needs more than ~32K of headroom on a big-window model.
_TARGET_FLOOR_CAP = 6_000
_TARGET_FLOOR_FRAC = 0.10
_TARGET_MAX_CAP = 32_000
_TARGET_MAX_FRAC = 0.35


def compute_target(context_length: int | None, *, task_weight: float = 1.0) -> int | None:
    """The task-elastic soft budget target for a window. None when the window is unknown.
    `floor = min(6K, 0.1×window)`, `surface_max = min(32K, 0.35×window)`; target interpolates
    floor→surface_max by task_weight (clamped to [0,1])."""
    if not context_length or context_length <= 0:
        return None
    floor = min(_TARGET_FLOOR_CAP, int(_TARGET_FLOOR_FRAC * context_length))
    surface_max = min(_TARGET_MAX_CAP, int(_TARGET_MAX_FRAC * context_length))
    surface_max = max(surface_max, floor)  # tiny windows: keep the band non-inverted
    # NaN-safe (T2 review COSMETIC-2): a Planner bug producing a NaN task_weight must fail
    # SAFE = roomy (surface_max), never be silently masked as "lean" (floor) which would
    # over-compact. `nan != nan` is the portable NaN test.
    tw = 1.0 if task_weight != task_weight else min(1.0, max(0.0, task_weight))
    return int(floor + tw * (surface_max - floor))
