"""Model reasoning-capability inference (§Architecture.1).

Decides HOW a registered model wants its reasoning controlled, so the resolver
knows whether to (a) pass through to a model that self-orchestrates (Anthropic
adaptive, Gemini dynamic) — "don't out-think a model that already thinks" — or
(b) drive `reasoning_effort` ourselves for a reasoning model without native auto
(Qwen3/DeepSeek-R1 on LM Studio), or (c) treat it as a plain non-reasoning model.

Pure: a small table + name regex over (provider_kind, provider_model_name,
capability_flags). The model metadata reaches composition as a request hint from
the FE (it already lists user-models with these fields); this is a UX policy, not
an authz boundary, so a hint is acceptable. An explicit
`capability_flags.reasoning_control` overrides the heuristic.
"""

from __future__ import annotations

import re
from typing import Any, Literal

ReasoningControl = Literal["adaptive", "effort", "none"]

# Models that self-decide thinking (we pass through; never run our classifier).
_ADAPTIVE_KINDS = {"anthropic"}
_ADAPTIVE_GOOGLE_KINDS = {"google", "gemini", "google_vertex", "vertex"}

# Reasoning models controlled via reasoning_effort (we MAY classify → effort).
_EFFORT_OPENAI = re.compile(r"\b(o1|o3|o4|gpt-5)\b", re.IGNORECASE)
_EFFORT_LOCAL = re.compile(
    r"(qwen3|qwen-3|deepseek[-_]?r1|magistral|reasoning|thinking|qwq)",
    re.IGNORECASE,
)
_LOCAL_KINDS = {"lm_studio", "ollama", "llama_cpp", "vllm", "openai_compatible"}

_VALID: set[str] = {"adaptive", "effort", "none"}


def infer_reasoning_control(
    provider_kind: str | None,
    provider_model_name: str | None,
    capability_flags: dict[str, Any] | None = None,
) -> ReasoningControl:
    """Best-effort inference. Unknown → "none" (safe: reasoning_effort is then a
    no-op and auto won't waste a classifier)."""
    # 1. Explicit override from the registry wins.
    if capability_flags:
        override = capability_flags.get("reasoning_control")
        if isinstance(override, str) and override in _VALID:
            return override  # type: ignore[return-value]

    kind = (provider_kind or "").strip().lower()
    name = provider_model_name or ""

    # 2. Self-orchestrating models → pass-through.
    if kind in _ADAPTIVE_KINDS:
        return "adaptive"
    if kind in _ADAPTIVE_GOOGLE_KINDS and re.search(r"2\.5|3\.|gemini-[3-9]", name, re.IGNORECASE):
        return "adaptive"

    # 3. reasoning_effort-controlled reasoning models.
    if kind == "openai" and _EFFORT_OPENAI.search(name):
        return "effort"
    if kind in _LOCAL_KINDS and _EFFORT_LOCAL.search(name):
        return "effort"

    # 4. Everything else: not a reasoning model.
    return "none"
