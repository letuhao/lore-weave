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

# D6 (Context Budget Law) — a FACT-PRESERVING EXTRACTIVE summary, not a lossy prose
# blur. A rolling prose summary silently drops load-bearing facts (a name, a decision,
# an open promise) that a later turn still needs; the weak local models we target are
# the worst at this. So the summary leads with an EXPLICIT, verbatim FACTS block (the
# system of record) and only then a short prose synopsis (the convenience). The FACTS
# block is what makes lossy compaction safe — anything listed there survives.
_SUMMARY_SYSTEM_PROMPT = (
    "You compress the EARLIER part of an ongoing conversation so it fits in context "
    "WITHOUT losing anything the assistant must still know. Output EXACTLY two "
    "sections, nothing else:\n\n"
    "FACTS:\n"
    "- Entities: every named person/place/thing/work introduced, VERBATIM.\n"
    "- Decisions: choices made and their rationale.\n"
    "- Established: concrete facts/state set (numbers, statuses, relationships).\n"
    "- Open threads: unresolved questions, promises, next steps.\n"
    "(Use '- <label>: none' for an empty category. Keep names EXACT — never "
    "paraphrase or translate a name.)\n\n"
    "SYNOPSIS:\n"
    "A few sentences of prose tying the above together.\n\n"
    "Omit pleasantries. Do NOT reason aloud. Do NOT add any other headers or preamble."
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
            messages=summary_messages, temperature=0.2, max_tokens=900,
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
