"""Map user thinking on/off to provider-registry chat job input fields."""
from __future__ import annotations

from typing import Any


def thinking_llm_fields(*, enabled: bool) -> dict[str, Any]:
    """LLM input fragments for reasoning/thinking control.

    Off (default for JSON pipelines): reasoning_effort=none + disable template thinking.
    On: medium effort + enable_thinking for LM Studio / llama.cpp style models (Gemma, Qwen3).
    """
    if enabled:
        return {
            "reasoning_effort": "medium",
            "chat_template_kwargs": {"thinking": True, "enable_thinking": True},
        }
    return {
        "reasoning_effort": "none",
        "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
    }
