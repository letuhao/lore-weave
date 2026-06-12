"""Config-driven feature-flags gating which techniques are ACTIVE (RAID C8).

Q-R2 phased rollout: P1 (``template`` + ``retrieval``) is active by default; P2
(``fabrication``) and P3 (``recook``) register but stay INACTIVE until the C15
cost/quality gate. The flags are the single switch the registry consults — an
inactive technique is neither listed nor selectable.

Source of truth precedence (most → least specific):
  1. an explicit override map passed to :func:`load_feature_flags` (tests / the
     C15 gate flipping a tier on);
  2. per-technique env vars ``ENRICH_STRATEGY_<TECHNIQUE>_ENABLED`` (``1``/``0``,
     ``true``/``false``, case-insensitive);
  3. the locked default: P1 on, P2/P3 off.

NO model names, NO secrets here — only boolean enablement. Conservative default
(P2/P3 OFF) is the H0/cost-discipline guardrail: a misconfig fails CLOSED.

Note: feature flags live in ``app/strategies/`` (not ``app/config/``) because
``app/config.py`` already exists as the settings module — a ``config/`` package
would shadow it. Cohesion with the registry/base is also tighter here.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from app.strategies.base import Technique, Tier

__all__ = [
    "DEFAULT_ACTIVE_TECHNIQUES",
    "FeatureFlags",
    "load_feature_flags",
]


# ── locked default (Q-R2): exactly the P1 techniques are active ───────────────
#    Derived from the technique→tier table so "P1 == active by default" can never
#    drift from the tier mapping in base.py.
DEFAULT_ACTIVE_TECHNIQUES: frozenset[Technique] = frozenset(
    t for t in Technique if t.tier is Tier.P1
)

_ENV_PREFIX = "ENRICH_STRATEGY_"
_ENV_SUFFIX = "_ENABLED"
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


def _parse_bool(raw: str) -> bool | None:
    """Parse an env flag to a bool, or ``None`` if it is not a recognised token
    (so an unparseable value falls through to the next precedence level rather
    than silently enabling/disabling a tier)."""
    v = raw.strip().lower()
    if v in _TRUTHY:
        return True
    if v in _FALSY:
        return False
    return None


class FeatureFlags(BaseModel):
    """Immutable enablement map over the four techniques.

    Resolved once at load time. The registry asks :meth:`is_active` for every
    ``list_active``/``select`` decision; nothing mutates a loaded instance.
    """

    model_config = ConfigDict(frozen=True)

    active: frozenset[Technique]

    def is_active(self, technique: Technique) -> bool:
        return technique in self.active

    def active_techniques(self) -> tuple[Technique, ...]:
        """Active techniques in fixed ``Technique`` declaration order
        (deterministic — never set-iteration order)."""
        return tuple(t for t in Technique if t in self.active)


def load_feature_flags(
    *,
    overrides: Mapping[Technique, bool] | None = None,
    env: Mapping[str, str] | None = None,
) -> FeatureFlags:
    """Resolve the active-technique set from defaults ← env ← overrides.

    For each technique the default (P1 on / P2-P3 off) is taken first, then a
    recognised env var flips it, then an explicit override flips it last. A
    misconfigured env value (unrecognised token) is ignored — the technique
    keeps its default, so the system fails CLOSED for P2/P3.
    """
    env = os.environ if env is None else env
    overrides = overrides or {}

    active: set[Technique] = set()
    for technique in Technique:
        enabled = technique in DEFAULT_ACTIVE_TECHNIQUES  # locked default
        env_raw = env.get(f"{_ENV_PREFIX}{technique.name}{_ENV_SUFFIX}")
        if env_raw is not None:
            parsed = _parse_bool(env_raw)
            if parsed is not None:
                enabled = parsed
        if technique in overrides:
            enabled = overrides[technique]
        if enabled:
            active.add(technique)
    return FeatureFlags(active=frozenset(active))
