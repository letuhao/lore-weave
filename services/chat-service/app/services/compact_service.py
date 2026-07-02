"""Compaction summarizer — the LLM half of conversation compaction (W3 factor).

Moved out of stream_service so BOTH consumers share one implementation:
  * the in-turn auto-compaction tiers (stream_service's ``compact_messages``
    summarize callback), and
  * the manual ``POST /v1/chat/sessions/{id}/compact`` route (sessions router),
    which adds the user's steering ``instructions`` ("keep all plot promises
    and character names" — the novel-domain steerable-compact pattern).

Provider-agnostic via the LLM gateway (works for local lm_studio / Qwen /
Gemma AND Claude). A failure RAISES — the auto path catches it and falls back
to deterministic truncation; the manual route maps it to a 502 and leaves the
session unchanged (a manual compact must never silently degrade to truncation:
the user asked for a summary).
"""
from __future__ import annotations

from loreweave_llm import (
    Client,
    StreamRequest,
    TokenEvent,
    reasoning_fields,
    resolve_reasoning,
)

from app.config import settings

_SUMMARY_SYSTEM_PROMPT = (
    "You compress the EARLIER part of an ongoing conversation into a dense, "
    "factual synopsis so it fits in context. Preserve named entities, decisions "
    "made, facts established, open threads, and any state the assistant must "
    "keep. Omit pleasantries. Output ONLY the synopsis prose — no preamble, no "
    "headers, and do NOT reason aloud."
)


def transcript_of(messages: list[dict]) -> str:
    """Flatten a messages array into a role-prefixed transcript for the
    summarizer. Content-parts arrays are joined; a prose-less tool-call turn is
    represented compactly as ``(called tool_a, tool_b)``."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content")
        if isinstance(content, list):  # content parts
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        if not content:  # a tool-call turn with no prose — represent it compactly
            tcs = m.get("tool_calls") or []
            names = ", ".join(tc.get("function", {}).get("name", "tool") for tc in tcs)
            content = f"(called {names})" if names else ""
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def summarize_for_compaction(
    messages: list[dict],
    *,
    model_source: str,
    model_ref: str,
    user_id: str,
    instructions: str | None = None,
) -> str:
    """Compress a run of OLDER turns into a dense synopsis with the session's
    OWN model. ``instructions`` (manual compact only) is folded in verbatim as
    a preserve-these directive so the user steers what survives.

    Hidden thinking is DISABLED for the summary call (live-caught: gemma spent
    the whole max_tokens budget on ReasoningEvents and returned EMPTY prose —
    the exact empty-prose footgun the SDK's reasoning_fields documents). A
    pref of "off" resolves to the same wire fields regardless of the model's
    control style — same semantics as the user picking Fast on the main path.
    """
    directive = resolve_reasoning(user_pref="off", model_control="none")
    rf = reasoning_fields(directive)

    system = _SUMMARY_SYSTEM_PROMPT
    if instructions and instructions.strip():
        system += (
            "\n\nThe user gave these preservation instructions — anything they "
            "name MUST survive the compression verbatim (names, promises, "
            "facts):\n" + instructions.strip()
        )
    summary_messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Conversation excerpt to compress:\n\n{transcript_of(messages)}\n\nSynopsis:"},
    ]
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
    )
    try:
        request = StreamRequest(
            model_source=model_source, model_ref=model_ref,
            messages=summary_messages, temperature=0.2, max_tokens=700,
            reasoning_effort=rf.get("reasoning_effort"),
            chat_template_kwargs=rf.get("chat_template_kwargs"),
        )
        parts: list[str] = []
        async for ev in client.stream(request):
            if isinstance(ev, TokenEvent):
                parts.append(ev.delta)
    finally:
        await client.aclose()
    return "".join(parts).strip()
