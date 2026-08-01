"""Auto reasoning ("thinking") mode — composition's domain scorer + the one wire-field seam.

The GENERIC policy lives in the `loreweave_llm` SDK (reusable across services):
`infer_reasoning_control`, `bucket_effort`, `resolve_reasoning`, `reasoning_fields`,
`directive_from_parts`, `ReasoningDirective`. Composition keeps only the creative-writing
scorer here. See docs/specs/2026-06-05-auto-reasoning-mode.md.

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

...then pass that DIRECTIVE down — never a bare effort string. A bare string cannot carry
`chat_template_kwargs`, so every path that threaded one silently half-applied the decision.
"""

from typing import Any

from loreweave_llm import ReasoningDirective, no_thinking_fields, reasoning_fields

from app.reasoning.policy import ReasoningSignals, score_effort

__all__ = ["ReasoningSignals", "score_effort", "wire_fields"]


def wire_fields(reasoning: ReasoningDirective | None) -> dict[str, Any]:
    """Provider wire fields for a resolved directive — the ONLY place composition turns a
    reasoning decision into request fields.

    `None` means "no directive was resolved on this path", and it SUPPRESSES rather than
    omitting. That asymmetry is deliberate and is the fix for a live incident: the streaming
    draft path treated a missing directive as "send nothing", inherited the model's own chat
    template, and returned an empty draft after spending the entire output budget on hidden
    reasoning — billed, and reported as success. A forgotten directive must degrade to the
    safe answer, not to the model's default.

    Lives here (not in `app.engine.*`) so `cowrite`, `select` and `stitch` can all reach it
    without an import cycle — the shape that let three copies drift apart in the first place.
    """
    return reasoning_fields(reasoning) if reasoning is not None else no_thinking_fields()
