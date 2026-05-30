"""Per-job COST GUARDRAIL (RAID C8) — estimate → enforce cap → pause before overrun.

The guardrail accumulates a job's *projected* spend against a per-job cap and
pauses the job (via the C8 state machine, reason ``cost_cap``) BEFORE the next
unit would breach the cap — never retroactively after an overrun. This is the
Q-R2 "cost discipline" control: conservative, fail-safe, autonomous.

Off-by-one contract (adversary focus — tested explicitly):
  * ``would_exceed(next_cost)`` is checked BEFORE the unit is charged. It is
    True iff ``spent + next_cost > cap`` (STRICTLY greater). Landing exactly ON
    the cap (``spent + next_cost == cap``) is ALLOWED — the cap is the maximum
    permitted spend, not a forbidden value.
  * ``charge`` refuses to push spend past the cap: if the unit would exceed, it
    does NOT add the spend and signals the caller to pause.

Boundaries (locked):
  * Cost is UNIT-OPAQUE (token budget, eval calls, …) — same unit as the
    strategy's :class:`~app.strategies.base.CostEstimate.cost` and the job's
    ``max_spend`` cap. NO currency assumption, NO model names.
  * NO I/O of its own beyond delegating the pause to the injected state machine.
"""

from __future__ import annotations

from app.jobs.state_machine import JobStateMachine, PauseReason

__all__ = [
    "CostCapExceeded",
    "CostGuardrail",
]


class CostCapExceeded(RuntimeError):
    """Raised by :meth:`CostGuardrail.charge_or_pause` when a unit cannot be
    charged without breaching the cap (after the job has been paused)."""

    def __init__(self, spent: float, attempted: float, cap: float) -> None:
        super().__init__(
            f"cost cap would be exceeded: spent={spent} + attempted={attempted} "
            f"> cap={cap}; job paused (cost_cap)"
        )
        self.spent = spent
        self.attempted = attempted
        self.cap = cap


class CostGuardrail:
    """Accumulates projected spend against a per-job cap.

    ``cap`` is the maximum permitted spend (same opaque unit as the strategy
    cost estimate). ``None`` means "no cap configured" — the guardrail then
    never blocks (the cost ceiling is enforced elsewhere / not set for this job).
    A negative cap is rejected; a zero cap means "allow no spend" (any positive
    unit pauses immediately).
    """

    def __init__(self, cap: float | None, *, spent: float = 0.0) -> None:
        if cap is not None and cap < 0:
            raise ValueError(f"cost cap must be >= 0 (got {cap})")
        if spent < 0:
            raise ValueError(f"initial spend must be >= 0 (got {spent})")
        self._cap = cap
        self._spent = float(spent)

    @property
    def cap(self) -> float | None:
        return self._cap

    @property
    def spent(self) -> float:
        return self._spent

    @property
    def remaining(self) -> float | None:
        """Headroom left under the cap, or ``None`` when uncapped."""
        if self._cap is None:
            return None
        return self._cap - self._spent

    def would_exceed(self, next_cost: float) -> bool:
        """True iff charging ``next_cost`` next would push spend STRICTLY over
        the cap. Checked BEFORE charging (projected, not retroactive). Always
        False when uncapped. Landing exactly on the cap is allowed (==, not >)."""
        if next_cost < 0:
            raise ValueError(f"next_cost must be >= 0 (got {next_cost})")
        if self._cap is None:
            return False
        return (self._spent + next_cost) > self._cap

    def charge(self, next_cost: float) -> bool:
        """Try to charge one unit's projected cost.

        Returns True and adds the spend if it fits under the cap (or uncapped);
        returns False and adds NOTHING if it would exceed (so accumulated spend
        never passes the cap). Pure accounting — does not touch the job state.
        """
        if self.would_exceed(next_cost):
            return False
        self._spent += next_cost
        return True

    async def charge_or_pause(
        self,
        next_cost: float,
        machine: JobStateMachine,
    ) -> None:
        """Charge ``next_cost`` if it fits; otherwise PAUSE the job (cost_cap)
        BEFORE incurring it and raise :class:`CostCapExceeded`.

        This is the enforcement entrypoint a (later C14) runner calls before
        each unit of work: the job is paused at the cap boundary, never allowed
        to overrun. The pause goes through the C8 state machine so the persisted
        ``status`` becomes ``paused`` with reason ``cost_cap``.
        """
        if self.charge(next_cost):
            return
        # `charge` only refuses when `would_exceed` is True, which is only ever
        # True for a configured (non-None) cap — so `self._cap` is set here.
        assert self._cap is not None  # noqa: S101 — invariant, not user input
        # Would exceed → pause first (state machine persists status=paused), then
        # signal the caller. Pausing a job not in `running` will itself raise an
        # IllegalTransitionError, surfacing a misuse rather than hiding it.
        await machine.pause(reason=PauseReason.COST_CAP)
        raise CostCapExceeded(self._spent, next_cost, self._cap)
