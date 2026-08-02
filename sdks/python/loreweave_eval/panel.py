"""JudgePanel — the registered judge-ensemble config (track phase Q0-0b).

Before this, the identity of the extractor + filter models (the ones that must
be EXCLUDED from the disjoint median-of-record to avoid self-reinforcement) was
scattered across module constants in ``compute_ensemble_macros.py`` and the
``KNOWLEDGE_EXTRACTOR_MODEL`` / ``KNOWLEDGE_FILTER_MODEL`` env vars, plus the
ensemble UUIDs in ``deepeval_metrics`` / ``run_rejudge_resumable``. That scatter
is a drift risk (memory: anti-self-reinforcement must be enforced in code, not a
manual env step).

A ``JudgePanel`` makes the panel composition + the exclusion set a single
first-class value that travels with a scored run. The production-shaped DB row
(track phase Q1 ``judge_panel`` table) mirrors these fields.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

# Historical production defaults (the qwen-30b extractor + qwen3.6-35b filter).
# Kept here as the single source of truth; compute_ensemble_macros re-exports
# them under their old private names for back-compat.
DEFAULT_EXTRACTOR_REF = "019e6a20-eeac-7b96-82ee-69a16d8ef68d"  # qwen-30b extractor
DEFAULT_FILTER_REF = "019e5650-eca7-78c2-985d-465aa3bce1ce"  # qwen3.6-35b filter


@dataclass(frozen=True)
class JudgePanel:
    """Which judge models form the ensemble, and which to EXCLUDE from the
    disjoint metric-of-record because they also extract/filter (self-grading).

    ``judge_model_refs`` is optional metadata (the panel composition); the
    load-bearing fields for the metric are the two exclude refs. ``excluded``
    is the set fed to the disjoint-median computation.
    """

    extractor_exclude_ref: str | None = None
    filter_exclude_ref: str | None = None
    judge_model_refs: tuple[str, ...] = field(default_factory=tuple)
    #: S13 — True when BOTH exclude refs came from the hardcoded production defaults below
    #: rather than from this deployment's environment.
    #:
    #: Those defaults are `user_model_id`s, and this repo's own rule is that a
    #: `user_model_id` is PER-MACHINE — a hardcoded table "sends the next developer to a 404
    #: or to someone else's row". So on any deployment but the one they were minted on, the
    #: exclusion set matches nothing, the real extractor stays in the panel grading its own
    #: output, and `panel_safety` used to call that `safe=True, no generator in panel` — the
    #: same words it uses for a genuinely clean panel.
    #:
    #: The defaults are KEPT: removing them would break the byte-identical guarantee
    #: `panel_from_env` makes to existing callers. What changes is that a defaulted set can
    #: no longer be mistaken for a verified one.
    exclusion_is_defaulted: bool = False

    @property
    def excluded(self) -> set[str]:
        return {
            ref
            for ref in (self.extractor_exclude_ref, self.filter_exclude_ref)
            if ref
        }

    def role_of(self, judge_uuid: str) -> str:
        """Classify a judge as ``extractor`` / ``filter`` / ``independent``."""
        if judge_uuid and judge_uuid == self.extractor_exclude_ref:
            return "extractor"
        if judge_uuid and judge_uuid == self.filter_exclude_ref:
            return "filter"
        return "independent"


def panel_from_env(env: Mapping[str, str] | None = None) -> JudgePanel:
    """Resolve a JudgePanel from the environment, preserving the historical
    ``KNOWLEDGE_EXTRACTOR_MODEL`` / ``KNOWLEDGE_FILTER_MODEL`` overrides and the
    hardcoded production defaults. With no env set, ``excluded`` equals the old
    inline ``{_DEFAULT_EXTRACTOR_UUID, _DEFAULT_FILTER_UUID}`` set — so callers
    that switch to this produce byte-identical results.
    """
    e = env if env is not None else os.environ
    # Whether the deployment SAID anything, tracked separately from the resolved value. The
    # value alone cannot distinguish "this box's real extractor" from "a UUID minted on
    # someone else's box", and that distinction is the difference between an exclusion that
    # works and one that silently excludes nobody.
    defaulted = "KNOWLEDGE_EXTRACTOR_MODEL" not in e and "KNOWLEDGE_FILTER_MODEL" not in e
    return JudgePanel(
        extractor_exclude_ref=e.get("KNOWLEDGE_EXTRACTOR_MODEL", DEFAULT_EXTRACTOR_REF),
        filter_exclude_ref=e.get("KNOWLEDGE_FILTER_MODEL", DEFAULT_FILTER_REF),
        exclusion_is_defaulted=defaulted,
    )
