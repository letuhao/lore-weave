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
from loreweave_canon_check import resolve_cast_liveness, unresolved_cast_refs
from loreweave_guard import CheckStatus
from loreweave_llm import ReasoningDirective

from app.engine.cowrite import build_revise_messages, revise_draft
from app.engine.name_grounding import audit_names

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
    max_iters: int = 1, reasoning: ReasoningDirective | None = None,
    trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[str, ReflectResult, int]:
    """Run the canon check→revise loop on `draft`. Returns
    (final_text, ReflectResult, revise_output_tokens)."""
    # ── name grounding — runs on EVERY path, including the three that return early below.
    #
    # D-CANON-GUARD-SKIPPED-WHOLE-CHAPTER: those early returns used to be the whole story, so a
    # book with no bound cast got no checking at all. This check needs neither a glossary nor a
    # reading position — only the draft and what the model was shown — so there is no path on
    # which it cannot run, and the case it catches (an invented character) is *most* likely
    # exactly where the old code checked least.
    audit = audit_names(draft, packed_prompt, getattr(profile, "source_language", None))
    name_fields = dict(
        unanchored_names=audit.unanchored, name_near_misses=audit.near_misses,
        name_check_method=audit.method,
    )

    def _name_check(a) -> CheckStatus:
        """S1 — WHY the name check did or did not run, not merely whether it did.

        `caseless_script` is not a failure and not a gap in this guard: the detector is
        capitalisation-based, so on Chinese or Japanese there is nothing for it to see and
        never will be. That is NOT_APPLICABLE. `empty` means there were no grounding names to
        compare against — an empty corpus, which is NO_RULES, computed on the CORPUS and not
        on the matched subset (the rule that keeps a book where nobody has died from rendering
        permanent amber)."""
        if a.method == "capitalised_latin":
            return CheckStatus.CHECKED
        if a.method == "caseless_script":
            return CheckStatus.NOT_APPLICABLE
        return CheckStatus.NO_RULES

    name_status = _name_check(audit)
    # Legacy `coverage` is the CHECKED subset — one source of truth, two shapes.
    name_cov = ["name_grounding"] if name_status is CheckStatus.CHECKED else []
    if audit.near_misses:
        logger.info("draft uses %d name(s) close to but not matching a known one: %s",
                    len(audit.near_misses),
                    ", ".join(f"{n['name']}~{n['closest']}" for n in audit.near_misses))

    # Explicit skip reasons so dirty data (a dangling chapter ref, a knowledge
    # outage) doesn't SILENTLY strip canon protection while reporting a green.
    if not cast_glossary_ids:
        # No entity could be contradicted — but that is NOT "nothing to check", which is what
        # this branch used to assume on its way to returning a green.
        return draft, ReflectResult(
            text=draft, resolved=True, status="skipped_no_cast", coverage=name_cov,
            checks={"canon_cast": CheckStatus.NO_SUBJECT, "name_grounding": name_status},
            **name_fields), 0
    at_order = scene_at_order(scene_sort_order)
    if at_order is None:
        # Has a cast but no resolved reading position → could NOT verify.
        return draft, ReflectResult(
            text=draft, resolved=True, status="skipped_no_position", coverage=name_cov,
            checks={"canon_cast": CheckStatus.NO_POSITION, "name_grounding": name_status},
            **name_fields), 0

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
            trace_id=trace_id, reasoning=reasoning,
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
    # The name audit ran on the FINAL text, which a revise pass may have rewritten — re-run it
    # so the report describes the draft the author receives, not the one before repair.
    final_audit = audit_names(result.text, packed_prompt,
                              getattr(profile, "source_language", None))
    result.unanchored_names = final_audit.unanchored
    result.name_near_misses = final_audit.near_misses
    result.name_check_method = final_audit.method
    # S1 — per-check first; `coverage` is its CHECKED subset. `canon_cast` is DEGRADED (not
    # merely absent from coverage) when the knowledge snapshot could not be read: the guard is
    # fine, its input was not, and those are different things to whoever reads the report.
    #
    # `no_judge` is not distinguished here on purpose: a symbolic-only pass DID check, it just
    # could not confirm, and its findings ride as advisory `confirmed=None` violations. Calling
    # that a coverage gap would paint amber on every book without a configured critic — the
    # exact "permanent amber" failure S1 exists to prevent. S6 owns the judge axis.
    # S2 — resolve the cast PER ENTITY before deciding what the check did. A populated
    # snapshot that happens to carry no status row for any of this scene's cast is an EMPTY
    # CORPUS for this check, not a pass: there was nothing to check against. That is NO_RULES,
    # computed on the corpus and not on the matched subset.
    result.cast_liveness = resolve_cast_liveness(cast_glossary_ids, snapshot)
    unresolved = unresolved_cast_refs(result.cast_liveness)
    result.unresolved_refs = len(unresolved)
    if degraded:
        cast_status = CheckStatus.DEGRADED
    elif result.cast_liveness and len(unresolved) == len(result.cast_liveness):
        cast_status = CheckStatus.NO_RULES
    else:
        cast_status = CheckStatus.CHECKED
    result.checks = {
        "canon_cast": cast_status,
        "name_grounding": _name_check(final_audit),
    }
    result.coverage = sorted(
        k for k, v in result.checks.items() if v is CheckStatus.CHECKED)
    if result.iterations:
        logger.info(
            "A2-S3b canon reflect: project=%s iters=%d resolved=%s remaining=%d",
            project_id, result.iterations, result.resolved, len(result.violations),
        )
    return result.text, result, revise_out_tokens
