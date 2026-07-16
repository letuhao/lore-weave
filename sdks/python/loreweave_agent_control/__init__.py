"""loreweave_agent_control — the Agent Control Plane SDK (Python).

The consumable control/governance primitives extracted from chat-service + knowledge-service
so any agent-runtime speaks one surface (spec: docs/specs/2026-07-16-agent-control-plane-sdk.md).
ACP A1 lands the PURE compute (no I/O): the rail verdict-machine + the executive state-merge.
The stateful pieces (the executive's I/O `run_executive`, the drive harness) stay consumer-side
and call into this. Behavior is byte-identical to the originals (RW-2 goldens guard it).
"""
from __future__ import annotations

from .rail import (
    BOOK_STATE_KEYS,
    DRIVE,
    ENFORCE,
    NUDGE,
    OFF,
    RAIL_OPTIONAL_NUDGE_CAP,
    RAIL_REQUIRED_NUDGE_CAP,
    STOP_ASYNC,
    STOP_DONE,
    STOP_UNKNOWN,
    STOP_USER,
    BookState,
    RailProgress,
    StepProgress,
    compute_rail_progress,
    enforcement_for,
    honest_giveup_directive,
    next_actionable_step,
    nudge_cap_for,
    parse_done_when,
    redrive_directive,
    render_book_state,
    render_progress_block,
    step_is_required,
    user_abandoned_rail,
)
from .state_merge import (
    EXECUTIVE_MAX_TURN_CHARS,
    EXECUTIVE_MAX_TURNS,
    EXECUTIVE_SYSTEM_PROMPT,
    build_messages,
    merge_state,
)

__all__ = [
    # rail — verdict machine + progress + directives
    "BOOK_STATE_KEYS",
    "BookState",
    "RailProgress",
    "StepProgress",
    "compute_rail_progress",
    "next_actionable_step",
    "parse_done_when",
    "render_book_state",
    "render_progress_block",
    "redrive_directive",
    "honest_giveup_directive",
    "user_abandoned_rail",
    "step_is_required",
    "nudge_cap_for",
    "enforcement_for",
    "DRIVE",
    "STOP_DONE",
    "STOP_USER",
    "STOP_ASYNC",
    "STOP_UNKNOWN",
    "ENFORCE",
    "NUDGE",
    "OFF",
    "RAIL_REQUIRED_NUDGE_CAP",
    "RAIL_OPTIONAL_NUDGE_CAP",
    # state_merge — the executive's pure parts
    "merge_state",
    "build_messages",
    "EXECUTIVE_SYSTEM_PROMPT",
    "EXECUTIVE_MAX_TURNS",
    "EXECUTIVE_MAX_TURN_CHARS",
]
