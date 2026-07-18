"""Co-write loop (§3.1) — build prompt → stream draft → meter real tokens.

Streams a drafter model via the llm SDK's `.sdk.stream` escape hatch (the
wrapper has no stream method). Relays token deltas as they arrive and harvests
the real `UsageEvent` frame. TOKEN METERING (enrichment complete.py lesson): an
ABSENT or ZERO usage frame is "not measured" → fall back to an over-estimating
char model + clamp ≥0; NEVER meter a stream as 0 (that silently weakens the cap).
A mid-stream output cap stops the stream + partial-saves (S3 budget-exhaustion).

De-bias (§2.6): the draft prompt carries the book's `source_language` + abstract
operation instructions — NO English-only illustrative phrases.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from loreweave_llm.errors import LLMError
from loreweave_llm.models import DoneEvent, ReasoningEvent, StreamRequest, TokenEvent, UsageEvent

from app.packer.profile import BookProfile, style_directive

logger = logging.getLogger(__name__)

_OPERATION_INSTRUCTIONS = {
    "continue": "Continue the scene from where the recent prose ends, in the same voice.",
    "draft_scene": "Draft this scene from its beat, goal, POV, and synopsis.",
    # B2 chapter single-pass: the user prompt carries the chapter intent + every
    # scene beat in order; write the WHOLE chapter as one continuous narrative
    # (not a single scene) so the output isn't fragmented back into per-scene size.
    "draft_chapter": "Draft the ENTIRE chapter as one continuous narrative, covering "
                     "every scene beat in the outline in order, with smooth transitions.",
    "expand": "Expand the current passage with more sensory and interior detail.",
    "rewrite": "Rewrite the current passage, keeping its events but improving the prose.",
    "describe": "Write a vivid description for the current moment.",
    # M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — per-scene "adapt from source" for a
    # derivative Work. The packer's <source_scene> block carries the inherited
    # SOURCE scene's prose (gathered ONLY for this op, spoiler-bounded ≤ the branch);
    # the model rewrites it through the divergence + entity overrides. Plan-free
    # (like continue/rewrite): it does NOT require a derivative scene node/plan.
    "adapt_scene": "Adapt the SOURCE scene's prose (in the <source_scene> block) to "
                   "this branch: keep its structural function, but rewrite it to "
                   "honour the divergence and entity overrides. Do not copy the "
                   "source verbatim.",
}


@dataclass
class DraftMetering:
    input_tokens: int
    output_tokens: int
    measured: bool   # False → over-estimated from a char model (no real usage frame)
    # Raw model stop reason from the gateway (DoneEvent / job.result["finish_reason"]).
    # "length" ⇒ the model hit the output cap (truncated); None ⇒ not reported.
    # D-COMP-TRUNCATION-SURFACING: the authoritative truncation signal (replaces the
    # cycle-3 char-estimate heuristic that was dropped for being too biased).
    finish_reason: str | None = None


def char_estimate(text: str) -> int:
    """Over-estimating char→token model for the metering FALLBACK only. ~3 chars
    per token over-estimates English while staying close for CJK; clamped ≥0."""
    return max(0, math.ceil(len(text or "") / 3))


def estimate_prompt_tokens(messages: list[dict[str, Any]], counter: Callable[[str], int]) -> int:
    return sum(counter(str(m.get("content", ""))) for m in messages)


def build_messages(
    packed_prompt: str, profile: BookProfile, operation: str, guide: str = "",
) -> list[dict[str, str]]:
    """System + user messages for the drafter. The packer's structured blocks are
    the grounding; the wrapper carries language + the operation steer."""
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5 — density/pace + present-character voices
    system = (
        "You are a co-writer continuing a novel. Use the provided canon, present "
        "characters, threads, beat, recent prose, and lore as grounding; never "
        "contradict the canon and never introduce facts beyond what is given. "
        "Everything in the context has ALREADY happened earlier in the novel and "
        "the reader has read it: CONTINUE the story forward from that point — do "
        "NOT re-introduce characters, re-describe the established setting, or "
        "re-narrate prior scenes/events already shown; advance new action instead. "
        # Anti-repetition (LOOM-69d): the model-vs-architecture diagnostic found the
        # local drafter reuses a small set of distinctive images/openings across
        # scenes (recurring weather/color motifs, a repeated opening construction).
        # Push for surface variety — a model-agnostic craft nudge.
        "Vary your prose: do NOT reuse a distinctive image, metaphor, or "
        "sentence-opening you have already used in this work (e.g. a recurring "
        "weather or colour motif, or a repeated opening line) — each passage should "
        "read freshly with its own sensory language."
        + lang + voice + style
    )
    instruction = _OPERATION_INSTRUCTIONS.get(operation, "Write the next passage of the scene.")
    # FD-1 S3 — only fires when open promises were re-injected (the <open_promises>
    # block is present ⇒ narrative_thread is enabled + has open threads). Without a
    # steer the block is inert context; with it, the model advances/pays promises.
    # Gated by the block's presence so the default (flag-off) prompt is unchanged.
    promise_steer = (
        "\n\nThe <open_promises> are unresolved narrative promises/foreshadows the "
        "reader is waiting on: advance or pay one off where it fits this scene; do "
        "NOT silently drop them, and do not contradict canon to force one."
    ) if "<open_promises>" in packed_prompt else ""
    user = packed_prompt + "\n\n" + instruction + promise_steer + (
        f"\n\nAuthor guidance: {guide}" if guide else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# T3.2 — selection-scoped operations. DISTINCT from _OPERATION_INSTRUCTIONS (scene
# drafting): these act on a SELECTED passage the author highlighted, not a scene beat.
# build_selection_messages RAISES on an unregistered op (no draft_scene fallback) —
# the LOOM-39 dict.get(key, DEFAULT)-hides-a-missing-enum lesson: a typo'd op must
# NOT silently draft a whole scene over the selection.
_SELECTION_INSTRUCTIONS = {
    "rewrite": "Rewrite the SELECTED PASSAGE below, preserving its events and meaning "
               "but improving the prose. Keep roughly the same length.",
    "expand": "Expand the SELECTED PASSAGE below with more sensory and interior detail, "
              "preserving its meaning and continuity. It should grow longer.",
    "describe": "Enrich the SELECTED PASSAGE below with vivid sensory and scene "
                "description, keeping its events and meaning intact.",
}

# Generous backstop cap (chars). The FE disables the tools above this; the request
# model's Field(max_length=...) 422s a bypass. ~8k chars ≈ a long paragraph or two.
SELECTION_MAX_CHARS = 8000


def build_selection_messages(
    selection: str, profile: BookProfile, operation: str,
    guide: str = "", grounding: str = "",
) -> list[dict[str, str]]:
    """T3.2 — (system, user) for a SELECTION-scoped edit (rewrite/expand/describe).
    EXPLICIT dispatch: an unregistered operation RAISES (never falls back to a scene
    draft — LOOM-39). `grounding` is the packer's structured blocks (canon/lore) when
    a scene_context was supplied; empty → voice-only. Output is ONLY the revised
    passage so the FE can replace the selection verbatim."""
    if operation not in _SELECTION_INSTRUCTIONS:
        raise ValueError(f"unregistered selection operation: {operation!r}")
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5
    system = (
        "You are a co-writer editing a specific passage of a novel. Use any provided "
        "canon, characters, and lore as grounding; never contradict the canon and "
        "never introduce facts beyond what is given. Output ONLY the revised passage "
        "— no preamble, no quotation marks, no commentary." + lang + voice + style
    )
    parts: list[str] = []
    if grounding:
        parts.append(grounding)
    parts.append(_SELECTION_INSTRUCTIONS[operation])
    parts.append("SELECTED PASSAGE:\n" + selection)
    if guide:
        parts.append("Author guidance: " + guide)
    return [{"role": "system", "content": system}, {"role": "user", "content": "\n\n".join(parts)}]


def build_revise_messages(
    packed_prompt: str, profile: BookProfile, draft: str,
    violations: list[Any],
) -> list[dict[str, str]]:
    """A2-S3b — (system, user) for a canon REVISE pass. The drafter rewrites
    `draft` to remove the confirmed contradictions while preserving the scene.
    Abstract + multilingual-safe (no English-only illustrative phrases)."""
    lang = "" if profile.source_language in ("", "auto") else (
        f" Write the prose in the language with code '{profile.source_language}'."
    )
    voice = f" Match this voice: {profile.voice}." if profile.voice else ""
    style = style_directive(profile)  # T3.5
    system = (
        "You are a co-writer revising a passage to fix continuity errors. The "
        "listed characters are GONE (dead, destroyed, departed, or lost) before "
        "this passage and MUST NOT be portrayed as an active presence — not "
        "acting, speaking, perceiving, or bodily present. Rewrite the passage to "
        "remove these contradictions while preserving its events, intent, voice, "
        "and length. Output ONLY the revised prose." + lang + voice + style
    )
    listed = "\n".join(
        f'- {getattr(v, "name", None) or getattr(v, "entity_id", "?")}'
        f'{(": " + v.span) if getattr(v, "span", "") else ""}'
        for v in violations
    )
    user = (
        f"{packed_prompt}\n\nGONE CHARACTERS WRONGLY PRESENT (fix these):\n{listed}"
        f"\n\nPASSAGE TO REVISE:\n{draft}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def revise_draft(
    sdk: Any, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, Any]], prompt_token_estimate: int,
    max_output_tokens: int, temperature: float = 0.7,
    trace_id: str | None = None, reasoning_effort: str | None = None,
) -> tuple[str, "DraftMetering"]:
    """One-shot (non-stream) revise: drives `stream_draft` and harvests the
    terminal usage frame. Returns (revised_text, metering). Empty text on LLM
    error (the caller keeps the prior draft → reflect treats it as give-up)."""
    text = ""
    metering = DraftMetering(input_tokens=prompt_token_estimate, output_tokens=0, measured=False)
    async for ev in stream_draft(
        sdk, user_id=user_id, model_source=model_source, model_ref=model_ref,
        messages=messages, prompt_token_estimate=prompt_token_estimate,
        max_output_tokens=max_output_tokens, hard_cap_output=max_output_tokens * 2,
        temperature=temperature, trace_id=trace_id, reasoning_effort=reasoning_effort,
    ):
        if ev["type"] == "usage":
            text, metering = ev["text"], ev["metering"]
    return text, metering


async def stream_draft(
    sdk: Any, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, Any]], prompt_token_estimate: int,
    max_output_tokens: int, hard_cap_output: int | None = None,
    temperature: float = 0.7, trace_id: str | None = None,
    reasoning_effort: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Async generator of stream events for the router to relay as SSE:
      {"type":"token","delta":...} · {"type":"reasoning","delta":...}
      {"type":"capped"} (mid-stream output cap hit) · {"type":"error","error":...}
      {"type":"usage","text":<full prose>,"metering":DraftMetering} (terminal).
    """
    req = StreamRequest(
        model_source=model_source, model_ref=model_ref, messages=messages,
        temperature=temperature, max_tokens=max_output_tokens or None,
        trace_id=trace_id,
        # Expose the reasoning knob (model-default when None). reasoning_effort
        # ="none" disables hidden thinking on reasoning-model drafters so the
        # whole budget doesn't get spent on reasoning_tokens (empty ghost).
        reasoning_effort=reasoning_effort,
    )
    parts: list[str] = []
    measured = False
    in_tok = out_tok = 0
    est_out = 0
    capped = False
    finish_reason: str | None = None
    error: str | None = None
    try:
        async for ev in sdk.stream(req, user_id=user_id):
            if isinstance(ev, TokenEvent):
                parts.append(ev.delta)
                yield {"type": "token", "delta": ev.delta}
                est_out += char_estimate(ev.delta)
                if hard_cap_output and est_out > hard_cap_output and not measured:
                    capped = True
                    yield {"type": "capped"}
                    break
            elif isinstance(ev, ReasoningEvent):
                yield {"type": "reasoning", "delta": ev.delta}
            elif isinstance(ev, UsageEvent):
                measured = True
                in_tok = ev.input_tokens or 0
                out_tok = ev.output_tokens or 0
            elif isinstance(ev, DoneEvent):
                # D-COMP-TRUNCATION-SURFACING: the model's stop reason ("length" ⇒
                # hit the cap). Previously discarded.
                finish_reason = ev.finish_reason
    except LLMError as exc:
        logger.warning("stream_draft LLM error: %s", exc)
        error = str(exc)
        yield {"type": "error", "error": error}

    text = "".join(parts)
    # Gate OUTPUT metering on a non-zero output frame specifically: an absent OR
    # zero-output frame is "not measured" → over-estimate from the char model
    # (never meter 0 — the enrichment lesson). A frame may report input but
    # zero output, so the two axes are decided independently.
    out_measured = measured and out_tok > 0
    metering = DraftMetering(
        input_tokens=in_tok if (measured and in_tok > 0) else prompt_token_estimate,
        output_tokens=out_tok if out_measured else char_estimate(text),
        measured=out_measured,
        finish_reason=finish_reason,
    )
    # `error` rides the terminal frame so the router can distinguish a real failure
    # (an LLMError with NO content — a resolve failure metered at 0 → the job is marked
    # FAILED) from a clean finish. A mid-stream error AFTER partial content keeps `text`
    # non-empty: the router keeps the partial work as `completed` but sets truncated=True
    # and carries `error` (finish_reason is None on an error interruption, so the error is
    # what marks it incomplete — the consumers OR it into `truncated`).
    yield {"type": "usage", "text": text, "metering": metering, "capped": capped,
           "error": error}
