"""PlanForge LLM client protocol — M2 replaces default impl with provider-registry."""

from __future__ import annotations

from typing import Any, Protocol


class LMStudioClient(Protocol):
    """Injected by tests (mock) or M2 production adapter."""

    def health_check(self) -> dict[str, Any]: ...

    def chat(
        self,
        *,
        step: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 8000,
    ) -> str: ...


class PlanForgeLLMNotConfiguredError(RuntimeError):
    pass


def default_llm_client(**_: Any) -> LMStudioClient:
    raise PlanForgeLLMNotConfiguredError(
        "PlanForge LLM requires model_ref via provider-registry (M2) — use mode=rules or pass a test client"
    )
