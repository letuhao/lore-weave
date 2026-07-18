"""Track C — the RAIL DRIVER. **MOVED to the Agent Control Plane SDK (ACP A1).**

The implementation now lives in `loreweave_agent_control.rail` (a pure, stdlib-only module,
byte-identical to what used to be here). This module is a thin RE-EXPORT shim so every existing
`from app.services.rail_progress import ...` keeps working unchanged while chat-service becomes a
consumer of the shared SDK (ACP-8 dogfood). See docs/specs/2026-07-16-agent-control-plane-sdk.md.
"""
from __future__ import annotations

from loreweave_agent_control.rail import (  # noqa: F401 — re-export surface
    _STATE_LABELS,  # private, but an existing chat test imports it — keep the surface intact
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

__all__ = [
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
]
