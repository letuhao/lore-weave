"""Reusable auto-reasoning ("thinking") policy primitives.

Generic, domain-agnostic machinery shared by every service that calls the gateway
(composition, translation, extraction, chat…). The SDK already owns
`reasoning_effort` / `ReasoningEffort`, so the policy that decides WHEN/HOW MUCH a
model should think belongs here too.

What's generic (here) vs domain (the caller):
- generic: which models self-orchestrate vs take `reasoning_effort` vs neither
  (`infer_reasoning_control`); the monotone score→effort bucketer (`bucket_effort`);
  the user-override / capability-dispatch resolution (`resolve_reasoning`).
- domain (NOT here): which signals matter and their weights. The caller computes a
  score from its own signals, buckets it, and passes the resulting `auto_effort`.

Research basis (2026-06): Anthropic/Gemini self-decide (pass through — don't
out-think them); OpenAI o/GPT-5 + local Qwen3/DeepSeek-R1 take `reasoning_effort`
(we classify); everything else is non-reasoning. See
docs/specs/2026-06-05-auto-reasoning-mode.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from loreweave_llm.models import ReasoningEffort

ReasoningControl = Literal["adaptive", "effort", "none"]
UserReasoningPref = Literal["off", "auto", "low", "medium", "high"]

_VALID_CONTROL: set[str] = {"adaptive", "effort", "none"}

# Self-orchestrating providers (pass through — never run a classifier on them).
_ADAPTIVE_KINDS = {"anthropic"}
_GOOGLE_KINDS = {"google", "gemini", "google_vertex", "vertex"}
# Providers/models controlled via reasoning_effort.
_LOCAL_KINDS = {"lm_studio", "ollama", "llama_cpp", "vllm", "openai_compatible"}
_EFFORT_OPENAI = re.compile(r"\b(o1|o3|o4|gpt-5)\b", re.IGNORECASE)
_EFFORT_LOCAL = re.compile(r"(qwen3|qwen-3|deepseek[-_]?r1|magistral|reasoning|thinking|qwq)", re.IGNORECASE)
_GEMINI_REASONING = re.compile(r"2\.5|gemini-[3-9]|3\.", re.IGNORECASE)


def infer_reasoning_control(
    provider_kind: str | None,
    provider_model_name: str | None,
    capability_flags: dict[str, Any] | None = None,
) -> ReasoningControl:
    """How a registered model wants reasoning controlled. An explicit
    `capability_flags.reasoning_control` overrides the heuristic. Unknown → "none"
    (safe: reasoning_effort is then a no-op and auto won't waste a classifier)."""
    if capability_flags:
        override = capability_flags.get("reasoning_control")
        if isinstance(override, str) and override in _VALID_CONTROL:
            return override  # type: ignore[return-value]

    kind = (provider_kind or "").strip().lower()
    name = provider_model_name or ""

    if kind in _ADAPTIVE_KINDS:
        return "adaptive"
    if kind in _GOOGLE_KINDS and _GEMINI_REASONING.search(name):
        return "adaptive"
    if kind == "openai" and _EFFORT_OPENAI.search(name):
        return "effort"
    if kind in _LOCAL_KINDS and _EFFORT_LOCAL.search(name):
        return "effort"
    return "none"


def bucket_effort(score: int, *, high: int = 4, medium: int = 2, low: int = 1) -> ReasoningEffort:
    """Monotone score → effort bucketer for rule-based 'when to think' scorers.
    Thresholds are inclusive lower bounds; below `low` → "none"."""
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    if score >= low:
        return "low"
    return "none"


@dataclass(frozen=True)
class ReasoningDirective:
    """What the caller should send. `effort=None` + `passthrough=True` means OMIT
    reasoning_effort (let an adaptive model self-decide). `source` explains the
    decision for UI/telemetry."""
    effort: ReasoningEffort | None
    passthrough: bool
    source: str  # "user" | "adaptive" | <auto_source> | "non_reasoning"


def resolve_reasoning(
    *,
    user_pref: UserReasoningPref,
    model_control: ReasoningControl,
    auto_effort: ReasoningEffort = "none",
    auto_source: str = "rule_based",
) -> ReasoningDirective:
    """Combine the user preference + the model's control style into a directive.

    - explicit user choice (off/low/medium/high) ALWAYS wins.
    - "auto": adaptive → pass through (don't out-think it); effort → use the
      caller-computed `auto_effort` (labelled `auto_source`); none → no-op.
    """
    if user_pref == "off":
        return ReasoningDirective(effort="none", passthrough=False, source="user")
    if user_pref in ("low", "medium", "high"):
        return ReasoningDirective(effort=user_pref, passthrough=False, source="user")  # type: ignore[arg-type]

    if model_control == "adaptive":
        return ReasoningDirective(effort=None, passthrough=True, source="adaptive")
    if model_control == "effort":
        return ReasoningDirective(effort=auto_effort, passthrough=False, source=auto_source)
    return ReasoningDirective(effort=None, passthrough=False, source="non_reasoning")


def reasoning_fields(directive: ReasoningDirective) -> dict[str, Any]:
    """The provider chat-job input fragments for a resolved reasoning directive —
    the single place that turns a `ReasoningDirective` into wire fields, replacing
    translation's `thinking_llm_fields` + composition's inline copies.

    - `passthrough` (an adaptive self-deciding model, e.g. Anthropic) → `{}`: OMIT
      reasoning_effort entirely so we don't out-think a model that self-orchestrates
      (sending it to Anthropic is wrong — it has no reasoning_effort knob).
    - `effort is None` (non-reasoning model) → `{}`: nothing to send.
    - an explicit effort → `{reasoning_effort, chat_template_kwargs}`. `reasoning_effort`
      is the OpenAI-o/local knob; `chat_template_kwargs.{thinking,enable_thinking}` is
      the LM Studio / llama.cpp / vLLM template toggle. effort='none' explicitly
      DISABLES hidden thinking (so reasoning_tokens don't silently burn the output
      budget — the empty-prose footgun)."""
    if directive.passthrough or directive.effort is None:
        return {}
    enable = directive.effort != "none"
    return {
        "reasoning_effort": directive.effort,
        "chat_template_kwargs": {"thinking": enable, "enable_thinking": enable},
    }
