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

from app.config import settings
from app.engine.critic_policy import resolve_critic_refs
from app.engine.canon_check import (
    CanonViolation,
    ReflectResult,
    check_canon,
    judge_plan_conflicts,
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
    drafter_source: str, drafter_ref: str,
    judge_source: str | None, judge_ref: str | None, source_language: str | None,
    plan_supported: bool, trace_id: str | None, cancel_check,
    identity_verified: bool | None = None,
) -> tuple[CheckStatus, list[str]]:
    """Does this draft kill someone the PLAN still needs? Appends any conflict to
    `result.violations` and returns `(CheckStatus, unlinked_names)`.

    The acceptance defect of the whole generation-SSOT run. `gone_cast_in_draft` asks the
    inverse question and cannot see this: the death is being CREATED here, in a draft nothing
    has extracted, so the knowledge snapshot has no row and the symbolic pre-filter finds no
    candidate. Measured on two isolated throwaway books — the scene that kills her and the one
    that does not both returned `guard_status='checked'`.

    TWO TIERS, the same shape the gone-cast check already uses. The symbolic tier is
    `status_effects` — one model's reading of a passage, to which a feint, a dream, a prophecy
    and a body that turns out to be someone else all look identical — so it may only ever
    produce `confirmed=None`, ADVISORY. A DISTINCT judge promotes to `confirmed=True`, HARD,
    which flips `resolved` and blocks publish. With no distinct judge configured the finding
    stays advisory rather than being dropped OR promoted: the drafter that wrote the death
    must not be the model that certifies it.

    Every failure mode returns a STATUS rather than raising: this runs on a draft the author has
    already paid for, and it must never be the reason a generate fails (F1).
    """
    if not plan_supported:
        # The CHAPTER-level paths (single-pass, stitch). They cover many scenes at once, so
        # there is no single position for "who does the plan need AFTER this", and the rung
        # cannot be built. That is NO_POSITION, not NOT_APPLICABLE: the check is relevant here
        # and did not run, which is a GAP, and the whole point of the per-check vocabulary is
        # that a caller can tell those two apart. Reported as NOT_APPLICABLE — as it was until
        # this line — a chapter would read exactly like a scene with nothing after it.
        return CheckStatus.NO_POSITION, []
    if not plan_status:
        # No later scene needs anyone — nothing to contradict. NOT a gap: this is the last
        # scene of the chapter, and calling it one would paint amber on every chapter ending.
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
    candidates = [
        CanonViolation(
            kind=PLAN_CONFLICT_KIND, source="score_symbolic",
            entity_id=c["entity_id"], glossary_entity_id=c["entity_id"],
            name=c["name"], matched=c["name"], status="gone", confirmed=None,
            why=("the prose has this character die or depart, but the plan places them in a "
                 "later scene of this chapter"),
        )
        for c in conflicts
    ]
    judge_unusable = False
    # `identity_verified` is FALSE when provider-registry could not resolve what model a ref
    # actually is (an outage, a deleted row). Two different `user_model_id`s are not two
    # different models — five rows on this box resolve to one — so an unverified identity means
    # we could not establish that the drafter is not certifying its own death. It stays
    # ADVISORY rather than HARD, which is the same direction this function already takes for a
    # judge that is down: a judge we cannot vouch for must not be able to BLOCK a publish.
    may_promote = identity_verified is not False
    if candidates and judge_source and judge_ref and may_promote:
        # ADVISORY → HARD, and ONLY here. The author's rule is *judge confirms ⇒ HARD, no
        # judge ⇒ advisory*, and the caller passes judge_source/ref only when a model DISTINCT
        # from the drafter is configured — the model that wrote the death must not be the one
        # that certifies it (invariant 2). Every failure inside leaves `confirmed=None`.
        candidates, judged = await judge_plan_conflicts(
            llm, user_id=str(user_id), model_source=judge_source, model_ref=judge_ref,
            draft=result.text, candidates=candidates, source_language=source_language or "auto",
            trace_id=trace_id, cancel_check=cancel_check,
        )
        judge_unusable = not judged
    elif candidates and judge_source and judge_ref:
        # Configured, distinct by ref, and UNVERIFIABLE. Not the same state as "no judge
        # configured", and until now the envelope could not tell them apart.
        logger.info("plan-liveness: judge identity unverified — candidates stay advisory")
    result.violations.extend(candidates)
    if any(v.confirmed is True for v in candidates):
        # `reflect_revise` computed `resolved` BEFORE this check existed, from the gone-cast
        # violations only. A confirmed plan conflict is a HARD violation by the same rule, and
        # the publish gate keys on `resolved == false` — leaving it True would give the author
        # a red row on a chapter that still publishes, which is the false-green in reverse.
        result.resolved = False
    if candidates:
        logger.info("plan-liveness conflict: %d candidate(s), %d judge-confirmed",
                    len(candidates), sum(1 for v in candidates if v.confirmed is True))
    if judge_unusable:
        # The judge was configured, was asked, and came back with nothing usable. MEASURED on
        # real 500-word drafts: a judge model reasoned aloud for 5,684 characters and hit the
        # output cap before emitting any JSON (`finish_reason='length'`), so zero verdicts
        # parsed and every candidate stayed `confirmed=None`. That is byte-identical to "the
        # judge looked and declined to confirm" — the blocking tier had stopped existing and
        # the envelope said nothing. UNPARSEABLE is the enum member for exactly this ("the
        # judge answered and the answer could not be used"), and it exists because a guard that
        # cannot report its own silence is the bug this whole arc is about.
        return CheckStatus.UNPARSEABLE, unlinked
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
    # Does THIS path support the plan rung at all? The scene paths do. The chapter-level ones
    # (single-pass, stitch) do not — they cover many scenes, so there is no single position to
    # be "after". False makes the check report NO_POSITION (a declared gap) instead of
    # NOT_APPLICABLE (nothing to check), which are different things and were indistinguishable
    # on the envelope until this flag existed.
    plan_supported: bool = True,
    # T36 / SET-3 — the PER-BOOK half of the role check, read from
    # `composition_work.settings["canon_role_check_enabled"]` by the caller (which owns the
    # Work row; `profile` is a parsed BookProfile and deliberately does NOT carry raw
    # settings, so reading it off `profile` would be a silent no-op — SET-4's exact
    # prohibition). ANDed with the deploy ceiling below.
    role_check_enabled: bool = False,
    draft: str, packed_prompt: str, profile: Any,
    drafter_source: str, drafter_ref: str,
    judge_source: str | None, judge_ref: str | None,
    # Whether provider-registry could confirm the judge is a DIFFERENT MODEL, not merely a
    # different ROW. `None` ⇒ the caller did not resolve it; `False` ⇒ it tried and could
    # not, which keeps a plan conflict advisory rather than publish-blocking.
    identity_verified: bool | None = None,
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
        name_truth_source=audit.truth_source,
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
    # THE EIGHTH COPY, found by audit after S6 collapsed the seven in routers/engine.py.
    # The guard S6 shipped scans that one FILE, so this restatement was invisible to it —
    # an enumerated scope is default-uncovered (NV-2). Now one policy, one rule.
    # KEPT, and I nearly deleted it. My reasoning was that this is a NINTH copy of the
    # distinct-critic rule, strictly weaker than the caller's — a ref comparison cannot see two
    # `user_model_id` rows collapsing to one model — and that the caller blanks the refs when
    # they are not distinct anyway. The first half is true. The second is true OF THE ROUTER,
    # which is the caller I had read. `app/worker/operations.py` passes
    # `judge_source=critic_source or model_source`: on the worker path, no critic configured
    # means the DRAFTER's own refs arrive here. Removing this would have let a model certify
    # its own death on every background generation, which is invariant 2, on the path that
    # runs unattended. A pre-existing test caught it.
    #
    # So this is defence in depth, not duplication — and the identity half below is what the
    # caller adds ON TOP of it, not instead of it.
    distinct = resolve_critic_refs(judge_source, judge_ref, drafter_ref).distinct
    source_language = getattr(profile, "source_language", "auto")

    # The role axis reports COULD-NOT-VERIFY through this, because every failure path in
    # `judge_role_attribution` returns `[]` — the same value a clean check returns. Set by the
    # callback below and folded onto the result after the reflect loop; `nonlocal` rather than
    # a return value so the existing `check_fn` contract (and its callers) are untouched.
    role_degraded: str | None = None

    async def check_fn(text: str) -> list[CanonViolation]:
        nonlocal role_degraded

        def _role_degraded(reason: str) -> None:
            nonlocal role_degraded
            # First reason wins across reflect iterations: the interesting event is that the
            # check stopped being trustworthy, and a later iteration overwriting it with a
            # different failure would hide when that started.
            if role_degraded is None:
                role_degraded = reason

        return await check_canon(
            text, snapshot,
            judge=llm if distinct else None, user_id=str(user_id),
            model_source=str(judge_source) if distinct else "",
            model_ref=str(judge_ref) if distinct else "",
            source_language=source_language, trace_id=trace_id,
            cancel_check=cancel_check,
            # T36 / SET-3 — effective = AND(deploy ceiling, per-book setting).
            # The ceiling answers "is this available at all here?"; the Work's own
            # setting answers "does this author want it?". A ceiling that is off
            # can never be overridden upward by a book.
            role_check=(settings.authoring_canon_role_check_ceiling
                        and role_check_enabled),
            on_role_degraded=_role_degraded,
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
    result.name_truth_source = final_audit.truth_source
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
        judge_source=judge_source, judge_ref=judge_ref,
        identity_verified=identity_verified,
        source_language=getattr(profile, "source_language", None),
        plan_supported=plan_supported, trace_id=trace_id, cancel_check=cancel_check,
    )
    result.unlinked_gone_refs = plan_unlinked
    # The role axis: only reportable when the check was actually asked for. `None` when it was
    # off (nothing was owed), the failure reason when the judge was called and could not
    # answer, and "checked" when it did.
    if settings.authoring_canon_role_check_ceiling and role_check_enabled:
        result.role_check_status = role_degraded or "checked"
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
