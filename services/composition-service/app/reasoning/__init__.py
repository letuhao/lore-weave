"""Auto reasoning ("thinking") mode — capability-aware strategy resolver.

See docs/specs/2026-06-05-auto-reasoning-mode.md. Three pure pieces:
- `capability.infer_reasoning_control` — how a registered model wants reasoning
  controlled (adaptive / effort / none), inferred from provider + model name.
- `policy.score_effort` — the rule-based "when to think" scorer for `effort`
  models (no extra LLM call), over signals the packer already computes.
- `resolve.resolve_reasoning` — combines the user preference + model capability
  + engine into a concrete directive the co-write stream sends.
"""

from app.reasoning.capability import ReasoningControl, infer_reasoning_control
from app.reasoning.policy import ReasoningSignals, score_effort
from app.reasoning.resolve import ReasoningDirective, UserReasoningPref, resolve_reasoning

__all__ = [
    "ReasoningControl",
    "infer_reasoning_control",
    "ReasoningSignals",
    "score_effort",
    "ReasoningDirective",
    "UserReasoningPref",
    "resolve_reasoning",
]
