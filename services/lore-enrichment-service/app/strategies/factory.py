"""Gate-aware strategy FACTORY (RAID C16, DEFERRED-054 enforcement).

This is the LOAD-BEARING enforcement that closes the C14-shape trap flagged in
DEFERRED-054: before C16, the C15 eval gate was TRUST-BASED — ``gate.py``'s
``gated_feature_flags`` had ZERO app callers and only a read-only gate-status
route shipped, so nothing actually stopped a future P2/P3 path from calling
``load_feature_flags(overrides={FABRICATION: True})`` and bypassing the gate.

C16 makes the gate ENFORCED, not advisory: ALL P2 (fabrication) — and later P3
(recook) — strategy selection MUST be constructed through ONE factory that reads
the LIVE gate-status (the latest persisted ``enrichment_eval_runs`` for the
project, the exact source the ``/internal/eval/{project}/gate-status`` route
exposes) and REFUSES to activate the higher-cost tier when the gate is LOCKED.

The contract (proven by tests):
  * gate LOCKED (no eval run, or latest run ``passed=False``) → the registry this
    factory builds has P2/P3 forced OFF, so ``registry.select('fabrication')``
    raises :class:`~app.strategies.registry.InactiveStrategyError`. A job that
    asks for fabrication is REFUSED — it never silently activates.
  * gate CLEARED (latest run ``passed=True``) → fabrication BECOMES selectable
    (subject to its per-technique flag/override, exactly like P1's env flags).

Crucially, the factory does NOT accept a caller-supplied ``FABRICATION: True``
override that bypasses the gate: the gate decision is applied AFTER any base
overrides via :func:`~app.eval.gate.gated_feature_flags`, which FORCES every
non-P1 technique OFF when the gate has not passed (overriding the override). So
there is no ``load_feature_flags(overrides={FABRICATION: True})`` escape hatch —
the only way fabrication activates is a real, persisted, passing eval run.

NO model names, NO LLM/HTTP here — the factory only reads the gate signal (via an
injected, async ``GateStatusReader``) and wires the C8 registry. The concrete
reader that hits the DB (``EvalRunsRepo``) lives in :mod:`app.strategies.gate_reader`
so this module stays I/O-free + trivially unit-testable with a fake reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable, Mapping

from app.strategies.base import EnrichmentStrategy, Technique, Tier
from app.strategies.registry import StrategyRegistry

if TYPE_CHECKING:  # type-only — the runtime import is deferred (see note below)
    from app.eval.gate import GateDecision

# NOTE: ``app.eval.gate`` is imported LAZILY inside the functions that need it
# (not at module top) to break a circular import: ``app.eval.gate`` imports
# ``app.strategies.base``, which triggers the ``app.strategies`` package
# ``__init__`` (it re-exports this factory) — importing the gate at top here
# would re-enter ``app.eval.gate`` while it is still initialising. The gate
# module is fully loaded by the time these functions run, so the deferred import
# is safe and adds no measurable overhead.

__all__ = [
    "LiveGateStatus",
    "GateStatusReader",
    "GateAwareStrategyFactory",
    "decision_from_gate_status",
]


@dataclass(frozen=True)
class LiveGateStatus:
    """The live P2/P3 gate signal read from the latest persisted eval run.

    Mirrors the fields the ``/internal/eval/{project}/gate-status`` route returns
    (the canonical gate surface). ``p2_p3_unlocked`` is the load-bearing field:
    True ONLY when an eval has run for this (project, suite_version) AND it passed
    the gate. ``has_run=False`` → ``p2_p3_unlocked=False`` (fail-CLOSED — no eval
    yet can never be a false-green).
    """

    has_run: bool
    p2_p3_unlocked: bool
    suite_version: str
    composite: float | None = None
    passed: bool | None = None

    @classmethod
    def locked(cls, suite_version: str) -> "LiveGateStatus":
        """The fail-closed default: no eval run → gate LOCKED."""
        return cls(
            has_run=False,
            p2_p3_unlocked=False,
            suite_version=suite_version,
            composite=None,
            passed=False,
        )


#: Injected async reader: (user_id, project_id, suite_version) → the live gate
#: status. The production impl reads the latest ``enrichment_eval_runs`` row via
#: ``EvalRunsRepo.get_latest`` (see :mod:`app.strategies.gate_reader`); tests pass
#: a deterministic stub. It MUST fail CLOSED (return a LOCKED status) on any read
#: error — a DB outage can never unlock the higher-cost tier.
GateStatusReader = Callable[[str, str, str], Awaitable[LiveGateStatus]]


def decision_from_gate_status(status: LiveGateStatus) -> GateDecision:
    """Project a :class:`LiveGateStatus` onto the C15 :class:`GateDecision` shape.

    The factory reuses the EXISTING ``gated_feature_flags`` enforcement (which
    forces non-P1 OFF when ``not decision.passed``), so it needs a GateDecision.
    The decision's ``passed`` is exactly ``status.p2_p3_unlocked`` — the persisted
    gate verdict — so the enforcement is driven by real eval data, never a fresh
    re-score here. The composite/reasons are carried for audit only.
    """
    from app.eval.gate import GateDecision  # lazy — see module note

    if status.p2_p3_unlocked:
        reasons: list[str] = []
    elif not status.has_run:
        reasons = ["no eval run for this project/suite — gate LOCKED (fail-closed)"]
    else:
        reasons = [
            f"latest eval run did not pass the gate "
            f"(composite={status.composite}) — P2/P3 LOCKED"
        ]
    return GateDecision(
        passed=status.p2_p3_unlocked,
        composite=float(status.composite) if status.composite is not None else 0.0,
        min_composite=0.0,  # the threshold was applied at persist time (C15 gate)
        reasons=reasons,
    )


class GateAwareStrategyFactory:
    """Builds a gate-enforced :class:`StrategyRegistry` for P2/P3 selection.

    This is the SINGLE construction path any caller (the job runner, the API)
    MUST use to obtain a registry capable of selecting a P2 (fabrication) or P3
    (recook) strategy. It:

      1. reads the LIVE gate status (latest persisted eval run for the project),
      2. derives a :class:`GateDecision` from it,
      3. builds the C8 feature-flags via :func:`~app.eval.gate.gated_feature_flags`
         — which FORCES every non-P1 technique OFF unless the gate passed,
      4. constructs a :class:`StrategyRegistry` over those flags and registers the
         supplied strategies.

    Because step 3 reuses the C15 enforcement, a caller cannot smuggle
    fabrication on with a ``base_override``: when the gate is locked, the override
    is overridden OFF. The ONLY way fabrication is selectable from this factory is
    a real, persisted, passing eval run for the project.
    """

    def __init__(
        self,
        *,
        gate_reader: GateStatusReader,
        strategies: list[EnrichmentStrategy],
        suite_version: str = "enrichment-v1",
    ) -> None:
        self._gate_reader = gate_reader
        self._strategies = list(strategies)
        self._suite_version = suite_version

    async def read_gate(self, *, user_id: str, project_id: str) -> LiveGateStatus:
        """Read the live gate status for a project (fail-closed on read error).

        Any exception from the injected reader is swallowed into a LOCKED status —
        a DB outage / unreachable eval store can NEVER unlock the higher-cost tier
        (the conservative cost-discipline posture, Q-R2)."""
        try:
            return await self._gate_reader(
                user_id, project_id, self._suite_version
            )
        except Exception:  # noqa: BLE001 — fail CLOSED on any read error
            return LiveGateStatus.locked(self._suite_version)

    async def build_registry(
        self,
        *,
        user_id: str,
        project_id: str,
        base_overrides: Mapping[Technique, bool] | None = None,
    ) -> StrategyRegistry:
        """Construct the gate-enforced registry for (user, project).

        Reads the live gate, applies the C15 enforcement to the flags, and returns
        a registry with all supplied strategies registered.

        When the gate is LOCKED, every non-P1 technique is forced OFF (the C15
        ``gated_feature_flags`` enforcement) so ``select`` raises
        ``InactiveStrategyError`` — fabrication cannot activate.

        When the gate is CLEARED, this factory's PURPOSE is to make its managed
        higher-tier strategies selectable, so it DEFAULTS to enabling the non-P1
        techniques it holds (a passed gate is precisely the signal that unlocks
        them — Q-R2). A caller's explicit ``base_overrides`` takes precedence over
        this default, so an operator can still keep a specific tier dark even
        after the gate clears. (The C15 ``gated_feature_flags`` only FORCES values
        when the gate FAILED; on a pass it honours these overrides as-is.)"""
        from app.eval.gate import gated_feature_flags  # lazy — see module note

        status = await self.read_gate(user_id=user_id, project_id=project_id)
        decision = decision_from_gate_status(status)

        # On a PASSED gate, default-enable the non-P1 techniques this factory
        # manages (its whole reason to exist), then let explicit overrides win.
        overrides: dict[Technique, bool] = {}
        if decision.passed:
            for strategy in self._strategies:
                if strategy.technique.tier is not Tier.P1:
                    overrides[strategy.technique] = True
        if base_overrides:
            overrides.update(base_overrides)

        flags = gated_feature_flags(decision, base_overrides=overrides)
        registry = StrategyRegistry(flags=flags)
        for strategy in self._strategies:
            registry.register(strategy)
        return registry

    async def select(
        self,
        technique: str | Technique,
        *,
        user_id: str,
        project_id: str,
        base_overrides: Mapping[Technique, bool] | None = None,
    ) -> EnrichmentStrategy:
        """Gate-enforced selection of a strategy for a project.

        The convenience path the runner uses: build the gate-enforced registry and
        ``select`` in one call. A P2/P3 technique while the gate is LOCKED raises
        :class:`~app.strategies.registry.InactiveStrategyError` — fabrication is
        REFUSED, never silently activated (DEFERRED-054)."""
        registry = await self.build_registry(
            user_id=user_id,
            project_id=project_id,
            base_overrides=base_overrides,
        )
        return registry.select(technique)
