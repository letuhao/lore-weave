"""Auto reasoning ("thinking") mode — composition's domain scorer.

The GENERIC policy now lives in the `loreweave_llm` SDK (reusable across services):
`infer_reasoning_control`, `bucket_effort`, `resolve_reasoning`, `ReasoningDirective`.
Composition keeps only the creative-writing scorer here. See
docs/specs/2026-06-05-auto-reasoning-mode.md.

Typical use at the /generate call site:

    from loreweave_llm import infer_reasoning_control, resolve_reasoning
    from app.reasoning import ReasoningSignals, score_effort

    control = infer_reasoning_control(model_kind, model_name, flags)
    directive = resolve_reasoning(
        user_pref=body.reasoning,
        model_control=control,
        auto_effort=score_effort(signals),
        auto_source="rule_based",
    )
"""

from app.reasoning.policy import ReasoningSignals, score_effort

__all__ = ["ReasoningSignals", "score_effort"]
