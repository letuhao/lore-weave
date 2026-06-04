"""Top-level reasoning resolver (§Architecture.3).

Combines the user preference + the model's reasoning-control style + the chosen
engine into a concrete `ReasoningDirective` the co-write stream sends. This is the
one place the policy lives, so the router stays thin.

Rules:
- An explicit user choice (off/low/medium/high) ALWAYS wins — the author override.
- "auto":
    - adaptive model → pass through (let it self-decide; we don't out-think it).
    - effort  model → run the engine (rule_based now; llm_judge is a V1 seam).
    - none    model → no-op (reasoning_effort is meaningless).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.reasoning.capability import ReasoningControl
from app.reasoning.policy import Effort, ReasoningSignals, score_effort

UserReasoningPref = Literal["off", "auto", "low", "medium", "high"]
EngineKind = Literal["rule_based", "llm_judge"]


@dataclass(frozen=True)
class ReasoningDirective:
    """What the stream should send. `effort=None` + `passthrough=True` means omit
    reasoning_effort entirely (let an adaptive model decide). `source` is for the
    SSE `job` frame so the UI can show how the decision was made."""
    effort: Effort | None
    passthrough: bool
    source: str  # "user" | "adaptive" | "rule_based" | "llm_judge" | "non_reasoning"


def resolve_reasoning(
    *,
    user_pref: UserReasoningPref,
    model_control: ReasoningControl,
    signals: ReasoningSignals,
    engine: EngineKind = "rule_based",
) -> ReasoningDirective:
    # 1. Explicit author override — highest priority, regardless of model.
    if user_pref == "off":
        return ReasoningDirective(effort="none", passthrough=False, source="user")
    if user_pref in ("low", "medium", "high"):
        return ReasoningDirective(effort=user_pref, passthrough=False, source="user")  # type: ignore[arg-type]

    # 2. Auto — let the model's capability pick the strategy.
    if model_control == "adaptive":
        # Anthropic/Gemini already self-orchestrate — pass through, don't classify.
        return ReasoningDirective(effort=None, passthrough=True, source="adaptive")
    if model_control == "effort":
        if engine == "llm_judge":
            # V1 seam — not implemented; fall back to the rule-based scorer so
            # "auto" never silently degrades to model-default.
            return ReasoningDirective(effort=score_effort(signals), passthrough=False, source="rule_based")
        return ReasoningDirective(effort=score_effort(signals), passthrough=False, source="rule_based")

    # 3. Non-reasoning model — reasoning_effort is a no-op.
    return ReasoningDirective(effort=None, passthrough=False, source="non_reasoning")
