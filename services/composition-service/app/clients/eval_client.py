"""Judge client for `judge_prose` (composition-service, M3 — M6 critic).

Contract-verified 2026-06-04: `loreweave_eval` has NO dedicated client class —
its `JudgeLLMClient` is a structural Protocol (one method: `submit_and_wait`),
which our `LLMClient` already satisfies. So the judge client IS the llm_client;
this module just gives M6 a clearly-named accessor + the load-bearing
content-extraction helper, instead of duplicating the SDK wiring.

Anti-self-reinforcement (§4): the critic model must differ from the drafter —
that is the CALLER's choice (different `model_ref` at `submit_and_wait`), not a
separate transport. judge_prose reuses `operation="chat"` (the OpenAI wire
shape; the judge parses JSON itself) — no new JobOperation enum.
"""

from __future__ import annotations

from typing import Any

from app.clients.llm_client import LLMClient, get_llm_client

__all__ = ["get_judge_client", "extract_judge_content"]


def get_judge_client() -> LLMClient:
    """The judge client is the shared LLMClient (satisfies the loreweave_eval
    `JudgeLLMClient` Protocol structurally). Critic model-diversity is set via a
    distinct `model_ref` per call, not a separate client."""
    return get_llm_client()


def extract_judge_content(result: dict[str, Any] | None) -> str:
    """Read a gateway completion's text from a terminal Job result.

    LOAD-BEARING (memory `gateway_response_messages_array_not_content_string`):
    the content is at `result["messages"][0]["content"]`, NOT `result["content"]`.
    Returns "" when absent so a malformed/empty frame degrades to unjudged
    rather than crashing the critique batch."""
    if not isinstance(result, dict):
        return ""
    messages = result.get("messages") or []
    if messages and isinstance(messages[0], dict):
        return messages[0].get("content", "") or ""
    return ""
