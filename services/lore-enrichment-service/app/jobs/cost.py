"""Per-job COST BUDGET with a reserved eval-cost line (RAID C14, M5).

Wraps the C8 :class:`~app.jobs.cost_guardrail.CostGuardrail` and adds the locked
**reserved eval-cost budget line** (M5): a fraction of the per-job cap is held
back for the (C15) eval pass so the enrichment pipeline can never consume the
budget the eval will need. The guardrail then enforces against the REDUCED
working cap (``cap − eval_reserve``); a breach of the working cap PAUSES the job
(via the C8 state machine, reason ``cost_cap``) — never crashes, never silently
overruns into the eval reserve.

This module owns ONLY the budget arithmetic + the reserve split. It re-uses the
C8 guardrail's off-by-one contract (``would_exceed`` strictly greater than the
cap; landing exactly ON the cap is allowed) verbatim — no new enforcement logic.

Boundaries (locked):
  * Cost is UNIT-OPAQUE (token budget / eval calls) — same opaque unit as the
    strategy ``CostEstimate.cost`` and the job's ``max_spend`` cap. NO currency.
  * The eval reserve is NOT spent here (C14 does not run eval — that is C15). It
    is RESERVED: held out of the working cap so it is guaranteed available later.
  * NO I/O of its own beyond delegating the pause to the injected C8 guardrail /
    state machine. NO model names, NO secrets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.jobs.cost_guardrail import CostCapExceeded, CostGuardrail
from app.jobs.state_machine import JobStateMachine
from app.strategies.base import CostEstimate, Technique

if TYPE_CHECKING:  # avoid a runtime import cycle (gap model imported lazily)
    from app.gaps.model import Gap

__all__ = [
    "DEFAULT_EVAL_RESERVE_FRACTION",
    "RETRIEVAL_GAP_COST",
    "GENERATION_GAP_COST",
    "PER_GAP_WORKING_COST",
    "CostCapExceeded",  # re-exported so callers import the pause signal from here
    "EvalReserveError",
    "GapCostModel",
    "JobCostBudget",
]

#: Default fraction of the per-job cap reserved for the (C15) eval pass (M5).
#: 15% leaves the bulk for enrichment while guaranteeing the eval can run.
DEFAULT_EVAL_RESERVE_FRACTION: float = 0.15

# ── the REAL per-gap cost in TOKENS (C1, DEFERRED-052) ────────────────────────
# A P1 gap does TWO billable calls: one retrieval query-embed (C10, the embed
# seam) + one LLM completion (C11, the generation seam). The cost UNIT is now
# REAL TOKENS (PO ruling, audit C1) — consistent with how the platform's other
# features (chat / knowledge) meter spend (provider-registry bills input+output
# (+reasoning) tokens). These constants are the CONSERVATIVE PRE-CHARGE per gap:
# charged BEFORE the gap so a runaway local-LLM job is PAUSED by the cap before
# unbounded overshoot; the runner then RECONCILES to the ACTUAL tokens after the
# gap (harvested from the LLM ``usage`` frame + the embed query estimate, via the
# per-job ``UsageMeter`` → ``JobCostBudget.reconcile``). A reconcile down refunds
# headroom; a reconcile up may overshoot one gap (the eval-reserve absorbs it).
#
# The old values (1.0 + 4.0 opaque units) modelled "work units", not tokens —
# the cap could not be set in a unit consistent with the rest of the platform.
#: Conservative per-gap embed-query token PRE-CHARGE (one /internal/embed call;
#: the query is a short name + dimension labels — tens of CJK tokens).
RETRIEVAL_GAP_COST: float = 64.0
#: Conservative per-gap generation token PRE-CHARGE (one /internal/llm/stream
#: call: the grounding-citing prompt + the completion). Generation dominates, so
#: it carries the larger share. Reconciled to the real ``usage`` count after.
GENERATION_GAP_COST: float = 1200.0
#: Per-gap working PRE-CHARGE in tokens = embed query + generation.
PER_GAP_WORKING_COST: float = RETRIEVAL_GAP_COST + GENERATION_GAP_COST


class GapCostModel:
    """The REAL per-gap cost estimator the runner charges against the cap.

    Quacks like the slice of :class:`~app.strategies.base.EnrichmentStrategy`
    the runner uses (``estimate_cost``), but — unlike ``TemplateStrategy`` (whose
    estimate models the FREE scaffold, cost 0.0) — it returns the NON-ZERO cost
    of the real P1 work per gap: one retrieval query-embed (C10) + one LLM
    completion (C11). This is what makes the per-job cost-cap actually bite: a
    runaway local-LLM job is paused before it overshoots, because each gap now
    has a real, positive charge.

    Cost is provider-agnostic and denominated in REAL TOKENS (C1, DEFERRED-052) —
    the same unit the platform's other features meter in. The estimate is a
    conservative PRE-charge per gap (charged before the gap runs, so the cap can
    pause a runaway BEFORE it incurs the next gap's LLM call). Pure +
    side-effect-free.

    C1 (DEFERRED-052) RESOLVED for P1: the runner now RECONCILES this pre-charge
    to the ACTUAL tokens after each gap (harvested from the LLM ``usage`` frame +
    the embed-query estimate via the per-job ``UsageMeter`` →
    ``JobCostBudget.reconcile``), still checking the cap BEFORE the next gap.
    P2/P3 (fabrication multi-pass, recook re-generate) still pre-charge their own
    opaque per-gap estimate and are NOT yet token-reconciled — they are gate-
    locked (not live); wiring their meter-reconcile is tracked for gate
    activation. See docs/deferred/DEFERRED.md (#052 resolved-for-P1, #059 P2/P3).
    """

    technique = Technique.RETRIEVAL

    def __init__(
        self,
        *,
        retrieval_gap_cost: float = RETRIEVAL_GAP_COST,
        generation_gap_cost: float = GENERATION_GAP_COST,
    ) -> None:
        if retrieval_gap_cost < 0 or generation_gap_cost < 0:
            raise ValueError("per-gap costs must be >= 0")
        self._retrieval = retrieval_gap_cost
        self._generation = generation_gap_cost

    @property
    def per_gap_cost(self) -> float:
        """The non-zero cost charged for one gap (embed + LLM completion)."""
        return self._retrieval + self._generation

    def estimate_cost(self, gap_batch: list["Gap"]) -> CostEstimate:
        """Project the real cost of enriching ``gap_batch`` (embed + LLM / gap).

        Returns a :class:`CostEstimate` whose ``cost`` is ``per_gap_cost * n`` —
        the runner accumulates it against the working cap BEFORE each gap, so a
        breach pauses the job. NON-ZERO by construction (the inert-cap fix)."""
        n = len(gap_batch)
        return CostEstimate(
            technique=self.technique,
            gap_count=n,
            units=float(n),
            cost=self.per_gap_cost * n,
        )


class EvalReserveError(ValueError):
    """Raised on a nonsensical eval-reserve configuration (fraction out of
    range, or an explicit reserve larger than the cap)."""


class JobCostBudget:
    """A per-job budget = a C8 guardrail over (cap − reserved eval line).

    Construct with the job's full ``cap`` (opaque unit). The eval reserve is
    either an explicit absolute amount (``eval_reserve``) or a fraction of the
    cap (``eval_reserve_fraction``, default 15%). The pipeline guardrail enforces
    against the WORKING cap = ``cap − eval_reserve``; a working-cap breach pauses
    the job. The eval reserve stays untouched for C15.

    An uncapped job (``cap is None``) reserves nothing and never blocks — the
    eval line is meaningless without a finite cap.
    """

    def __init__(
        self,
        cap: float | None,
        *,
        eval_reserve: float | None = None,
        eval_reserve_fraction: float = DEFAULT_EVAL_RESERVE_FRACTION,
        spent: float = 0.0,
    ) -> None:
        if not 0.0 <= eval_reserve_fraction < 1.0:
            raise EvalReserveError(
                f"eval_reserve_fraction must be in [0, 1) (got {eval_reserve_fraction})"
            )
        self._cap = cap
        if cap is None:
            # Uncapped: no reserve, no working cap, guardrail never blocks.
            self._eval_reserve = 0.0
            self._guard = CostGuardrail(None, spent=spent)
            return

        if cap < 0:
            raise EvalReserveError(f"cap must be >= 0 (got {cap})")

        reserve = (
            float(eval_reserve)
            if eval_reserve is not None
            else cap * eval_reserve_fraction
        )
        if reserve < 0:
            raise EvalReserveError(f"eval_reserve must be >= 0 (got {reserve})")
        if reserve > cap:
            raise EvalReserveError(
                f"eval_reserve ({reserve}) cannot exceed the cap ({cap})"
            )
        self._eval_reserve = reserve
        working_cap = cap - reserve
        self._guard = CostGuardrail(working_cap, spent=spent)

    # ── introspection ──────────────────────────────────────────────────────────
    @property
    def cap(self) -> float | None:
        """The full per-job cap (working cap + eval reserve), or None if uncapped."""
        return self._cap

    @property
    def eval_reserve(self) -> float:
        """The amount held back for the (C15) eval pass (M5)."""
        return self._eval_reserve

    @property
    def working_cap(self) -> float | None:
        """The cap the pipeline guardrail enforces against (cap − eval reserve)."""
        return self._guard.cap

    @property
    def spent(self) -> float:
        """Pipeline spend so far (does NOT include the reserved eval line)."""
        return self._guard.spent

    @property
    def remaining(self) -> float | None:
        """Pipeline headroom under the working cap, or None if uncapped."""
        return self._guard.remaining

    @property
    def guardrail(self) -> CostGuardrail:
        """The underlying C8 guardrail (for callers that want the raw control)."""
        return self._guard

    def would_exceed(self, next_cost: float) -> bool:
        """True iff charging ``next_cost`` would breach the WORKING cap (the eval
        reserve is protected). Delegates the C8 off-by-one contract verbatim."""
        return self._guard.would_exceed(next_cost)

    def charge(self, next_cost: float) -> bool:
        """Charge a unit against the working cap (pure accounting). Returns False
        and adds nothing if it would dip into the eval reserve / breach the cap."""
        return self._guard.charge(next_cost)

    def reconcile(self, delta: float) -> None:
        """Reconcile the working spend by ``delta`` after a gap ran (C1, token
        metering). Delegates to the guardrail's unconditional
        :meth:`~app.jobs.cost_guardrail.CostGuardrail.record_actual`: the gap
        already executed, so the REAL token delta (actual − pre-charged estimate)
        is recorded even if it overshoots the working cap (the eval-reserve
        absorbs a one-gap overshoot; the next pre-charge then pauses). A negative
        ``delta`` refunds headroom when the gap under-ran its estimate."""
        self._guard.record_actual(delta)

    async def charge_or_pause(
        self, next_cost: float, machine: JobStateMachine
    ) -> None:
        """Charge ``next_cost`` against the working cap; if it would breach (i.e.
        eat into the reserved eval line), PAUSE the job (cost_cap) before incurring
        it and raise :class:`CostCapExceeded`. The C15 eval reserve is never
        spent by the pipeline — it is guaranteed available."""
        await self._guard.charge_or_pause(next_cost, machine)
