"""S2 — the `compress` primitive (§3 / §10.2 F2 state re-injection).

`compress(state) → re-injectable summary`: an LLM call that condenses the older
"story so far" + the (spoiler-filtered) KG timeline + the decompose plan into a
bounded narrative-state summary, so long chapters don't blow the prompt budget
with raw prose (DOME temporal-KG memory + RecurrentGPT NL-memory). The packer
calls this only when the raw story-so-far exceeds its budget slice, then injects
the summary in place of the older raw paragraphs (keeping the immediate-preceding
prose verbatim).

⚠ SPOILER-SAFETY (/review-impl H2): the caller MUST pass the packer's ALREADY
reading-position-filtered timeline + strictly-prior prose — `compress` does NOT
read the KG itself, so it cannot leak future canon. It only re-phrases what it's
given.

Degrade-safe: any LLM/empty failure returns "" — the caller then keeps the raw
(budget-trimmed) prose, so a compress outage never blocks or corrupts a generate.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from loreweave_llm import no_thinking_fields
from loreweave_llm.errors import LLMError

from app.clients.eval_client import extract_judge_content
from app.clients.llm_client import LLMClient
from app.llm_budget import unusable, max_tokens_for
from app.engine.cross_scene_check import build_extract_prompt, extract_people

logger = logging.getLogger(__name__)


def build_compress_messages(
    prose: list[str], timeline: list[str], plan: str, source_language: str,
) -> tuple[str, str]:
    """(system, user). Abstract + source-language-aware (no English-only
    illustrative phrases — the CJK-bias lesson)."""
    lang = "" if source_language in ("", "auto") else (
        f" Write the summary in the language with code '{source_language}'."
    )
    # A running STATE LEDGER, not a plot recap. The 2026-07-26 chapter-quality
    # investigation traced the mid-arc continuity breaks (a character's ongoing
    # physical TRANSFORMATION silently flipped between chapters; a character crossed
    # terrain the story had established as impassable) to a generic summary that
    # blurred each entity's evolving CONDITION and LOCATION. When those facts are
    # vague in the summary, the drafter re-invents them and contradicts canon. So we
    # force the summary to carry the continuity-critical state explicitly.
    system = (
        "You maintain a running STORY-STATE LEDGER for a long work so a writer can "
        "continue WITHOUT contradicting what is already established. Condense the "
        "story so far into a compact, faithful state record — NOT a plot recap. "
        "For EACH character present, record their current physical and mental "
        "CONDITION and any ongoing TRANSFORMATION or status (e.g. wounded, changed, "
        "fading, disguised, bound) — carry this forward PRECISELY, because otherwise "
        "the writer will re-invent it and contradict it. Also record: the LOCATION "
        "of each character and key object (who/what is WHERE); what has CHANGED in "
        "the world or setting (what is destroyed, altered, or impassable); "
        "unresolved tensions and open commitments; and established concrete facts "
        "(names, relationships, outcomes). Preserve concrete names, states, and "
        "outcomes; drop prose flourishes. Do NOT invent anything not present in the "
        "inputs, and do NOT speculate about what happens next. Return ONLY the "
        "state ledger." + lang
    )
    parts = []
    if plan:
        parts.append(f"CHAPTER PLAN:\n{plan}")
    if timeline:
        parts.append("ESTABLISHED FACTS (timeline):\n" + "\n".join(f"- {t}" for t in timeline))
    if prose:
        parts.append("STORY SO FAR (prose to condense):\n\n" + "\n\n".join(prose))
    return system, "\n\n".join(parts)


def cap_recent_prose(prose: list[str], max_chars: int) -> list[str]:
    """D-COMP-COMPRESS-INPUT-CAP — bound the prose fed to compress(): keep the
    MOST-RECENT paragraphs whose total ≤ max_chars (a state summary cares most
    about recency). Always keeps ≥1 (the immediate-preceding paragraph) even if it
    alone exceeds the cap. Returns the kept paragraphs in original order."""
    if max_chars <= 0 or sum(len(p) for p in prose) <= max_chars:
        return prose
    kept: list[str] = []
    budget = max_chars
    for p in reversed(prose):  # newest-first
        if kept and len(p) > budget:
            break
        kept.append(p)
        budget -= len(p)
    return list(reversed(kept))


async def compress(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    prose: list[str], timeline: list[str], plan: str = "",
    source_language: str = "auto", max_tokens: int = max_tokens_for("compress"),
    max_input_chars: int = 24000, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> str:
    """Condense into a re-injectable state summary. Returns "" on any failure
    (caller keeps the raw, budget-trimmed prose). No-op ("" ) when there is
    nothing to compress."""
    if not prose and not timeline:
        return ""
    prose = cap_recent_prose(prose, max_input_chars)
    system, user = build_compress_messages(prose, timeline, plan, source_language)
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "response_format": {"type": "text"}, "temperature": 0.2,
                "max_tokens": max_tokens, **no_thinking_fields(),
            },
            job_meta={"usage_purpose": "context_compress", "extractor": "compress"}, trace_id=trace_id,
            cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("compress LLM error: %s — keeping raw prose", exc)
        return ""
    if getattr(job, "status", None) != "completed":
        logger.info("compress status=%s — keeping raw prose", getattr(job, "status", None))
        return ""
    ledger = extract_judge_content(job.result).strip()
    if not ledger:
        return ""

    # D-LEDGER-DROPS-CAST-ATTRIBUTES — the summariser decides what matters, and it drops the
    # thing that breaks continuity.
    #
    # The prompt above already demands each character's CONDITION and LOCATION. Measured
    # anyway, on two real runs: the ledger recorded the character scene 2 had just introduced
    # as `Condition: Unknown` (gender gone — and scene 3 then contradicted it), and a later
    # ledger listed Elara and The Void but omitted the Scribe entirely. Asking harder is not
    # the fix; the request was already explicit.
    #
    # So the cast facts are carried MECHANICALLY. The same extraction that the seam check
    # proved reliable on this model runs over the prose, and the rows are prepended verbatim.
    # The LLM still writes the narrative ledger — it just no longer gets to decide whether a
    # character's pronoun survives.
    cast = await _cast_state(
        llm, user_id=user_id, model_source=model_source, model_ref=model_ref,
        prose=prose, source_language=source_language, trace_id=trace_id,
        cancel_check=cancel_check)
    return f"{cast}\n\n{ledger}" if cast else ledger


async def _cast_state(
    llm: LLMClient, *, user_id: str, model_source: str, model_ref: str,
    prose: list[str], source_language: str, trace_id: str | None,
    cancel_check: Callable[[], Awaitable[bool]] | None,
) -> str:
    """A deterministic `WHO IS IN THIS: name — pronoun — role` block, or "" if unavailable.

    Degrade-safe on purpose: a failed extraction costs the mechanical guarantee, not the
    summary. The caller still gets the LLM ledger.
    """
    body = "\n\n".join(prose)[-8000:]
    if not body.strip():
        return ""
    try:
        job = await llm.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source, model_ref=model_ref,
            input={"messages": [{"role": "system",
                                 "content": build_extract_prompt(source_language)},
                                {"role": "user", "content": body}],
                   "response_format": {"type": "text"}, "temperature": 0.0,
                   # No `target`: the output is one row per person in the passage and the
                   # count is exactly what the call exists to discover, so any number here
                   # would be invented. `language` is known and IS read on the VERDICT branch.
                   "max_tokens": max_tokens_for("cross_scene_check",
                                                language=source_language),
                   **no_thinking_fields()},
            job_meta={"usage_purpose": "context_compress", "extractor": "cast_state"},
            trace_id=trace_id, cancel_check=cancel_check,
        )
    except LLMError as exc:
        logger.warning("cast-state extract failed (%s) — ledger only", exc)
        return ""
    # A truncated roster parses to ZERO rows, which would build an EMPTY "WHO IS IN THIS"
    # block — a positive claim that the passage has nobody in it, handed to the next
    # scene's drafter. The registry row declares the fatality; degrading to the ledger
    # says less, and saying less is right when the alternative is saying something false.
    if (why := unusable(job, "cross_scene_check")):
        logger.info("cast-state unusable (%s) — ledger only", why)
        return ""
    rows = extract_people(job.result)
    lines = []
    seen: set[str] = set()
    for r in rows:
        who = r["who"].strip()
        key = who.lower().lstrip("the ").strip()
        # A pronoun-only row ("she", "her") names nobody; keeping it would put a bare pronoun
        # in the ledger as if it were a character.
        if not who or key in seen or len(key) < 3 or r["pronoun"] == who.lower():
            continue
        seen.add(key)
        bits = [who]
        if r["pronoun"] != "none":
            bits.append(r["pronoun"])
        if r["role"]:
            bits.append(r["role"])
        lines.append("- " + " — ".join(bits))
        if len(lines) >= 20:
            break
    if not lines:
        return ""
    header = "WHO IS IN THIS (carried verbatim; do not change a name, pronoun or role):"
    return header + "\n" + "\n".join(lines)
