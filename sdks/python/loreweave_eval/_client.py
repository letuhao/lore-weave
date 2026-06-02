"""Structural client contract the LLM judge needs — the lift seam (Q0).

`llm_judge` originally annotated its injected client as
`app.clients.llm_client.LLMClient` (a knowledge-service wrapper). That made
the eval code import a knowledge-service internal purely for a type
annotation — the client was ALWAYS passed in as a function parameter, never
constructed here.

To lift the judge into a shared SDK package consumed by BOTH knowledge-service
(R&D today) and learning-service (the online-eval consumer, track phase Q4),
we depend on a `Protocol` instead of the concrete wrapper. Any object exposing
a compatible `submit_and_wait` — knowledge-service's `LLMClient`,
learning-service's future client, or a test double — satisfies it
structurally. Runtime behavior is unchanged (annotation-only swap).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class JudgeJob(Protocol):
    """The terminal job shape the judge reads: ``status`` + ``result``.

    Satisfied by ``loreweave_llm.models.Job`` (and knowledge-service's
    wrapper return) without modification.
    """

    status: str
    result: dict[str, Any] | None


@runtime_checkable
class JudgeLLMClient(Protocol):
    """The single method the judge calls — ``submit_and_wait`` for one
    gateway chat completion.

    A concrete client with MORE optional parameters (e.g. knowledge-service's
    ``LLMClient`` also accepts ``trace_id``) still satisfies this Protocol;
    structural typing only requires the parameters the judge actually passes.
    """

    async def submit_and_wait(
        self,
        *,
        user_id: str,
        operation: str,
        model_source: str,
        model_ref: str,
        input: dict[str, Any],
        chunking: Any | None = None,
        job_meta: dict[str, Any] | None = None,
        transient_retry_budget: int = 1,
    ) -> JudgeJob: ...
