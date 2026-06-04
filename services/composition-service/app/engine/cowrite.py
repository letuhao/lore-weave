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

from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

_OPERATION_INSTRUCTIONS = {
    "continue": "Continue the scene from where the recent prose ends, in the same voice.",
    "draft_scene": "Draft this scene from its beat, goal, POV, and synopsis.",
    "expand": "Expand the current passage with more sensory and interior detail.",
    "rewrite": "Rewrite the current passage, keeping its events but improving the prose.",
    "describe": "Write a vivid description for the current moment.",
}


@dataclass
class DraftMetering:
    input_tokens: int
    output_tokens: int
    measured: bool   # False → over-estimated from a char model (no real usage frame)


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
    system = (
        "You are a co-writer continuing a novel. Use the provided canon, present "
        "characters, threads, beat, recent prose, and lore as grounding; never "
        "contradict the canon and never introduce facts beyond what is given."
        + lang + voice
    )
    instruction = _OPERATION_INSTRUCTIONS.get(operation, "Write the next passage of the scene.")
    user = packed_prompt + "\n\n" + instruction + (f"\n\nAuthor guidance: {guide}" if guide else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def stream_draft(
    sdk: Any, *, user_id: str, model_source: str, model_ref: str,
    messages: list[dict[str, Any]], prompt_token_estimate: int,
    max_output_tokens: int, hard_cap_output: int | None = None,
    temperature: float = 0.7, trace_id: str | None = None,
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
    )
    parts: list[str] = []
    measured = False
    in_tok = out_tok = 0
    est_out = 0
    capped = False
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
                pass
    except LLMError as exc:
        logger.warning("stream_draft LLM error: %s", exc)
        yield {"type": "error", "error": str(exc)}

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
    )
    yield {"type": "usage", "text": text, "metering": metering, "capped": capped}
