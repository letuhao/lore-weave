"""K16.1 — Extraction job state machine (KSA §8.4).

Pure validation layer for the K10.4 `extraction_jobs` row status
transitions. Callers (K16.3 start endpoint, K16.4 pause/resume/cancel
endpoints, K16.6 worker-ai task runner) invoke `validate_transition`
BEFORE touching `ExtractionJobsRepo.update_status` so an invalid
transition is rejected with a clear `StateTransitionError` instead
of silently becoming a row-not-found `None` return.

**Why a separate layer instead of pushing rules into the repo:**
K10.4's repo already has a narrow terminal-lock rail
(`WHERE status NOT IN ('complete','cancelled','failed')`) which is
sufficient for the budget-critical `try_spend` path. A richer state
machine belongs in the application layer because:

  1. The repo is the user-isolation boundary and must stay small
     for security review. Adding a matrix of valid transitions
     would bloat the SQL and obscure the multi-tenancy filters.
  2. The worker-ai runner needs to distinguish `paused_user` (don't
     auto-resume) from `paused_budget` (can auto-resume when the
     monthly budget rolls over) from `paused_error` (needs manual
     investigation). Encoding those semantics in SQL CASE branches
     would be fragile; a Python matrix is reviewable.
  3. The `pause_reason` is represented as a *modifier* on the
     existing single `paused` status rather than a schema change.
     The DB schema stays stable; K16.1 is purely application logic.

**Pause-reason representation:** the K10.4 schema has a single
`paused` status, not three. K16.1 introduces the `PauseReason`
discriminator as an *argument* to the transition validator. Code
that wants to store the reason persistently can stash it in the
existing `error_message` column with a `[budget]` / `[user]` /
`[error]` prefix, or wait for a future migration to add a
`pause_reason` column. Either way, the validator only cares about
the *rules* — it does not touch storage.

**Reference:** KSA §8.4 state machine, K16.1 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import logging
from typing import Literal

__all__ = [
    "JobStatus",
    "PauseReason",
    "StateTransitionError",
    "TERMINAL_STATES",
    "validate_transition",
    "is_terminal",
]

logger = logging.getLogger(__name__)


# Kept in sync with
# `app.db.repositories.extraction_jobs.JobStatus`. Duplicated rather
# than imported to keep this module free of a repo dependency — the
# state machine is pure and unit-testable without asyncpg.
JobStatus = Literal[
    "pending", "running", "paused", "complete", "failed", "cancelled"
]

# Reasons a job can be in the `paused` state. KSA §8.4 distinguishes
# these three because the worker-ai auto-resume policy differs:
#   - `user`:   user hit pause manually; NEVER auto-resume.
#   - `budget`: monthly cap hit; auto-resume when cap rolls over.
#   - `error`:  unhandled worker exception; requires manual
#               investigation, never auto-resume.
PauseReason = Literal["user", "budget", "error"]


TERMINAL_STATES: frozenset[JobStatus] = frozenset(
    {"complete", "failed", "cancelled"}
)


class StateTransitionError(ValueError):
    """Raised when a caller attempts an invalid status transition.

    Subclasses `ValueError` so existing FastAPI exception handlers
    that map ValueError to 400 Bad Request handle it without extra
    wiring, while the class name lets callers pattern-match in
    tests and logs.
    """


# The valid-transition matrix. A row is "from this status, you may
# transition to any status in this set". An empty set marks a
# terminal state.
#
# Rules encoded (KSA §8.4):
#   - pending → running (worker picks up)
#   - pending → cancelled (user cancels before worker starts)
#   - running → paused (with reason), complete, failed, cancelled
#   - paused → running (resume), cancelled
#   - complete/failed/cancelled → {} (terminal)
#
# Note: `running → running` and `paused → paused` are NOT self-loops
# — a worker that wants to update progress calls `advance_cursor`,
# which is a different repo method that does not touch status.
_VALID_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"paused", "complete", "failed", "cancelled"}),
    "paused": frozenset({"running", "cancelled", "failed"}),
    "complete": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def is_terminal(status: JobStatus) -> bool:
    """True if `status` is a terminal state. Terminal jobs cannot
    be transitioned out of; the retry use case is served by creating
    a new job (cleaner audit trail, no try_spend revival risk)."""
    return status in TERMINAL_STATES


def validate_transition(
    current: JobStatus,
    new: JobStatus,
    *,
    pause_reason: PauseReason | None = None,
    trace_id: str | None = None,
) -> None:
    """Validate a status transition and log it.

    Args:
        current: the job's current status.
        new: the target status.
        pause_reason: REQUIRED when `new == "paused"`, FORBIDDEN
            otherwise. Enforces the KSA §8.4 invariant that a
            paused row always carries a reason discriminator.
        trace_id: optional request/worker trace id for the log
            line. The K16 acceptance criteria explicitly require
            every transition to be logged with a trace id.

    Raises:
        StateTransitionError: if `current → new` is not in the
            valid-transition matrix, if `current` is terminal, or
            if the `pause_reason` contract is violated.
    """
    if is_terminal(current):
        raise StateTransitionError(
            f"cannot transition out of terminal state '{current}' "
            f"(attempted → '{new}'); create a new job instead"
        )

    allowed = _VALID_TRANSITIONS.get(current)
    if allowed is None:
        raise StateTransitionError(
            f"unknown current status '{current}'"
        )
    if new not in allowed:
        raise StateTransitionError(
            f"invalid transition '{current}' → '{new}'; "
            f"allowed targets: {sorted(allowed)}"
        )

    if new == "paused":
        if pause_reason is None:
            raise StateTransitionError(
                "transition to 'paused' requires a pause_reason "
                "(one of: user, budget, error)"
            )
    else:
        if pause_reason is not None:
            raise StateTransitionError(
                f"pause_reason is only valid for transitions to "
                f"'paused', not '{new}'"
            )

    logger.info(
        "K16.1: job transition %s → %s%s trace_id=%s",
        current,
        new,
        f" reason={pause_reason}" if pause_reason else "",
        trace_id or "<unset>",
    )
