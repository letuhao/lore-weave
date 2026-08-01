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
from loreweave_extraction.extractors.event import extract_events
from loreweave_guard import CheckStatus, GuardReport, check_over

from app.engine.plan_conflict import (
    PLAN_CONFLICT_KIND,
    asserted_gone,
    name_index,
    plan_conflicts,
)
from loreweave_llm import ReasoningDirective

from app.engine.cowrite import build_revise_messages, revise_draft
from app.engine.name_grounding import audit_names

logger = logging.getLogger(__name__)


async def _check_plan_liveness(
    llm, result, *, user_id: UUID, plan_status: dict[str, str] | None,
    plan_cast: list[dict[str, Any]] | None,
    drafter_source: str, drafter_ref: str, cancel_check,
) -> tuple[CheckStatus, list[str]]:
    """Does this draft kill someone the PLAN still needs? Appends any conflict to
    `result.violations` and returns `(CheckStatus, unlinked_names)`.

    The acceptance defect of the whole generation-SSOT run. `gone_cast_in_draft` asks the
    inverse question and cannot see this: the death is being CREATED here, in a draft nothing
    has extracted, so the knowledge snapshot has no row and the symbolic pre-filter finds no
    candidate. Measured on two isolated throwaway books — the scene that kills her and the one
    that does not both returned `guard_status='checked'`.

    Advisory tier only (`confirmed=None`). `status_effects` is one model's reading of a passage,
    and a feint, a dream, a prophecy or a body that turns out to be someone else all look the
    same to it. Promoting to HARD is the judge's job (the same two tiers the gone-cast check
    already uses) and is the next slice.

    Every failure mode returns a STATUS rather than raising: this runs on a draft the author has
    already paid for, and it must never be the reason a generate fails (F1).
    """
    if not plan_status:
        # No later scene needs anyone — nothing to contradict. Not a gap.
        return CheckStatus.NOT_APPLICABLE, []
    if not plan_cast:
        # The plan HAS an opinion and we could not fetch the names to join it to. That is a
        # hole, not a pass: without this branch a glossary outage would read as "no conflicts".
        return CheckStatus.UNVERIFIED_INPUT, []
    text = (result.text or "").strip()
    if not text:
        return CheckStatus.NO_SUBJECT, []
    try:
        events = await extract_events(
            text, [], [n for n in (e.get("cached_name") for e in plan_cast) if n],
            user_id=str(user_id), project_id=None,
            model_source=drafter_source, model_ref=drafter_ref,
            llm_client=llm, reasoning_effort="none", cancel_check=cancel_check,
        )
    except Exception:  # noqa: BLE001 — F1: a check never fails a generate.
        logger.warning("plan-liveness extraction failed (advisory)", exc_info=True)
        return CheckStatus.DEGRADED, []

    conflicts, unlinked = plan_conflicts(
        asserted_gone(events), name_index(plan_cast), plan_status)
    for c in conflicts:
        result.violations.append(CanonViolation(
            kind=PLAN_CONFLICT_KIND, source="score_symbolic",
            entity_id=c["entity_id"], glossary_entity_id=c["entity_id"],
            name=c["name"], matched=c["name"], status="gone", confirmed=None,
            why=("the prose has this character die or depart, but the plan places them in a "
                 "later scene of this chapter"),
        ))
    if conflicts:
        logger.info("plan-liveness conflict: %d entity(ies) the plan still needs", len(conflicts))
    # UNLINKED is not clean. The check ran, but on a corpus it could only partly resolve, and
    # the live POC hit exactly this (glossary held the cast with an empty `cached_name`): the
    # death was detected and nothing joined. Reporting `checked` there is the false-green this
    # whole arc exists to kill.
    return (CheckStatus.UNVERIFIED_INPUT if unlinked else CheckStatus.CHECKED), unlinked


async def run_canon_reflect(
    *,
    knowledge, llm,
    user_id: UUID, project_id: UUID,
    cast_glossary_ids: list[str], scene_sort_order: int | None,
    # The PLAN layer of the liveness cascade, produced by the caller (which owns the repo) —
    # `OutlineRepo.plan_liveness_after`. Optional because the chapter-level paths have no single
    # scene position to be "after", and a caller that cannot answer must pass nothing rather
    # than a guess. Absent ⇒ the cascade is KG-only, which is what it was before this review.
    plan_status: dict[str, str] | None = None,
    # The cast rows (`entity_id`, `cached_name`, `cached_aliases`) the plan-liveness join needs.
    # Produced by the caller for the same reason `plan_status` is: it owns the glossary client.
    # Absent while `plan_status` is present ⇒ the check reports UNVERIFIED_INPUT rather than a
    # clean result, because an unjoinable plan is a hole, not an absence of conflicts.
    plan_cast: list[dict[str, Any]] | None = None,
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

    def _early(status: str, cast: CheckStatus) -> "ReflectResult":
        """The two early returns, built from ONE checks dict.

        `coverage` used to be spelled `["name_grounding"] if name_status is CHECKED else []`
        here — a third hand-rolled restatement of `GuardReport.covered`, correct today only
        because `canon_cast` happens never to be CHECKED on these branches. Correct-by-branch
        is how the six copies of the canon envelope stayed consistent right up until the run
        that added a field to five of them.
        """
        checks = {"canon_cast": cast, "name_grounding": name_status}
        return ReflectResult(
            text=draft, resolved=True, status=status,
            coverage=GuardReport(checks=checks).covered, checks=checks, **name_fields)

    if audit.near_misses:
        logger.info("draft uses %d name(s) close to but not matching a known one: %s",
                    len(audit.near_misses),
                    ", ".join(f"{n['name']}~{n['closest']}" for n in audit.near_misses))

    # Explicit skip reasons so dirty data (a dangling chapter ref, a knowledge
    # outage) doesn't SILENTLY strip canon protection while reporting a green.
    if not cast_glossary_ids:
        # No entity could be contradicted — but that is NOT "nothing to check", which is what
        # this branch used to assume on its way to returning a green.
        return draft, _early("skipped_no_cast", CheckStatus.NO_SUBJECT), 0
    at_order = scene_at_order(scene_sort_order)
    if at_order is None:
        # Has a cast but no resolved reading position → could NOT verify.
        return draft, _early("skipped_no_position", CheckStatus.NO_POSITION), 0

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
    result.cast_liveness = resolve_cast_liveness(
        cast_glossary_ids, snapshot, plan_status=plan_status)
    unresolved = unresolved_cast_refs(result.cast_liveness)
    result.unresolved_refs = len(unresolved)
    #
    # The corpus for this check is the cast SOME layer could speak to; `unresolved` is exactly
    # the part no layer could. `check_over` owns the "empty corpus ⇒ NO_RULES, outage ⇒
    # DEGRADED" branch. It is called here rather than restated because it had NO production
    # call site at all until this review — the branch above it was a hand-rolled copy, and a
    # rule with one implementation and one copy has two implementations.
    plan_status_check, plan_unlinked = await _check_plan_liveness(
        llm, result, user_id=user_id, plan_status=plan_status, plan_cast=plan_cast,
        drafter_source=drafter_source, drafter_ref=drafter_ref,
        cancel_check=cancel_check,
    )
    result.unlinked_gone_refs = plan_unlinked
    result.checks = {
        "canon_cast": check_over(
            len(result.cast_liveness) - len(unresolved), degraded=degraded),
        "name_grounding": _name_check(final_audit),
        "plan_liveness": plan_status_check,
    }
    result.coverage = GuardReport(checks=result.checks).covered
    if result.iterations:
        logger.info(
            "A2-S3b canon reflect: project=%s iters=%d resolved=%s remaining=%d",
            project_id, result.iterations, result.resolved, len(result.violations),
        )
    return result.text, result, revise_out_tokens
