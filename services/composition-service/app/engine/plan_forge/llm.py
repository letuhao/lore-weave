"""BYOK LLM adapter for PlanForge — provider-registry via composition LLMClient."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)

_NO_THINK = {
    "reasoning_effort": "none",
    "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
}


class PlanForgeLLMError(RuntimeError):
    """Non-retryable PlanForge LLM failure (caller maps to job failed)."""


class ProviderPlanForgeLLM:
    """Async chat client — explicit model_ref required (no planner default)."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        user_id: str,
        model_source: str,
        model_ref: str,
        usage_purpose: str = "plan_forge",
        io_log: list[dict[str, Any]] | None = None,
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._llm = llm
        self._user_id = user_id
        self._model_source = model_source
        self._model_ref = model_ref
        self._usage_purpose = usage_purpose
        self._io_log = io_log if io_log is not None else []
        self._cancel_check = cancel_check

    @property
    def io_log(self) -> list[dict[str, Any]]:
        return self._io_log

    async def chat(
        self,
        *,
        step: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 8000,
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> str:
        check = cancel_check if cancel_check is not None else self._cancel_check
        try:
            job = await self._llm.submit_and_wait(
                user_id=self._user_id,
                operation="chat",
                model_source=self._model_source,
                model_ref=self._model_ref,
                input={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "text"},
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **_NO_THINK,
                },
                job_meta={"usage_purpose": self._usage_purpose, "extractor": step},
                cancel_check=check,
            )
        except LLMError as exc:
            logger.warning("plan_forge LLM error step=%s: %s", step, exc)
            raise PlanForgeLLMError(str(exc)) from exc
        if job.status != "completed":
            raise PlanForgeLLMError(f"LLM job status={job.status}")
        content = extract_judge_content(job.result)
        if not content.strip():
            raise PlanForgeLLMError("empty LLM response")
        if self._io_log is not None:
            self._io_log.append(
                {
                    "step": step,
                    "prompt_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
                    "prompt_chars": len(user),
                    "response_chars": len(content),
                }
            )
        return content
