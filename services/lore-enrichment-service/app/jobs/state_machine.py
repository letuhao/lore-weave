"""Per-job STATE MACHINE (RAID C8).

Drives one ``enrichment_job`` through its lifecycle with the explicit
``estimate / start / pause / resume / cancel`` (+ ``complete`` / ``fail``)
transitions. Illegal transitions RAISE (never a silent no-op). State persists to
the C2 ``enrichment_job.status`` column; the state enum values are EXACTLY the
C2 ``status`` CHECK vocabulary so a persisted state is always schema-valid.

Locked transition DAG (states = C2 status vocabulary):

    pending     → estimating | cancelled
    estimating  → running    | cancelled | failed
    running     ⇄ paused
    running     → completed  | cancelled | failed
    paused      → running    | cancelled
    completed   → (terminal)
    cancelled   → (terminal)
    failed      → (terminal)

Boundaries (locked):
  * In-process only — NO Redis runner, NO orchestration (C14). This class owns
    transition legality + the status/timestamp/cost fields on the row; it does
    NOT schedule work.
  * NO LLM/model names, NO secrets. Persistence is a single parametrised UPDATE
    via an injected async executor (so unit tests run with a fake sink and no DB).
  * The pause transition carries a reason (``manual`` | ``cost_cap``) — the
    cost guardrail (C8) drives the ``cost_cap`` pause.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

__all__ = [
    "JobState",
    "PauseReason",
    "IllegalTransitionError",
    "JobRecord",
    "JobStateMachine",
    "PersistFn",
]


class JobState(str, Enum):
    """Lifecycle states — values mirror C2 ``enrichment_job.status`` EXACTLY."""

    PENDING = "pending"
    ESTIMATING = "estimating"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


# Terminal states have no outgoing transitions.
_TERMINAL: frozenset[JobState] = frozenset(
    {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}
)

# The legal transition DAG (single source of truth). Any (from, to) NOT listed
# here is illegal and raises.
_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.PENDING: frozenset({JobState.ESTIMATING, JobState.CANCELLED}),
    JobState.ESTIMATING: frozenset(
        {JobState.RUNNING, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.RUNNING: frozenset(
        {JobState.PAUSED, JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED}
    ),
    JobState.PAUSED: frozenset({JobState.RUNNING, JobState.CANCELLED}),
    JobState.COMPLETED: frozenset(),
    JobState.CANCELLED: frozenset(),
    JobState.FAILED: frozenset(),
}


class PauseReason(str, Enum):
    """Why a job was paused — drives the persisted ``error_message``/audit note.

    ``COST_CAP`` is set by the C8 cost guardrail when projected spend would
    breach the job's cap; ``MANUAL`` is an author/operator pause.
    """

    MANUAL = "manual"
    COST_CAP = "cost_cap"


class IllegalTransitionError(RuntimeError):
    """Raised on an attempt to make a transition not in the legal DAG."""

    def __init__(self, frm: JobState, to: JobState) -> None:
        super().__init__(
            f"illegal job transition {frm.value!r} -> {to.value!r} "
            f"(not in the lifecycle DAG)"
        )
        self.frm = frm
        self.to = to


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobRecord:
    """In-memory mirror of the C2 ``enrichment_job`` row this machine drives.

    Only the lifecycle-relevant columns are modelled. ``state`` is kept in sync
    with what was last persisted, so an assertion that in-memory == persisted is
    meaningful (the machine never advances ``state`` without persisting).
    """

    job_id: str
    state: JobState = JobState.PENDING
    pause_reason: PauseReason | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None
    # audit trail of (from, to) pairs — handy for tests + later observability.
    history: list[tuple[JobState, JobState]] = field(default_factory=list)


# An async persistence hook: given a record, write its lifecycle columns to the
# C2 ``enrichment_job`` row. Injected so unit tests use a fake sink and no DB.
PersistFn = Callable[[JobRecord], Awaitable[None]]


def _is_legal(frm: JobState, to: JobState) -> bool:
    return to in _TRANSITIONS.get(frm, frozenset())


class JobStateMachine:
    """Drives one :class:`JobRecord` through the lifecycle DAG.

    Every public transition validates legality FIRST (raising
    :class:`IllegalTransitionError` on an illegal move — no silent no-op),
    mutates the record, then persists via the injected hook. Because the in-
    memory ``state`` is only advanced after a successful persist call, the in-
    memory state always matches what was written.
    """

    def __init__(self, record: JobRecord, persist: PersistFn | None = None) -> None:
        self._record = record
        self._persist = persist

    @property
    def record(self) -> JobRecord:
        return self._record

    @property
    def state(self) -> JobState:
        return self._record.state

    def is_terminal(self) -> bool:
        return self._record.state in _TERMINAL

    def can(self, to: JobState) -> bool:
        """True iff a transition to ``to`` is legal from the current state."""
        return _is_legal(self._record.state, to)

    # ── explicit named transitions ────────────────────────────────────────────
    async def estimate(self) -> None:
        """pending → estimating."""
        await self._transition(JobState.ESTIMATING)

    async def start(self) -> None:
        """estimating → running (stamps ``started_at`` on first start)."""
        await self._transition(JobState.RUNNING)

    async def pause(self, reason: PauseReason = PauseReason.MANUAL) -> None:
        """running → paused, recording WHY (manual vs cost_cap)."""
        await self._transition(JobState.PAUSED, pause_reason=reason)

    async def resume(self) -> None:
        """paused → running (clears the pause reason)."""
        await self._transition(JobState.RUNNING)

    async def cancel(self) -> None:
        """→ cancelled (legal from pending/estimating/running/paused)."""
        await self._transition(JobState.CANCELLED)

    async def complete(self) -> None:
        """running → completed (terminal)."""
        await self._transition(JobState.COMPLETED)

    async def fail(self, error_message: str | None = None) -> None:
        """→ failed (legal from estimating/running); records the error."""
        await self._transition(JobState.FAILED, error_message=error_message)

    # ── core ──────────────────────────────────────────────────────────────────
    async def _transition(
        self,
        to: JobState,
        *,
        pause_reason: PauseReason | None = None,
        error_message: str | None = None,
    ) -> None:
        frm = self._record.state
        if not _is_legal(frm, to):
            # Illegal move RAISES — never a silent no-op (adversary focus).
            raise IllegalTransitionError(frm, to)

        now = _now()
        rec = self._record

        # field side-effects (timestamps + reason), applied before persist.
        if to is JobState.RUNNING:
            if rec.started_at is None:
                rec.started_at = now
            rec.pause_reason = None  # resuming/starting clears any pause reason
        elif to is JobState.PAUSED:
            rec.paused_at = now
            rec.pause_reason = pause_reason
            if pause_reason is not None:
                rec.error_message = f"paused: {pause_reason.value}"
        elif to in _TERMINAL:
            rec.completed_at = now
            if to is JobState.FAILED:
                rec.error_message = error_message

        prev = rec.state
        rec.state = to  # advance in-memory only after legality passed
        rec.history.append((prev, to))

        if self._persist is not None:
            try:
                await self._persist(rec)
            except Exception:
                # Persist failed — roll the in-memory state back so it never
                # diverges from what is actually stored (adversary: persisted ==
                # in-memory). Re-raise so the caller sees the failure.
                rec.state = prev
                rec.history.pop()
                raise
