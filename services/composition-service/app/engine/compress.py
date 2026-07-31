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
from app.llm_budget import max_tokens_for

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
    return extract_judge_content(job.result).strip()
