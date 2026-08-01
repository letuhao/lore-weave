"""BYOK LLM adapter for PlanForge — provider-registry via composition LLMClient."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.llm_budget import max_tokens_for

logger = logging.getLogger(__name__)


#: ANTI-REPETITION — the fix for the failure that made this path look unreliable.
#:
#: Root-caused 2026-07-28 by capturing an actual failing response instead of theorising about it.
#: The tail was `0_0_0_0_0_0_0…` repeated to the token cap: the model falls into a DEGENERATE
#: REPETITION INSIDE A JSON STRING, runs out of budget mid-string, and leaves unbalanced JSON.
#:
#: A grammar cannot prevent this, and that is the important part. A JSON string is
#: quote-anything-quote, so an unbounded repetition is grammar-LEGAL — **schema enforcement
#: guarantees SHAPE, never TERMINATION.** Which is also why `maxItems` did nothing when it was
#: tried: the loop is inside ONE value, not across array members. Wrong lever.
#:
#: `provider-registry.forwardOptionalChatFields` has always passed `frequency_penalty` through. The
#: capability was there and unused, exactly as `response_format` was. Measured over 4 attempts at
#: the materialize step:
#:
#:     no penalty            2/4 valid   response sizes [819, 819, 12484, 32619]
#:     frequency_penalty .3  4/4 valid   response sizes [907, 1110, 1127, 2757]
#:
#: Strength measured per step rather than guessed. 0.3 cleared the materialize step (4/4) and did
#: NOT clear analyze, which is the longer generation:
#:
#:     analyze · none            2/3 valid   sizes [4095, 5146, 43447]
#:     analyze · frequency 0.3   2/3 valid   sizes [3314, 5794, 45453]
#:     analyze · frequency 0.8   3/3 valid   sizes [4474, 4609, 5614]
#:
#: 0.8 is high for structured output — the worry is that penalising repetition pushes the model away
#: from the repeated KEY NAMES a schema requires — so the content was checked, not assumed: arcs 3-4
#: and events 3-4 at 0.8, identical to the healthy runs at lower settings. No degradation observed.
_ANTI_LOOP = {"frequency_penalty": 0.8}


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
        # Sentinel, resolved below. The response is a whole planning package and its item
        # count is what the step is producing, so there is no truthful `target` to pass and
        # this site stays on the no-signal ratchet by design — see the resolution point.
        max_tokens: int | None = None,
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
        schema: dict[str, Any] | None = None,
        frequency_penalty: float | None = None,
    ) -> str:
        """One chat step. With `schema`, the shape is enforced by the DECODER where the provider
        supports it — `provider-registry.forwardOptionalChatFields` passes `response_format` through
        to LM Studio's grammar layer.

        This path is the ONE that works without the section classifier, and it was the only one that
        could not constrain its output: both steps asked for free text, hand-parsed it, and on a
        parse failure spent a SECOND 12,000-token call asking the model to repair its own JSON.

        A provider that REJECTS the schema falls back to free-form, so the worst case is exactly
        today's behaviour rather than a lost step.

        `frequency_penalty` overrides the default anti-loop strength. Callers raise it when a
        previous attempt came back as a repetition loop — the one lever that actually addresses that
        failure, since the grammar cannot forbid a loop inside a string."""
        # Resolved per call rather than as a default argument. Nothing here can pass a
        # `target`: this method serves every plan-forge step (analyze, materialize, refine,
        # elaborate, and each one's JSON repair), and the item count is precisely what the
        # step is generating. `language` is not read by STRUCTURED. So the row's measured
        # floor — 12000, sized for a whole planning package in one response — IS the answer,
        # and this site is left counted as backlog rather than cleared with a kwarg the kind
        # would discard.
        max_tokens = max_tokens or max_tokens_for("plan_forge_chat")
        check = cancel_check if cancel_check is not None else self._cancel_check
        anti_loop = dict(_ANTI_LOOP)
        if frequency_penalty is not None:
            anti_loop["frequency_penalty"] = frequency_penalty
        fmt: dict[str, Any] = {"type": "text"}
        if schema is not None:
            fmt = {"type": "json_schema",
                   "json_schema": {"name": step.replace(" ", "_")[:40] or "result",
                                   "schema": schema}}
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
                    "response_format": fmt,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **no_thinking_fields(),
                    **anti_loop,
                },
                job_meta={"usage_purpose": self._usage_purpose, "extractor": step},
                cancel_check=check,
            )
        except LLMError as exc:
            if schema is not None:
                # Schema support is not a platform requirement. Retrying once WITHOUT it covers both
                # a rejection and a transient failure, and a genuine outage fails again immediately —
                # which is cheaper than a message-shape heuristic that guesses which one it was.
                logger.info("plan_forge step=%s: schema rejected or call failed (%s) — "
                            "retrying free-form", step, exc)
                return await self.chat(step=step, system=system, user=user,
                                       temperature=temperature, max_tokens=max_tokens,
                                       cancel_check=cancel_check, schema=None)
            logger.warning("plan_forge LLM error step=%s: %s", step, exc)
            raise PlanForgeLLMError(str(exc)) from exc
        if job.status != "completed":
            raise PlanForgeLLMError(f"LLM job status={job.status}")
        content = extract_judge_content(job.result)
        if not content.strip():
            raise PlanForgeLLMError("empty LLM response")
        self._io_log.append(
                {
                    "step": step,
                    "prompt_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
                    "prompt_chars": len(user),
                    "response_chars": len(content),
                }
            )
        return content
