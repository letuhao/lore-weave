"""Strategy REGISTRY (RAID C8) — register-by-key + feature-flag-gated lookup.

A technique registers exactly one :class:`~app.strategies.base.EnrichmentStrategy`
under its key (the technique value). Lookup is gated by the C8 feature-flags:

  * :meth:`list_active` returns only strategies whose technique is ACTIVE per the
    flags (P1 by default), in fixed technique order.
  * :meth:`select` returns a strategy ONLY if it is registered AND active —
    a registered-but-inactive technique (P2/P3 until the C15 gate) raises
    :class:`InactiveStrategyError`; an unregistered/unknown key raises
    :class:`UnknownStrategyError`. There is NO path that returns an inactive
    strategy, so P2/P3 cannot leak out before the gate.

The registry holds no model names and performs no I/O. Flags are injected (not
read from a global) so the C15 gate / tests can flip a tier on deterministically.
"""

from __future__ import annotations

from app.strategies.base import EnrichmentStrategy, Technique
from app.strategies.feature_flags import FeatureFlags, load_feature_flags

__all__ = [
    "StrategyRegistry",
    "UnknownStrategyError",
    "InactiveStrategyError",
]


class UnknownStrategyError(KeyError):
    """Raised when a key has no registered strategy (typo / not-yet-built)."""


class InactiveStrategyError(PermissionError):
    """Raised when a registered strategy's technique is gated OFF by the flags.

    A distinct, non-KeyError type so callers can tell "no such technique" from
    "that technique exists but is dark until the gate" — and so a feature-flag
    bypass is impossible to mistake for a missing-key fall-through.
    """


class StrategyRegistry:
    """In-memory registry of techniques → strategies, gated by feature-flags.

    Construct with the active feature-flags (defaults to the locked P1-only set).
    Registration is independent of activation: P2/P3 strategies SHOULD be
    registered so the gate can later activate them, but they stay unselectable
    until their tier's flag is on.
    """

    def __init__(self, flags: FeatureFlags | None = None) -> None:
        self._flags: FeatureFlags = flags if flags is not None else load_feature_flags()
        self._by_key: dict[Technique, EnrichmentStrategy] = {}

    # ── registration ────────────────────────────────────────────────────────
    def register(self, strategy: EnrichmentStrategy) -> None:
        """Register ``strategy`` under its technique. Re-registering the same
        technique is rejected (a technique has at most one strategy) so a typo
        can't silently shadow an active strategy."""
        technique = strategy.technique
        if technique in self._by_key:
            raise ValueError(
                f"technique {technique.value!r} already has a registered strategy"
            )
        self._by_key[technique] = strategy

    # ── lookup (flag-gated) ───────────────────────────────────────────────────
    def select(self, key: str | Technique) -> EnrichmentStrategy:
        """Return the active strategy for ``key``.

        Raises :class:`UnknownStrategyError` if the key is not a known technique
        or has no registered strategy, and :class:`InactiveStrategyError` if the
        technique is registered but gated OFF. NEVER returns an inactive
        strategy — the only way to get one out is to activate its tier's flag.
        """
        technique = self._coerce(key)
        strategy = self._by_key.get(technique)
        if strategy is None:
            raise UnknownStrategyError(
                f"no strategy registered for technique {technique.value!r}"
            )
        if not self._flags.is_active(technique):
            raise InactiveStrategyError(
                f"technique {technique.value!r} (tier {technique.tier.value}) is "
                f"inactive — gated off until the C15 cost/quality gate"
            )
        return strategy

    def is_active(self, key: str | Technique) -> bool:
        """True iff ``key`` is a known, registered, AND flag-active technique."""
        try:
            technique = self._coerce(key)
        except UnknownStrategyError:
            return False
        return technique in self._by_key and self._flags.is_active(technique)

    def list_active(self) -> list[EnrichmentStrategy]:
        """Registered AND active strategies, in fixed technique order.

        Inactive (P2/P3 pre-gate) strategies are NEVER included, so this can be
        safely surfaced to a UI / job planner without leaking dark techniques.
        """
        return [
            self._by_key[t]
            for t in Technique
            if t in self._by_key and self._flags.is_active(t)
        ]

    def list_registered(self) -> list[EnrichmentStrategy]:
        """ALL registered strategies (active or not), in fixed technique order.

        For introspection/ops only — does NOT imply selectability. ``select`` /
        ``list_active`` remain the only flag-gated access paths.
        """
        return [self._by_key[t] for t in Technique if t in self._by_key]

    # ── internal ──────────────────────────────────────────────────────────────
    @staticmethod
    def _coerce(key: str | Technique) -> Technique:
        if isinstance(key, Technique):
            return key
        try:
            return Technique(key)
        except ValueError as exc:
            raise UnknownStrategyError(
                f"{key!r} is not a known technique"
            ) from exc
