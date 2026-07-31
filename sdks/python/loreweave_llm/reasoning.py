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

#: How a registered model wants reasoning controlled.
#:
#: - "adaptive"  — the model self-orchestrates (Anthropic, Gemini 2.5+). Send nothing.
#: - "effort"    — the model takes `reasoning_effort`, and we choose the level.
#: - "suppress"  — the ENDPOINT accepts the suppression knobs, but we have no evidence
#:                 this model reasons. Default it OFF (see below).
#: - "none"      — no reasoning knob exists at all. Send nothing.
#:
#: "suppress" vs "none" is the distinction this module was missing, and its absence cost a
#: live silent failure: gemma-4-26b-a4b-qat on LM Studio matches no name pattern in
#: `_EFFORT_LOCAL`, so it classified as "none" → nothing on the wire → the model's own chat
#: template kept thinking ON → the entire output budget went to hidden reasoning → an empty
#: draft, billed, reported as success.
#:
#: The lesson is NOT "widen the regex" — no name list is ever complete. It is that a GUESS
#: must fail SAFE. For a local endpoint suppression is free when we guess wrong in the
#: harmless direction (`reasoning_effort="none"` is a no-op on a model that cannot think) and
#: load-bearing when we guess wrong in the other. So local-unknown suppresses.
#:
#: Fail-open was once correct: real OpenAI 400s on `reasoning_effort` for gpt-* models. That
#: guard now lives at the gateway (`stripDefaultOpenAIUnsupportedFields`, LOOM-71), which
#: strips both fields for OpenAI cloud and KEEPS them for a custom base_url — i.e. for exactly
#: the local servers this branch targets. The reason for failing open moved away; the default
#: did not follow it here until now.
ReasoningControl = Literal["adaptive", "effort", "suppress", "none"]
UserReasoningPref = Literal["off", "auto", "low", "medium", "high"]

_VALID_CONTROL: set[str] = {"adaptive", "effort", "suppress", "none"}

# Self-orchestrating providers (pass through — never run a classifier on them).
_ADAPTIVE_KINDS = {"anthropic"}
_GOOGLE_KINDS = {"google", "gemini", "google_vertex", "vertex"}
# Providers/models controlled via reasoning_effort.
_LOCAL_KINDS = {"lm_studio", "ollama", "llama_cpp", "vllm", "openai_compatible"}
_EFFORT_OPENAI = re.compile(r"\b(o1|o3|o4|gpt-5)\b", re.IGNORECASE)
#: D-REASONING-MODEL-PATTERNS-DUPLICATED (2026-07-31): worker-ai carried its OWN copy of
#: this list (`_REASONING_MODEL_PATTERNS` in `runner.py`) with a different membership —
#: it had `glm-z`, `minimax-m1` and `deepseek-reasoner` that this one lacked, and lacked
#: the hyphenated `qwen-3` that this one has. Two answers to "does this name look like a
#: reasoning model", drifting apart. Merged here, where the rest of the model-family
#: knowledge lives, and exported as `looks_like_reasoning_model` for the second consumer.
_EFFORT_LOCAL = re.compile(
    r"(qwen3|qwen-3|deepseek[-_]?r1|deepseek[-_]?reasoner|magistral"
    r"|reasoning|reasoner|thinking|qwq|glm-z|minimax-m1)",
    re.IGNORECASE,
)
#: OpenAI o-series as a TOKEN (o1/o3/o4/o5), so `gpt-4o` does not match. Kept separate
#: from `_EFFORT_OPENAI` because that one is provider-scoped; this is name-only.
_REASONING_O_SERIES = re.compile(r"(?:^|[^a-z0-9])o[1345](?:-|$|[^a-z0-9])", re.IGNORECASE)


def looks_like_reasoning_model(name: str | None) -> bool:
    """Best-effort: does this model NAME look like a reasoning/thinking model?

    Name heuristics only — provider-registry has no reasoning capability flag, so this
    WILL have false negatives on novel models. Every caller must treat it as ADVISORY
    (a warning, a suppression default), never as a hard gate.

    One home for the pattern set: a second copy in a consumer drifts, and the drift is
    invisible because both copies keep working.
    """
    if not name:
        return False
    return bool(_REASONING_O_SERIES.search(name) or _EFFORT_LOCAL.search(name))
_GEMINI_REASONING = re.compile(r"2\.5|gemini-[3-9]|3\.", re.IGNORECASE)


def infer_reasoning_control(
    provider_kind: str | None,
    provider_model_name: str | None,
    capability_flags: dict[str, Any] | None = None,
) -> ReasoningControl:
    """How a registered model wants reasoning controlled. An explicit
    `capability_flags.reasoning_control` overrides the heuristic — and that override, not a
    wider regex, is the right home for a model this function guesses wrong about.

    Unknown on a LOCAL endpoint → "suppress" (thinking off by default; see the
    `ReasoningControl` note). Unknown anywhere else → "none"."""
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
    if kind in _LOCAL_KINDS:
        # A name match means "known reasoning model" → let the caller pick a level. No match
        # means "we don't know" — NOT "it cannot think". Suppress rather than gamble on the
        # chat template's default.
        return "effort" if _EFFORT_LOCAL.search(name) else "suppress"
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
    if model_control == "suppress":
        # An unclassified LOCAL model: turn thinking OFF explicitly rather than sending
        # nothing and inheriting whatever the chat template does. `source` names the reason
        # so telemetry shows a DECISION, not an absence — the empty-draft incident was
        # unreadable precisely because "we chose not to send" and "we had nothing to send"
        # looked identical after the fact.
        return ReasoningDirective(effort="none", passthrough=False, source="suppress_unclassified")
    return ReasoningDirective(effort=None, passthrough=False, source="non_reasoning")


def directive_from_parts(
    *, source: str | None, effort: str | None, passthrough: bool | None,
) -> ReasoningDirective:
    """Rebuild a directive from its SERIALIZED parts (a queued job's input, a stored row).

    The one way to cross the persistence boundary. Callers used to re-derive the collapse by
    hand — `None if input["reasoning_passthrough"] else input["reasoning_effort"]` — which
    produced two different conventions inside a single file (one collapsing at write time,
    one at read time) and dropped `chat_template_kwargs` on every path that did it.

    Tolerant by design: a job enqueued before this existed carries a null effort and no
    passthrough flag, and rebuilds to the same no-op directive it would have had. In-flight
    work drains unchanged."""
    eff = effort if effort in ("none", "low", "medium", "high") else None
    return ReasoningDirective(
        effort=eff,  # type: ignore[arg-type]
        passthrough=bool(passthrough),
        source=source or "non_reasoning",
    )


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
