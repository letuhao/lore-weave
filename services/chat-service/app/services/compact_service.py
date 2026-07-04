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
    DoneEvent,
    StreamRequest,
    TokenEvent,
    reasoning_fields,
    resolve_reasoning,
)

from app.config import settings


class SummaryTruncatedError(RuntimeError):
    """The summarizer stopped at max_tokens (finish_reason='length') — its TAIL
    (Open-threads + SYNOPSIS, the most load-bearing state) would be silently
    dropped. Raised instead of returning a partial summary; the manual compact
    route maps it to 502 (session unchanged) and the auto path falls back to
    deterministic hard-truncation (compaction.py) — both honest, unlike storing
    a summary with facts silently missing (audit HIGH-1, 2026-07-04)."""

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
    "- Established: concrete facts/state set (numbers, statuses, relationships) — keep "
    "EVERY figure exact (counts, prices, dates, ages); these are dropped and mis-stated "
    "most, so err toward INCLUDING a detail rather than compressing it away.\n"
    "- Open threads: unresolved questions, promises, next steps.\n"
    "- Keywords: a flat comma-separated list of EVERY salient term above (each name, "
    "place, number, and title) — a recovery INDEX so any specific detail can be found "
    "again. Be exhaustive here even if a detail is also in another line.\n"
    "(Use '- <label>: none' for an empty category. Keep names EXACT — never "
    "paraphrase or translate a name. Better slightly long than missing a fact.)\n\n"
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
            # Headroom for the FACTS block + SYNOPSIS on a long, entity-dense
            # conversation (the structure inflates length vs a plain blurb). If it
            # STILL truncates, the guard below refuses the partial rather than
            # silently dropping the tail.
            messages=summary_messages, temperature=0.2, max_tokens=1400,
            reasoning_effort=rf.get("reasoning_effort"),
            chat_template_kwargs=rf.get("chat_template_kwargs"),
        )
        parts: list[str] = []
        finish_reason: str | None = None
        async for ev in client.stream(request):
            if isinstance(ev, TokenEvent):
                parts.append(ev.delta)
            elif isinstance(ev, DoneEvent):
                finish_reason = ev.finish_reason
    finally:
        await client.aclose()
    # D6 / audit HIGH-1: never return a summary the provider cut off — its tail
    # (Open-threads + SYNOPSIS) would be gone. Let the caller degrade honestly.
    if finish_reason == "length":
        raise SummaryTruncatedError(
            f"summary hit max_tokens ({request.max_tokens}); tail facts would be lost"
        )
    return "".join(parts).strip()


async def persist_auto_compact(
    pool,
    session_id: str,
    user_id: str,
    *,
    model_source: str,
    model_ref: str,
    target: int,
    keep_recent: int = 8,
    prev_summary: str | None,
    prev_before_seq: int | None,
    trace=None,
) -> tuple[str, int] | None:
    """C_persist — the AUTOMATIC analogue of the manual /compact route. When a session's LIVE
    history (post the previous boundary, + the prev summary folded in) exceeds `target`,
    summarize the droppable middle ONCE and PERSIST {compact_summary, compacted_before_seq} so
    every later turn LOADS the summary instead of re-summarizing the raw history every turn (the
    62%-overhead regression the sweep found). The loader (stream_service) already splices
    summary + post-boundary messages, so this converts O(turns) summarizer calls into
    O(turns / keep_recent).

    Returns (new_summary, new_before_seq) on success, or None (session UNCHANGED — safe) when:
    nothing to compact, still under target, the summarizer failed (falls back to the ephemeral
    tiers), or a concurrent compact landed (OCC). Mirrors the manual route's persist exactly.

    `trace` (optional `TraceAccumulator`) — when supplied AND a persist actually lands, a T6
    compiler span is recorded with the tokens SAVED (droppable summarized away − the summary
    that replaced them). This is the ONE turn that paid the summarizer cost, so the saving is
    attributed here (later turns load the summary with no further compaction span)."""
    from app.services.compaction import extract_breadcrumb, summary_message
    from app.services.token_budget import estimate_messages_tokens, estimate_tokens

    if prev_before_seq is not None:
        rows = await pool.fetch(
            "SELECT sequence_num, role, content FROM chat_messages "
            "WHERE session_id=$1 AND is_error=false AND branch_id=0 AND sequence_num >= $2 "
            "ORDER BY sequence_num ASC",
            session_id, prev_before_seq,
        )
    else:
        rows = await pool.fetch(
            "SELECT sequence_num, role, content FROM chat_messages "
            "WHERE session_id=$1 AND is_error=false AND branch_id=0 ORDER BY sequence_num ASC",
            session_id,
        )
    if len(rows) <= keep_recent:
        return None
    live = [{"role": r["role"], "content": r["content"]} for r in rows]
    if prev_summary:
        live = [summary_message(prev_summary)] + live
    if target and estimate_messages_tokens(live) <= target:
        return None  # live history still under target — no persist needed this turn

    droppable = [{"role": r["role"], "content": r["content"]}
                 for r in rows[: len(rows) - keep_recent]]
    if prev_summary:
        droppable.insert(0, summary_message(prev_summary))
    try:
        summary = await summarize_for_compaction(
            droppable, model_source=model_source, model_ref=str(model_ref), user_id=user_id,
        )
    except Exception:
        return None  # session unchanged — the ephemeral compaction tiers still guard this turn
    if not summary:
        return None
    # Match the ephemeral path's reliability: lead the persisted summary with the DETERMINISTIC
    # breadcrumb (verbatim number/name facts), so a lossy LLM summary can't drop a fact the
    # recall depends on (the 1/9→9/9 fix, docs/eval/context-budget/T2-compaction-trigger).
    if settings.compact_breadcrumb_enabled:
        _bc = extract_breadcrumb(droppable)
        if _bc:
            summary = _bc + "\n\n" + summary
    new_before_seq = int(rows[len(rows) - keep_recent]["sequence_num"])
    result = await pool.execute(
        "UPDATE chat_sessions SET compact_summary=$3, compacted_before_seq=$4, updated_at=now() "
        "WHERE session_id=$1 AND owner_user_id=$2 AND compacted_before_seq IS NOT DISTINCT FROM $5",
        session_id, user_id, summary, new_before_seq, prev_before_seq,
    )
    if result == "UPDATE 0":
        return None  # a concurrent compact landed — safe, leave it
    if trace is not None:
        # T6 saving = what we summarized away − the summary that replaced it (negative delta
        # = tokens SAVED). The Inspector's `raw_tokens` folds this into the naive-concat baseline.
        _saved = estimate_messages_tokens(droppable) - estimate_tokens(summary)
        if _saved > 0:
            trace.add(
                "compiler", "T6", "summary",
                f"C_persist: summarized {len(droppable)} earlier msgs → persisted summary "
                f"(reused every later turn)",
                delta=-_saved,
            )
    return summary, new_before_seq
