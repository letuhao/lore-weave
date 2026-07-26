"""Graded-reasoning wire fields for the extraction submit builders.

D-KG-WORKER-GRADED-EFFORT — the four per-op submit builders
(`build_{entity,relation,event,fact}_submit_kwargs`) spread the resolved
reasoning wire fields into the LLM `input` so a stored extraction effort
(low/medium/high) actually reaches the provider.

The contract is **byte-identical for the default** — `reasoning_effort="none"`
(or None) returns `{}` so every pre-existing caller (translation-service +
knowledge-service pass2 consumers that never pass the param) builds the
exact same `input` dict it did before. Only a graded value low/medium/high
emits the wire fields.

worker-ai does NO model-capability dispatch (exactly like translation's
worker), so this uses a direct ``source="user"`` directive rather than
``resolve_reasoning`` — the effort on the job row was already clamped to
the caller's grant at mint time (knowledge-side), so the runner trusts it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["reasoning_wire_fields"]


def reasoning_wire_fields(reasoning_effort: str | None) -> dict[str, Any]:
    """Wire `input` fragments for a graded extraction effort.

    Returns ``{}`` for the default/absent case (``None`` or ``"none"``) so
    callers that don't opt in stay byte-identical — note this differs from
    ``loreweave_llm.reasoning.reasoning_fields(effort="none")``, which emits
    an explicit *disable* (`thinking:False`); here a "none" job means "no
    graded effort requested", which must add nothing to the dict.

    A graded value (``"low"``/``"medium"``/``"high"``) returns
    ``{reasoning_effort, chat_template_kwargs}`` via the shared SDK resolver.
    """
    if not reasoning_effort or reasoning_effort == "none":
        return {}
    # Local import keeps the module-load graph identical for the default path
    # and matches the SDK's lazy-import convention elsewhere.
    from loreweave_llm.reasoning import ReasoningDirective, reasoning_fields

    return reasoning_fields(
        ReasoningDirective(effort=reasoning_effort, passthrough=False, source="user")  # type: ignore[arg-type]
    )
