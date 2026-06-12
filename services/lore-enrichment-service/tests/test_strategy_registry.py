"""C8 — strategy registry + feature-flags tests.

Pins the plugin framework's gate: P1 (`template`/`retrieval`) is active by
default and selectable; P2/P3 (`fabrication`/`recook`) register but are NOT
selectable nor listed until their tier's flag is flipped on (the C15 gate).

Adversary focus (brief): an INACTIVE technique MUST NOT leak via `list_active`
or `select`; unknown keys raise distinctly from inactive ones.
"""

from __future__ import annotations

import pytest

from app.strategies.base import (
    CostEstimate,
    EnrichmentStrategy,
    StrategyContext,
    Technique,
    Tier,
)
from app.strategies.feature_flags import (
    DEFAULT_ACTIVE_TECHNIQUES,
    load_feature_flags,
)
from app.strategies.registry import (
    InactiveStrategyError,
    StrategyRegistry,
    UnknownStrategyError,
)


# ── a trivial no-op stub strategy (scope: register/select only, no real body) ──
class _StubStrategy(EnrichmentStrategy):
    def __init__(self, technique: Technique, unit_cost: float = 1.0) -> None:
        self.technique = technique
        self._unit_cost = unit_cost

    def estimate_cost(self, gap_batch: list) -> CostEstimate:  # type: ignore[type-arg]
        n = len(gap_batch)
        return CostEstimate(
            technique=self.technique,
            gap_count=n,
            units=float(n),
            cost=self._unit_cost * n,
        )

    async def run(self, gap_batch, context: StrategyContext):  # noqa: ANN001
        return None  # deferred to C9/C10/C16/C17 — no body in C8


def _full_registry(flags=None) -> StrategyRegistry:
    reg = StrategyRegistry(flags=flags)
    for t in Technique:
        reg.register(_StubStrategy(t))
    return reg


# ── feature-flag defaults (Q-R2: P1 active, P2/P3 inactive) ───────────────────
def test_default_active_set_is_exactly_p1() -> None:
    # P1 (active by default) = template + retrieval + compose_draft (Compose mode D,
    # ungated — it expands the author's own draft). Derived from the tier table.
    assert DEFAULT_ACTIVE_TECHNIQUES == frozenset(
        {Technique.TEMPLATE, Technique.RETRIEVAL, Technique.COMPOSE_DRAFT}
    )
    # and those are exactly the P1 tier
    assert all(t.tier is Tier.P1 for t in DEFAULT_ACTIVE_TECHNIQUES)


def test_default_flags_p2_p3_off() -> None:
    flags = load_feature_flags(env={})
    assert flags.is_active(Technique.TEMPLATE)
    assert flags.is_active(Technique.RETRIEVAL)
    assert not flags.is_active(Technique.FABRICATION)  # P2
    assert not flags.is_active(Technique.RECOOK)  # P3


# ── registry select: active / inactive / unknown ─────────────────────────────
def test_select_active_p1_returns_strategy() -> None:
    reg = _full_registry()
    for t in (Technique.TEMPLATE, Technique.RETRIEVAL):
        strat = reg.select(t)
        assert strat.technique is t
        assert strat.tier is Tier.P1
    # string keys work too
    assert reg.select("template").technique is Technique.TEMPLATE


def test_select_inactive_p2_p3_raises_inactive_not_unknown() -> None:
    reg = _full_registry()  # default flags → P2/P3 dark
    for t in (Technique.FABRICATION, Technique.RECOOK):
        with pytest.raises(InactiveStrategyError):
            reg.select(t)
    # critically: it's a DISTINCT error from "unknown" — a registered-but-dark
    # technique must never be confused with a missing one (no bypass).
    assert not issubclass(InactiveStrategyError, UnknownStrategyError)


def test_select_unknown_key_raises_unknown() -> None:
    reg = _full_registry()
    with pytest.raises(UnknownStrategyError):
        reg.select("does-not-exist")


def test_select_registered_but_unknown_to_registry_is_unknown() -> None:
    # a known technique with NO registered strategy → unknown, not inactive
    reg = StrategyRegistry()  # nothing registered
    with pytest.raises(UnknownStrategyError):
        reg.select(Technique.TEMPLATE)


# ── list_active never leaks inactive techniques ──────────────────────────────
def test_list_active_excludes_inactive() -> None:
    reg = _full_registry()
    active = reg.list_active()
    keys = {s.technique for s in active}
    # P1 default-active set: template + retrieval + compose_draft (mode D, ungated).
    assert keys == {Technique.TEMPLATE, Technique.RETRIEVAL, Technique.COMPOSE_DRAFT}
    assert Technique.FABRICATION not in keys
    assert Technique.RECOOK not in keys
    # deterministic order = Technique declaration order (compose_draft is declared last)
    assert [s.technique for s in active] == [
        Technique.TEMPLATE, Technique.RETRIEVAL, Technique.COMPOSE_DRAFT
    ]


def test_list_registered_shows_all_but_does_not_imply_selectable() -> None:
    reg = _full_registry()
    assert {s.technique for s in reg.list_registered()} == set(Technique)
    # still cannot select the dark ones
    with pytest.raises(InactiveStrategyError):
        reg.select(Technique.FABRICATION)


def test_is_active_helper() -> None:
    reg = _full_registry()
    assert reg.is_active(Technique.TEMPLATE)
    assert not reg.is_active(Technique.FABRICATION)
    assert not reg.is_active("nonsense")  # unknown → not active, no raise


# ── the C15 gate: flipping a tier on makes it selectable (and ONLY then) ──────
def test_gate_can_activate_p2_via_override() -> None:
    gated = load_feature_flags(overrides={Technique.FABRICATION: True})
    reg = _full_registry(flags=gated)
    # now selectable
    assert reg.select(Technique.FABRICATION).technique is Technique.FABRICATION
    assert Technique.FABRICATION in {s.technique for s in reg.list_active()}
    # P3 still dark (only fabrication was flipped)
    with pytest.raises(InactiveStrategyError):
        reg.select(Technique.RECOOK)


def test_env_var_can_disable_a_p1_default() -> None:
    # fail-safe: env can turn a default-on technique OFF
    flags = load_feature_flags(env={"ENRICH_STRATEGY_TEMPLATE_ENABLED": "0"})
    reg = _full_registry(flags=flags)
    with pytest.raises(InactiveStrategyError):
        reg.select(Technique.TEMPLATE)
    assert reg.select(Technique.RETRIEVAL).technique is Technique.RETRIEVAL


def test_unrecognised_env_token_falls_back_to_default() -> None:
    # garbage env value must NOT silently enable a dark P2/P3 (fail closed)
    flags = load_feature_flags(env={"ENRICH_STRATEGY_FABRICATION_ENABLED": "maybe"})
    assert not flags.is_active(Technique.FABRICATION)
    # ...nor disable a P1 default
    flags2 = load_feature_flags(env={"ENRICH_STRATEGY_TEMPLATE_ENABLED": "???"})
    assert flags2.is_active(Technique.TEMPLATE)


# ── registration guards ──────────────────────────────────────────────────────
def test_double_register_same_technique_rejected() -> None:
    reg = StrategyRegistry()
    reg.register(_StubStrategy(Technique.TEMPLATE))
    with pytest.raises(ValueError):
        reg.register(_StubStrategy(Technique.TEMPLATE))


# ── strategy interface: key/tier derive from technique (no hand-set tier) ─────
def test_strategy_key_and_tier_derive_from_technique() -> None:
    s = _StubStrategy(Technique.RETRIEVAL)
    assert s.key == "retrieval"
    assert s.tier is Tier.P1
    assert Technique.FABRICATION.tier is Tier.P2
    assert Technique.RECOOK.tier is Tier.P3


def test_estimate_cost_is_pure_and_scales() -> None:
    s = _StubStrategy(Technique.TEMPLATE, unit_cost=2.5)
    est = s.estimate_cost([object(), object(), object()])
    assert est.cost == pytest.approx(7.5)
    assert est.gap_count == 3
    assert est.technique is Technique.TEMPLATE
