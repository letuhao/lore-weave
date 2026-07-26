"""A2-S3b — canon check→revise orchestration for the auto-generate path.

Glues the pieces: fetch the canon snapshot (knowledge `fact_for_check`) at the
scene's position → SCORE symbolic guard → LLM-judge confirm (distinct model) →
`reflect(check→revise ≤N)`. Returns the (possibly revised) winner text + the
ReflectResult (remaining HARD violations + whether resolved) + the extra output
tokens the revise passes spent (so the engine meters the full job).

D1 — runs on the converged winner only. D2 — symbolic fast-path primary +
LLM-judge confirm. CC4 — any knowledge/judge outage degrades to advisory (no
hard violations, no revise), NEVER blocks a generate (F1).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.engine.canon_check import (
    CanonViolation,
    ReflectResult,
    check_canon,
    reflect_revise,
    scene_at_order,
)
from app.engine.cowrite import build_revise_messages, revise_draft

logger = logging.getLogger(__name__)


async def run_canon_reflect(
    *,
    knowledge, llm,
    user_id: UUID, project_id: UUID,
    cast_glossary_ids: list[str], scene_sort_order: int | None,
    draft: str, packed_prompt: str, profile: Any,
    drafter_source: str, drafter_ref: str,
    judge_source: str | None, judge_ref: str | None,
    prompt_estimate: int, max_output_tokens: int,
    max_iters: int = 1, reasoning_effort: str | None = None,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[str, ReflectResult, int]:
    """Run the canon check→revise loop on `draft`. Returns
    (final_text, ReflectResult, revise_output_tokens)."""
    # Explicit skip reasons so dirty data (a dangling chapter ref, a knowledge
    # outage) doesn't SILENTLY strip canon protection while reporting a green.
    if not cast_glossary_ids:
        # Nothing to check — benign (no entities could contradict).
        return draft, ReflectResult(text=draft, resolved=True, status="skipped_no_cast"), 0
    at_order = scene_at_order(scene_sort_order)
    if at_order is None:
        # Has a cast but no resolved reading position → could NOT verify.
        return draft, ReflectResult(text=draft, resolved=True, status="skipped_no_position"), 0

    snapshot = await knowledge.fact_for_check(
        project_id=project_id, at_order=at_order,
        glossary_entity_ids=cast_glossary_ids,
    )
    # Knowledge outage → snapshot None → check_canon returns [] → could NOT verify.
    degraded = snapshot is None

    # The judge must be a DISTINCT model (anti-self-reinforcement §4). No distinct
    # critic configured → symbolic-only (confirmed stays None → ADVISORY, never
    # auto-revised/hard-gated). source_language steers the judge's `why`.
    distinct = bool(judge_ref and judge_source and str(judge_ref) != str(drafter_ref))
    source_language = getattr(profile, "source_language", "auto")

    async def check_fn(text: str) -> list[CanonViolation]:
        return await check_canon(
            text, snapshot,
            judge=llm if distinct else None, user_id=str(user_id),
            model_source=str(judge_source) if distinct else "",
            model_ref=str(judge_ref) if distinct else "",
            source_language=source_language, trace_id=trace_id,
            cancel_check=cancel_check,
        )

    revise_out_tokens = 0
    revise_finish_reason: str | None = None

    async def revise_fn(text: str, hard: list[CanonViolation]) -> str | None:
        nonlocal revise_out_tokens, revise_finish_reason
        messages = build_revise_messages(packed_prompt, profile, text, hard)
        revised, metering = await revise_draft(
            llm.sdk, user_id=str(user_id), model_source=drafter_source,
            model_ref=drafter_ref, messages=messages,
            prompt_token_estimate=prompt_estimate, max_output_tokens=max_output_tokens,
            trace_id=trace_id, reasoning_effort=reasoning_effort,
        )
        revise_out_tokens += metering.output_tokens
        # Track the stop reason of the LAST pass that actually produced text — that
        # output is what reflect_revise keeps as the final draft, so its truncation
        # is the one that matters (D-COMP-TRUNCATION-SURFACING revise-path).
        if revised:
            revise_finish_reason = metering.finish_reason
        return revised or None

    result = await reflect_revise(
        draft=draft, check_fn=check_fn, revise_fn=revise_fn, max_iters=max_iters,
    )
    result.revise_finish_reason = revise_finish_reason
    # `checked` only when the snapshot was actually retrieved; a knowledge
    # outage verified nothing even though reflect_revise ran cleanly.
    result.status = "degraded" if degraded else "checked"
    if result.iterations:
        logger.info(
            "A2-S3b canon reflect: project=%s iters=%d resolved=%s remaining=%d",
            project_id, result.iterations, result.resolved, len(result.violations),
        )
    return result.text, result, revise_out_tokens
