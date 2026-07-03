"""Single-shot structured LLM generation — the shared plumbing under every
NON-agentic "generate" pipeline (schema-propose, wiki-gen, bio/profile-suggest,
summarize, working-memory…).

Every such engine hand-rolls the SAME sequence: build a chat input, disable hidden
reasoning so a reasoning model doesn't burn its output budget on thinking (the
"empty-prose footgun"), `submit_and_wait`, check the job completed, dig the text out
of ``result["messages"][0]["content"]``, and raise a clear error on empty output.
`structured_generate` owns that 80%; the caller keeps the domain-specific 20% (which
pydantic model, which salvage) by parsing the returned ``content`` with its own model
(reuse `parse_json_object` for the tolerant fence/prose-stripping extraction).

This is the AI-Task Standard's BE half (see docs/specs/2026-07-03-ai-task-standard.md).
It is NOT the agentic path — an agent-facing MCP tool wraps an engine that calls this,
per the Agent Extensibility Standard; it never duplicates this plumbing.

Model resolution is the caller's: it passes a BYOK ``model_ref`` (a ``user_model`` id)
resolved via provider-registry (no hardcoded model). The ``llm_client`` is any object
satisfying the per-service ``submit_and_wait`` protocol (unchanged).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from loreweave_llm.models import Job, ReasoningEffort
from loreweave_llm.reasoning import ReasoningDirective, reasoning_fields


class StructuredGenerateError(Exception):
    """The single-shot LLM call failed, ended non-completed, or returned empty
    output. A router maps this to a clean 502 (upstream/model error)."""


@dataclass(frozen=True)
class GenerateResult:
    """The raw completion plus the terminal job (for usage / finish_reason /
    job_meta). Most callers only touch ``.content``."""

    content: str
    job: Job


def _as_directive(reasoning: ReasoningEffort | ReasoningDirective) -> ReasoningDirective:
    if isinstance(reasoning, ReasoningDirective):
        return reasoning
    # a bare effort string ("none"/"low"/"medium"/"high") is an explicit user-style
    # choice; "none" => reasoning_fields emits chat_template_kwargs.{thinking:false}
    # (the footgun disable), which is why "none" is the safe default.
    return ReasoningDirective(effort=reasoning, passthrough=False, source="user")


def no_thinking_fields() -> dict[str, Any]:
    """Wire fields that DISABLE hidden reasoning (the empty-prose footgun disable:
    ``reasoning_effort="none"`` + ``chat_template_kwargs.{thinking:false}``) for a
    structured / one-shot call. For call sites that build their OWN job ``input``
    directly (not via ``structured_generate``) but still need the footgun closed —
    spread ``**no_thinking_fields()`` into ``input``."""
    return reasoning_fields(_as_directive("none"))


def parse_json_object(raw: str) -> dict[str, Any]:
    """Pull a JSON object out of an LLM completion, tolerating ```json fences and
    leading/trailing prose. Raises StructuredGenerateError if nothing parses.

    Consolidates the ~5 divergent private ``_extract_json_object`` copies. Callers
    then ``Model.model_validate(...)`` (with their own per-field salvage if wanted)."""
    s = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    if not s.startswith("{"):
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            s = m.group(0)
    try:
        obj = json.loads(s)
    except (json.JSONDecodeError, TypeError) as exc:
        raise StructuredGenerateError(f"output was not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise StructuredGenerateError("output JSON was not an object")
    return obj


def _content_of(job: Job) -> str:
    result = job.result or {}
    messages = result.get("messages") or []
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        return messages[0].get("content", "") or ""
    return ""


async def structured_generate(
    llm_client: Any,
    *,
    user_id: str,
    model_ref: str,
    messages: list[dict[str, str]],
    max_output_tokens: int,
    model_source: str = "user_model",
    reasoning: ReasoningEffort | ReasoningDirective = "none",
    temperature: float = 0.3,
    job_meta: dict[str, Any] | None = None,
    transient_retry_budget: int = 1,
    trace_id: str | None = None,
) -> GenerateResult:
    """Run one chat completion and return its text.

    - ``reasoning="none"`` (default) DISABLES hidden thinking so a reasoning model
      (Gemma-4, Qwen3, R1…) doesn't spend the whole ``max_output_tokens`` on hidden
      reasoning and return empty prose. Pass ``"medium"``/``"high"`` or a
      ``ReasoningDirective`` when graded effort is wanted.
    - ``max_output_tokens`` is REQUIRED — no silent unbounded budget.
    - Transport errors, a non-``completed`` job, or empty content all raise
      ``StructuredGenerateError`` (the empty case with a message that names the
      hidden-reasoning cause, not a downstream JSON error).
    """
    if not any((m.get("content") or "").strip() for m in messages):
        raise StructuredGenerateError("no prompt content to send")

    wire = reasoning_fields(_as_directive(reasoning))
    try:
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_output_tokens,
                **wire,
            },
            chunking=None,
            trace_id=trace_id,
            job_meta=job_meta,
            transient_retry_budget=transient_retry_budget,
        )
    except Exception as exc:  # SDK/transport — surface as a clean 502
        raise StructuredGenerateError(f"LLM call failed: {exc}") from exc

    if getattr(job, "status", None) != "completed":
        code = job.error.code if getattr(job, "error", None) else "LLM_UNKNOWN_ERROR"
        raise StructuredGenerateError(
            f"generate job ended status={getattr(job, 'status', '?')} ({code})"
        )

    content = _content_of(job)
    if not content.strip():
        raise StructuredGenerateError(
            "the model returned an empty response (it may have spent its budget on "
            "hidden reasoning) — try a different model or a more specific prompt"
        )
    return GenerateResult(content=content, job=job)
