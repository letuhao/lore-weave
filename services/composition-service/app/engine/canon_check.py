"""A2-S3 — SCORE-style symbolic canon guard (deterministic fast-path).

The cheap, near-free PRIMARY canon gate (spec §5.1 / §9 D2): over the
knowledge `fact-for-check` snapshot (status@P + entities), flag any cast member
that is `gone` at the scene's reading position but **present in the draft text**.

This is a *candidate* contradiction — a gone character named in the prose. The
A2-S3b LLM-judge confirms whether it is an actual contradiction (the entity is
ACTING/present) vs legitimate (flashback, memory, corpse, mourning). Keeping the
symbolic guard over-inclusive is intentional: it is the fast pre-filter, the
judge is the precise (and costly) confirmer.

Pure functions — no LLM, no I/O. The caller (A2-S3b engine wiring) fetches the
snapshot via `knowledge_client.fact_for_check` and feeds it here.

D-CANON-CHECK-SDK-UNIFY (2026-07-06): the mechanical pieces (span-matching,
verdict parsing/application, the judge request shape, the base candidate
fields) are shared with knowledge-service's mirror via `loreweave_canon_check`.
What stays HERE (domain-specific, confirmed genuinely divergent in the
unification diff): the prompt wording, the `glossary_entity_id` field, and the
whole check→revise reflect loop (`reflect_revise`/`ReflectResult`) — knowledge's
mirror has no revise-loop equivalent at all.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, computed_field

from loreweave_guard import CheckStatus, GuardReport

from loreweave_canon_check import (
    CanonCandidateBase,
    apply_verdicts,
    build_judge_request,
    extract_judge_text,
    find_span,
    gone_entities_referenced,
    parse_judge_verdicts,
)
from app.llm_budget import max_tokens_for
from app.engine.finding import Locator, SkipReason

logger = logging.getLogger(__name__)

__all__ = [
    "EVENT_ORDER_CHAPTER_STRIDE",
    "scene_at_order",
    "CanonViolation",
    "gone_cast_in_draft",
    "roles_at_position",
    "roles_in_draft",
    "judge_canon",
    "judge_role_attribution",
    "judge_plan_conflicts",
    "check_canon",
    "ReflectResult",
    "canon_envelope",
    "reflect_revise",
]

# Reading-axis stride — the cross-service contract with knowledge-service's
# event_order (= chapter sort_order × stride; CM4). Composition owns this as a
# CONTRACT constant (not an import of a knowledge internal), per the §CM4 note
# "stride = composition cutoff contract".
EVENT_ORDER_CHAPTER_STRIDE = 1_000_000


def scene_at_order(scene_sort_order: int | None) -> int | None:
    """The reading-axis position to check a scene against: the start of its
    chapter on the event_order scale. A death in a STRICTLY-earlier chapter
    (`from_order < sort_order × stride`) makes the entity `gone` for this scene;
    a death within this chapter does not (the character is alive until it
    happens). `None` when the scene's chapter has no resolved sort_order — the
    caller then skips the symbolic guard (advisory only)."""
    if scene_sort_order is None:
        return None
    return scene_sort_order * EVENT_ORDER_CHAPTER_STRIDE


class CanonViolation(CanonCandidateBase):
    kind: str = "gone_entity_present"
    glossary_entity_id: str | None = None
    # T36 — WHICH relationship a `role_contradiction` is about. `entity_id` is
    # the role's subject, and a subject usually holds SEVERAL roles at a
    # position (on the dogfood book one character held four), so the entity
    # alone does not identify the finding. Measured: the judge flagged a
    # misattributed betrayal and the finding was indistinguishable from one
    # about the same character's `antagonist_of` or `sibling_of` role.
    # None on every other kind.
    predicate: str | None = None
    object_name: str | None = None

    @property
    def locator(self) -> Locator:
        """The entity, plus the surface form that matched — or NOWHERE.

        `plan_conflicts` returns `unlinked` for every asserted-gone name no index entry
        matched, and that list is RETURNED rather than logged precisely because an assertion
        the guard could not place is a hole in coverage. A candidate built for one of those
        has no entity to point at, and saying so is the same answer `self_heal` gives when it
        cannot find its quote: `placed=False`, with the quote kept so a human has a handle.
        """
        if not self.entity_id:
            return Locator.nowhere(quote=self.matched or self.name or "",
                                   why=SkipReason.NOT_LOCATED)
        return Locator.entity(self.entity_id, matched=self.matched, quote=self.span)


def gone_cast_in_draft(
    draft: str, snapshot: dict[str, Any] | None,
) -> list[CanonViolation]:
    """Symbolic candidates: every `gone` entity in the snapshot whose name (or
    canonical_name) appears in `draft`. Empty when the snapshot is absent (the
    guard degrades to advisory — a knowledge outage never blocks). De-duped per
    entity (the first matching name form wins)."""
    rows = gone_entities_referenced(draft, snapshot, extra_field="glossary_entity_id")
    return [
        CanonViolation(
            entity_id=r["entity_id"], glossary_entity_id=r.get("glossary_entity_id"),
            name=r["name"], span=r["span"], matched=r["matched"],
        )
        for r in rows
    ]


# ── T36 · roles at the reading position (D-CANON-CHECK-BLIND-TO-ROLE) ───
#
# The guard above asks ONE question: "is a `gone` entity being treated as
# present?" The register's acceptance case asks a different one — *"is the trap
# attributed to the cast-designated antagonist?"* — and until now no code path
# posed it. The snapshot has carried a `relations` list all along; nothing in
# this service read it.
#
# Two things had to be true before that could be fixed, and the first was not:
#
#   1. The relations must be POSITION-WINDOWED. They were not — `fact_for_check`
#      served every relation as currently-true regardless of reading position,
#      so 175 of the dev graph's 619 positioned edges were already-ended roles
#      presented as live. Fixed in knowledge-service (T36 axis half); the
#      snapshot's relations are now the roles in force AT `at_order`, each
#      carrying the interval that answered.
#   2. Something must READ them. That is this block.
#
# The symbolic layer here is a RELEVANCE filter, deliberately over-inclusive in
# the same way `gone_cast_in_draft` is: it decides which roles this passage
# could possibly contradict, and the judge decides whether it does. A role is
# relevant when either endpoint is named in the draft — misattribution reads
# both ways ("the wrong character does X to the role's object" and "the role's
# bearer does something the role forbids"), so filtering on the subject alone
# would miss half the case the acceptance test is about.


def roles_at_position(snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The roles in force at the snapshot's reading position, normalised.

    A thin, defensive projection of `snapshot["relations"]` — the payload
    crosses a service boundary, so a missing key or a non-dict row is expected
    input, not an error. Rows without both endpoint names are dropped: a role
    the guard cannot NAME cannot be put to a judge or matched against prose.
    """
    out: list[dict[str, Any]] = []
    for rel in (snapshot or {}).get("relations") or []:
        if not isinstance(rel, dict):
            continue
        subj, obj = rel.get("subject_name"), rel.get("object_name")
        pred = rel.get("predicate")
        if not (isinstance(subj, str) and subj and isinstance(obj, str) and obj):
            continue
        if not (isinstance(pred, str) and pred):
            continue
        out.append({
            "subject_id": rel.get("subject_id"), "subject_name": subj,
            "predicate": pred,
            "object_id": rel.get("object_id"), "object_name": obj,
            # T36 — the interval that answered, carried through from the
            # snapshot so a `why` can say "in force since ch.N" rather than
            # asserting a timeless fact the reader has no way to place.
            "valid_from_ordinal": rel.get("valid_from_ordinal"),
            "valid_to_ordinal": rel.get("valid_to_ordinal"),
        })
    return out


def roles_in_draft(
    draft: str, snapshot: dict[str, Any] | None, *, limit: int = 20,
) -> list[dict[str, Any]]:
    """The roles in force at P that this passage could contradict: those with
    at least one endpoint named in `draft`.

    Over-inclusive on purpose (see the block comment above), but RANKED, in
    three tiers — and the ranking exists because the live data corrected a first
    attempt that had it wrong.

    On the dogfood book at ch.5 the filter selected **20 of 24** roles: a
    protagonist-centric cast names the protagonist in nearly every role AND in
    nearly every passage, so "either endpoint named" is close to a no-op there
    and the CAP becomes the thing that actually decides what the judge sees.
    A cap over an arbitrary order sends an arbitrary 20.

    The obvious ranking — both endpoints named first — is **backwards for the
    case this check exists to catch.** In a misattribution the passage has
    REPLACED the role's holder, so the true holder is exactly the name that is
    absent: canon says `Lâm Trạch betrayed Lâm Uyên`, the draft says Lâm Diệp <!-- doc-language-gate: ok -- stored entity names from the cited corpus; the example is only legible with the real names -->
    did, and only the OBJECT appears. Ranking on both-named buried it.

    So:
      tier 0 — both endpoints named   → the passage discusses both parties;
                                        a stated relationship may be contradicted
      tier 1 — OBJECT named, subject absent → the role's holder is missing from a
                                        passage about its object: the
                                        misattribution shape
      tier 2 — subject named only     → weakest; the role's object is off-scene

    `limit` caps how many reach the judge; the cap is LOGGED when it bites,
    because a silently truncated role set reads to every downstream layer
    exactly like a book with few roles.
    """
    if not draft or not snapshot:
        return []
    hits: list[dict[str, Any]] = []
    for role in roles_at_position(snapshot):
        subj_hit = find_span(draft, role["subject_name"])
        obj_hit = find_span(draft, role["object_name"])
        if subj_hit is None and obj_hit is None:
            continue
        if subj_hit is not None and obj_hit is not None:
            tier = 0
        elif obj_hit is not None:
            tier = 1
        else:
            tier = 2
        hit = subj_hit or obj_hit
        hits.append({**role, "matched": hit[0], "span": hit[1], "tier": tier})
    # Stable sort — equal-tier roles keep the snapshot's own order, so the
    # selection is reproducible for a given snapshot rather than dependent on
    # dict iteration luck.
    hits.sort(key=lambda h: h["tier"])
    if len(hits) > limit:
        by_tier = [sum(1 for h in hits if h["tier"] == t) for t in (0, 1, 2)]
        logger.info(
            "canon role check: %d of the roles in force at this position are "
            "named in the draft (tiers both/object-only/subject-only = "
            "%d/%d/%d); sending %d to the judge, strongest first",
            len(hits), *by_tier, limit,
        )
        return hits[:limit]
    return hits


def _build_role_judge_messages(
    draft: str, roles: list[dict[str, Any]], source_language: str,
) -> tuple[str, str]:
    """(system, user) for the role-attribution judge.

    A THIRD distinct question, and it gets its own prompt for the same reason
    `judge_plan_conflicts` does: the other two ask about a character's presence,
    this one asks about a RELATIONSHIP's holder. Kept free of English-only
    illustrative phrasing (the multilingual-judge lesson) — the description of
    what counts is abstract so it does not bias a Vietnamese or CJK judge.
    """
    lang = "" if source_language in ("", "auto") else (
        f" Write each `why` in the language with code '{source_language}'."
    )
    system = (
        "You verify story continuity. Each listed statement is an established "
        "relationship that is TRUE at this point in the story. For each, decide "
        "whether the passage CONTRADICTS it. Answer about THAT statement only.\n"
        "It IS a contradiction when the passage assigns that relationship, or "
        "the act it describes, to a DIFFERENT character than the one named in "
        "the statement. Judge this by what the passage says happened, not by "
        "which names it happens to contain: the named subject being ABSENT from "
        "the passage while someone else performs their role is the clearest "
        "form of this, not a reason to excuse it.\n"
        "It is NOT a contradiction when:\n"
        "- the passage SHOWS, states or confirms the relationship. Agreement is "
        "the opposite of a contradiction. If your reason would say the passage "
        "does what the statement says, answer false.\n"
        "- the passage is silent about the relationship and assigns it to nobody;\n"
        "- a character doubts, conceals, or is mistaken about it in their own words;\n"
        "- the two people are in conflict. Betrayal, hostility, deceit or violence "
        "between them does not END a family tie, a marriage, an alliance or an "
        "acquaintance — a traitor is still the cousin, spouse or ally they betrayed;\n"
        "- a character is somewhere other than a place the statement records. "
        "Moving is not a contradiction.\n"
        "Prefer false when unsure: a false alarm on correct prose costs the author "
        "more than a missed one.\n"
        "Return ONLY a JSON object "
        '{"verdicts":[{"entity_id":str,"violated":bool,"why":str}]}, using the '
        "entity_id given for each statement, which identifies the STATEMENT "
        "and not any character." + lang
    )
    # The `entity_id` handed to the judge is a per-STATEMENT token (`role_0`,
    # `role_1`, …), not the subject's real entity id.
    #
    # MEASURED, on the acceptance book with a real model: given the subject's
    # entity id, the judge correctly spotted that the passage gave a betrayal to
    # the wrong character — and returned the id of the character it was
    # ACCUSING rather than the id of the statement being contradicted. That id
    # also appeared in the list (as the subject of an unrelated `sibling_of`
    # role), so the verdict silently attached to the wrong relationship. The
    # finding read correct and pointed somewhere false, which is worse than
    # missing it. A token that names no character removes the ambiguity.
    listed = "\n".join(
        f'- entity_id=role_{i} "{r["subject_name"]}" '
        f'{r["predicate"]} "{r["object_name"]}"'
        for i, r in enumerate(roles)
    )
    user = f"ESTABLISHED RELATIONSHIPS AT THIS POINT:\n{listed}\n\nPASSAGE:\n{draft}"
    return system, user


async def judge_role_attribution(
    judge, *, user_id: str, model_source: str, model_ref: str,
    draft: str, roles: list[dict[str, Any]], source_language: str = "auto",
    max_tokens: int | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    on_degraded: Callable[[str], None] | None = None,
) -> list[CanonViolation]:
    """Ask whether the passage contradicts any role in force at P.

    ⚠️ `on_degraded` exists because EVERY failure path here returns `[]`, which is the same
    value a clean check returns. Without it the caller cannot tell *"the judge checked and
    found nothing"* from *"the judge never ran"* — and the canon envelope reported the second
    as the first. See the `no_verdicts` branch below for the live run that showed it.

    Returns only the roles the judge AFFIRMED, as `role_contradiction`
    candidates. That is the opposite convention from `judge_canon`, and
    deliberately so: there the symbolic layer already found something suspicious
    (a gone character named in the prose) and the judge narrows it, so an
    unjudged candidate is still worth surfacing as advisory. Here the symbolic
    layer only established RELEVANCE — "this role is mentioned" is not evidence
    of anything — so an unconfirmed role is not a finding and must not be
    reported as one.

    CC4: every LLM/parse failure returns `[]` (nothing affirmed) rather than
    raising. A judge that is down must not block a generate, and must not invent
    a violation either.
    """
    if not roles:
        return []
    from loreweave_llm.errors import LLMError

    max_tokens = max_tokens or max_tokens_for(
        "judge_canon", target=len(roles), language=source_language)
    system, user = _build_role_judge_messages(draft, roles, source_language)
    req = build_judge_request(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        usage_purpose="canon_check", extractor="judge_role_attribution",
        max_tokens=max_tokens,
    )
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref, trace_id=trace_id, cancel_check=cancel_check, **req,
        )
    except LLMError as exc:
        logger.warning("judge_role_attribution degraded (LLM error): %s — no role findings", exc)
        if on_degraded:
            on_degraded("llm_error")
        return []
    if getattr(job, "status", None) != "completed":
        logger.info("judge_role_attribution status=%s → no role findings",
                    getattr(job, "status", None))
        if on_degraded:
            on_degraded(f"job_{getattr(job, 'status', None)}")
        return []
    verdicts = parse_judge_verdicts(extract_judge_text(job.result))
    if not verdicts:
        # A COMPLETED job whose text yielded nothing — the same
        # completed-and-useless case `judge_plan_conflicts` documents, logged
        # with `finish_reason` so an operator sees "length" rather than silence.
        logger.warning(
            "judge_role_attribution produced NO verdicts for %d role(s) "
            "(finish_reason=%s) — the role check did not run",
            len(roles), (job.result or {}).get("finish_reason"),
        )
        # ⚠️ AND TELL THE CALLER, not just the log.
        #
        # Measured live 2026-08-12 (job `019ff401` on the acceptance book): 24 roles in force
        # at the position, 20 sent to the judge, `tokens_used=0`, an empty completion — and a
        # canon envelope carrying `status: checked`, `violations: []`, `resolved: true`. An
        # author reads that as canon-clean. The WARNING above is in the log, and **the log is
        # not the verdict.**
        #
        # This is the shape the same file already guards elsewhere with `skipped_no_cast` /
        # `skipped_no_position`: *"explicit skip reasons so dirty data doesn't SILENTLY strip
        # canon protection while reporting a green."* The role axis was the one without one.
        if on_degraded:
            on_degraded("no_verdicts")
        return []
    # `parse_judge_verdicts` returns `{entity_id: {violated, why}}`, not a list.
    # Keyed by the per-statement token so a verdict lands on the ROLE it was
    # asked about — see `_build_role_judge_messages` for what happened when it
    # was keyed by the subject's entity id.
    out: list[CanonViolation] = []
    for i, r in enumerate(roles):
        v = verdicts.get(f"role_{i}")
        if v is None or v.get("violated") is not True:
            continue
        out.append(CanonViolation(
            kind="role_contradiction",
            source="llm_judge",
            entity_id=str(r["subject_id"]),
            name=r["subject_name"],
            # NOT "gone" — this candidate says nothing about liveness, and
            # inheriting the base default would make it read as if it did.
            status="role",
            span=r.get("span", ""),
            matched=r.get("matched", ""),
            confirmed=True,
            why=str(v.get("why") or ""),
            predicate=r["predicate"],
            object_name=r["object_name"],
        ))
    return out


# ── LLM-judge: confirm acting-vs-mentioned (A2-S3b, spec §9 D2) ─────────

def _build_judge_messages(
    draft: str, candidates: list[CanonViolation], source_language: str,
) -> tuple[str, str]:
    """(system, user) for the canon judge. Abstract + multilingual-safe (no
    English-only illustrative phrases — they bias a CJK/VN judge; the lesson)."""
    lang = "" if source_language in ("", "auto") else (
        f" Write each `why` in the language with code '{source_language}'."
    )
    system = (
        "You verify story continuity. Each listed character is GONE (dead, "
        "destroyed, departed, or lost) before this passage. For each, decide "
        "whether the passage portrays them as an ACTIVE PRESENCE now — acting, "
        "speaking, perceiving, or bodily present — which is a continuity "
        "violation. A reference that is a memory, flashback, mention of their "
        "absence/death, a corpse, or others speaking ABOUT them is NOT a "
        "violation. Return ONLY a JSON object "
        '{"verdicts":[{"entity_id":str,"violated":bool,"why":str}]}.' + lang
    )
    listed = "\n".join(
        f'- entity_id={c.entity_id} name="{c.name}" (near: {c.span})'
        for c in candidates
    )
    user = f"GONE CHARACTERS REFERENCED:\n{listed}\n\nPASSAGE:\n{draft}"
    return system, user


async def judge_canon(
    judge, *, user_id: str, model_source: str, model_ref: str,
    draft: str, candidates: list[CanonViolation], source_language: str = "auto",
    max_tokens: int | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[CanonViolation]:
    """Confirm the symbolic candidates with the LLM-judge (D2 — only the cheap
    SCORE pre-filter runs on everything; the judge confirms the few candidates).
    Sets `confirmed`/`why` per candidate.

    CC4 (critic-degrade lesson): any LLM/parse failure leaves `confirmed=None`
    (symbolic-only → ADVISORY, never auto-revised/hard-gated) — the judge must
    never block on its own failure. A candidate the judge omits is also left
    `confirmed=None`."""
    if not candidates:
        return []
    from loreweave_llm.errors import LLMError

    # THE SIGNAL, not a constant. `budget_for` takes `target` (how many verdicts) and
    # `language` (a Vietnamese `why` costs 2.6 tokens/word against English's 1.7) and until
    # 2026-08-01 the VERDICT kind ignored both — `base = 0.0`, "the floor IS the model" — so
    # every judge call here was the renamed constant this SDK's own docstring warns about.
    # Resolved per call rather than as a default argument because the count is not knowable
    # at import time.
    max_tokens = max_tokens or max_tokens_for(
        "judge_canon", target=len(candidates), language=source_language)
    system, user = _build_judge_messages(draft, candidates, source_language)
    req = build_judge_request(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        usage_purpose="canon_check", extractor="judge_canon", max_tokens=max_tokens,
    )
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref, trace_id=trace_id, cancel_check=cancel_check, **req,
        )
    except LLMError as exc:
        logger.warning("judge_canon degraded (LLM error): %s — symbolic-only", exc)
        return candidates
    if getattr(job, "status", None) != "completed":
        logger.info("judge_canon status=%s → symbolic-only", getattr(job, "status", None))
        return candidates
    verdicts = parse_judge_verdicts(extract_judge_text(job.result))
    apply_verdicts(candidates, verdicts)   # /review-impl #3 — surfaces the judge's why
    return candidates


def _build_plan_conflict_messages(
    draft: str, candidates: list[CanonViolation], source_language: str,
) -> tuple[str, str]:
    """(system, user) for the plan-liveness judge.

    A DIFFERENT question from `judge_canon`'s, which is why it gets its own prompt rather than
    a shared one. That judge asks *"this character is already gone — is the passage treating
    them as present?"*. This one asks *"the passage appears to END this character — is that
    real and permanent, here, now?"*, because the plan-liveness candidate was raised by an
    extractor reading THIS passage, and `status_effects` cannot tell a death from a feint, a
    dream, a vision, a prophecy, a near-miss, a metaphor, or somebody else's body.

    Kept free of English-only illustrative phrasing (the multilingual-judge lesson): the list
    of what does NOT count is abstract, so it does not bias a Vietnamese or CJK judge.
    """
    lang = "" if source_language in ("", "auto") else (
        f" Write each `why` in the language with code '{source_language}'."
    )
    system = (
        "You verify story continuity. For each listed character, the passage appears to end "
        "their presence — death, departure, or destruction. Decide whether the passage "
        "ACTUALLY establishes that as a real, permanent event happening now. It is NOT real "
        "if the passage presents it as imagined, dreamed, foreseen, feared, remembered, "
        "hypothetical, figurative, attempted-but-survived, or as happening to someone else. "
        "Answer `violated: true` ONLY when the character truly and permanently ceases to be "
        "present from this point on. Return ONLY a JSON object "
        '{"verdicts":[{"entity_id":str,"violated":bool,"why":str}]}.' + lang
    )
    listed = "\n".join(f'- entity_id={c.entity_id} name="{c.name}"' for c in candidates)
    user = f"CHARACTERS THE PASSAGE APPEARS TO END:\n{listed}\n\nPASSAGE:\n{draft}"
    return system, user


async def judge_plan_conflicts(
    judge, *, user_id: str, model_source: str, model_ref: str,
    draft: str, candidates: list[CanonViolation], source_language: str = "auto",
    max_tokens: int | None = None, trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[list[CanonViolation], bool]:
    """Promote plan-liveness candidates from ADVISORY to HARD — or clear them.

    The author's decision, verbatim: *judge confirms ⇒ HARD, no judge ⇒ advisory*. So this is
    the only thing that may set `confirmed=True` on a `plan_liveness_conflict`, and the caller
    must only reach it with a DISTINCT judge model (invariant 2 — no model is silently its own
    judge; the drafter that wrote the death must not be the one that certifies it).

    CC4: every LLM/parse failure leaves `confirmed=None`, i.e. the candidate stays advisory.
    A judge that is down must not be able to BLOCK a publish, and must not clear one either.

    Returns `(candidates, judged)`. `judged` is False when the call produced NO usable verdict
    at all, and the second value exists because the first one cannot carry that fact: an
    unjudged candidate and a candidate the judge declined to confirm are both `confirmed=None`.

    MEASURED on real 500-word drafts, 2026-08-01, and it is why this returns a flag rather than
    logging and moving on: a judge model spent 5,684 characters reasoning aloud in Vietnamese
    and hit the output cap BEFORE emitting any JSON — `finish_reason='length'`, zero verdicts
    parsed, every candidate left `confirmed=None`. The blocking tier had silently stopped
    existing and the envelope read exactly as if the judge had looked and declined. Short
    fixture passages never reproduced it: the earlier 3/3 live validation used three-sentence
    excerpts, and it passed for that reason.
    """
    if not candidates:
        return [], True
    from loreweave_llm.errors import LLMError

    # Sized per verdict and per language — see judge_canon above for why this is resolved
    # here and not as a default argument.
    max_tokens = max_tokens or max_tokens_for(
        "judge_plan_conflict", target=len(candidates), language=source_language)
    system, user = _build_plan_conflict_messages(draft, candidates, source_language)
    req = build_judge_request(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        usage_purpose="canon_check", extractor="judge_plan_conflict", max_tokens=max_tokens,
    )
    try:
        job = await judge.submit_and_wait(
            user_id=user_id, operation="chat", model_source=model_source,
            model_ref=model_ref, trace_id=trace_id, cancel_check=cancel_check, **req,
        )
    except LLMError as exc:
        logger.warning("judge_plan_conflict degraded (LLM error): %s — advisory", exc)
        return candidates, False
    if getattr(job, "status", None) != "completed":
        logger.info("judge_plan_conflict status=%s → advisory", getattr(job, "status", None))
        return candidates, False
    verdicts = parse_judge_verdicts(extract_judge_text(job.result))
    if not verdicts:
        # A COMPLETED job whose text yielded nothing. `status == completed` does not mean the
        # model finished its sentence — a truncated reply is completed-and-useless, and
        # `finish_reason` is the only thing that says which. Logged with the reason so the
        # operator sees "length" (raise the budget, or pick a judge that answers directly)
        # rather than a mystery.
        logger.warning(
            "judge_plan_conflict produced NO verdicts for %d candidate(s) "
            "(finish_reason=%s) — the HARD tier did not run",
            len(candidates), (job.result or {}).get("finish_reason"),
        )
        return candidates, False
    apply_verdicts(candidates, verdicts)
    return candidates, True


async def check_canon(
    draft: str, snapshot: dict[str, Any] | None, *,
    judge=None, user_id: str = "", model_source: str = "", model_ref: str = "",
    source_language: str = "auto", trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
    role_check: bool = False,
    on_role_degraded: Callable[[str], None] | None = None,
) -> list[CanonViolation]:
    """Full canon check on a draft: SCORE symbolic pre-filter → (if any
    candidates AND a distinct judge is configured) LLM-judge confirmation.
    Returns ALL candidates with `confirmed` set (True/False by the judge, or
    None when no judge ran). The caller treats `confirmed is True` as HARD.

    T36 — when `role_check` is on, ALSO asks whether the passage contradicts a
    role in force at this position, and appends any affirmed contradictions.
    That is a SECOND judge call on scenes that have roles but no gone-cast
    candidate, i.e. new spend on the common path, so it is off by default and
    the caller opts in (`spend-causing-setting-fails-closed`). The role check
    never suppresses a gone-cast finding; it only adds.
    """
    candidates = gone_cast_in_draft(draft, snapshot)
    judged = judge is not None and bool(model_ref)
    if candidates and judged:
        candidates = await judge_canon(
            judge, user_id=user_id, model_source=model_source, model_ref=model_ref,
            draft=draft, candidates=candidates, source_language=source_language,
            trace_id=trace_id, cancel_check=cancel_check,
        )
    if not role_check or not judged:
        return candidates
    roles = roles_in_draft(draft, snapshot)
    if not roles:
        return candidates
    return candidates + await judge_role_attribution(
        judge, user_id=user_id, model_source=model_source, model_ref=model_ref,
        draft=draft, roles=roles, source_language=source_language,
        trace_id=trace_id, cancel_check=cancel_check,
        on_degraded=on_role_degraded,
    )


# ── reflect: check → revise ≤ N (spec §6/§8.3) ─────────────────────────

class ReflectResult(BaseModel):
    # Whether the canon guard actually ran, so a SKIP isn't a silent false-green:
    #   checked            — the guard ran over a real position + cast.
    #   skipped_no_cast    — the scene has no cast entities (nothing to check).
    #   skipped_no_position— the scene has a cast but no resolved reading position
    #                        (dirty/dangling chapter ref) → could NOT verify.
    #   degraded           — knowledge unavailable → could NOT verify.
    # `resolved=True` only means "no confirmed contradiction"; on a non-`checked`
    # status it means "nothing was verified", which the FE + publish-gate surface
    # so dirty data doesn't silently strip canon protection.
    status: str = "checked"
    # The ROLE axis, which had no status of its own until 2026-08-12.
    #
    #   None          — the role check was not requested, or there were no roles to ask
    #                   about. Nothing was owed, so nothing is reported.
    #   "checked"     — the judge answered.
    #   "no_verdicts" — the judge was CALLED and returned nothing usable.
    #   "llm_error" / "job_<status>" — it could not be called at all.
    #
    # Anything other than None/"checked" means COULD NOT VERIFY. It is a separate field
    # rather than a `checks` entry deliberately: `checks` feeds `coverage`, and the note in
    # `canon_reflect` explains why the judge axis is kept out of that calculation — it would
    # paint permanent amber on every book with no configured critic. This reports a judge
    # that FAILED, which is a different claim from one that was never configured.
    role_check_status: str | None = None
    # ── S1 · the honest primitive ────────────────────────────────────────────────────────
    # PER-CHECK status (`loreweave_guard.CheckStatus`), because this guard is a COMPOSITE and
    # a scalar makes it lie in one direction or the other: `status` above describes the
    # gone-cast check ONLY, so a run where name-grounding fired and cast-liveness could not
    # run has no honest single value.
    #
    # `status` is deliberately LEFT ALONE and still emits its legacy strings — they are
    # persisted in `generation_job.result` and matched by SQL in OutlineRepo.chapter_scene_gate.
    # Additive-then-switch (the S11 discipline): the new shape ships beside the old one, and
    # nothing that reads the old one changes behaviour until its own measurement says it may.
    checks: dict[str, str] = Field(default_factory=dict)
    # ── S2 · one cast-liveness SSOT, per ENTITY ───────────────────────────────────────────
    # `{entity_id: {"status", "source"}}`. `gone_cast_in_draft` answers only "which of these is
    # marked gone AND named in the draft", so every entity it omits reads as fine — an entity
    # the graph has never heard of is indistinguishable from one it knows is alive.
    cast_liveness: dict[str, dict[str, str]] = Field(default_factory=dict)
    #: Cast ids NO layer could speak to (KG silent, plan silent). The eval's
    #: `unresolved_cast_reference` class reads this and was BLIND without it — the field had
    #: zero occurrences anywhere in the service. A COUNT OF FACTS, not of failures: a book
    #: early in its life legitimately has a cast the graph has not caught up with.
    unresolved_refs: int = 0
    #: Names the draft asserts are GONE that the cast name-index could not resolve to an
    #: entity. NOT a count of failures — prose legitimately kills people who are not in the
    #: plan's cast. It exists so "the check ran and found nothing" is distinguishable from "the
    #: check found something it could not place": the live POC hit the second (glossary held the
    #: cast with an empty `cached_name`) and a version without this field read as clean.
    unlinked_gone_refs: list[str] = Field(default_factory=list)
    #
    # `status` describes the gone-cast check only, and on a book with no bound cast it read
    # `skipped_no_cast` while `resolved=True` and `violations=[]` — honest field by field, and
    # green to anything that looks at the two fields a caller naturally looks at. Measured
    # 2026-08-01: a 4-scene, 8,116-word chapter generated with every scene reporting that, an
    # invented character in three of them, and nothing anywhere saying "no check ran".
    #
    # A guard whose coverage is conditional on data the author may never have created must
    # REPORT its coverage. Empty list = nothing was verified.
    #
    # S1: this is now DERIVED from `checks` (the CHECKED subset). Kept as a field rather than a
    # property because callers assign to it, and because it is what three envelopes already
    # ship — but there is one source of truth behind it now.
    coverage: list[str] = Field(default_factory=list)
    # Names in the draft that appear nowhere in what the model was shown. Advisory by
    # construction — fiction introduces names — but `name_near_misses` is the sharper signal:
    # a name 1-2 edits from one the story already uses ("Mira" ← "Mina") is a corruption.
    unanchored_names: list[str] = Field(default_factory=list)
    name_near_misses: list[dict] = Field(default_factory=list)
    #: capitalised_latin | caseless_script | empty — a check that cannot see must say so
    #: rather than report a clean result (the `realised_words` discipline).
    name_check_method: str = ""
    text: str                                    # final draft (possibly revised)
    # Remaining violations the author should see: confirmed-HARD (confirmed=True)
    # AND ADVISORY (confirmed=None — symbolic-only, the judge was down/not-distinct
    # /silent). Judge-CLEARED candidates (confirmed=False) are excluded. The gate
    # blocks on the hard subset; advisory is flag-and-override (D4). /review-impl #1.
    violations: list[CanonViolation] = Field(default_factory=list)
    iterations: int = 0                          # revise passes actually run
    resolved: bool = True                        # no confirmed-HARD violations remain
    # D-COMP-TRUNCATION-SURFACING: the stop reason of the revise pass that produced
    # the final `text` ("length" ⇒ that repair itself hit the cap, so `text` may be
    # truncated even when the original winner draft was not). None when no revise
    # pass produced text (no repair, or the reviser gave up). The engine ORs this
    # into the job's `truncated` flag so a truncating repair isn't a silent green.
    revise_finish_reason: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def guard_status(self) -> str:
        """S1 — the HONEST headline, derived from `checks` by `loreweave_guard.GuardReport`.

        Distinct from `status`, and it has to be: `status` is one check's verdict wearing the
        guard's name. The measured consequence was `status="skipped_no_cast"` counting as a
        checked chapter in `chapter_scene_gate`'s SQL, which lists only
        `('skipped_no_position','degraded')` as unchecked — so the ONE state in which the guard
        verified nothing at all was the one the publish gate treated as fine.

        `computed_field` so it serialises: this rides in `generation_job.result` and the gate
        SQL reads it back. A plain `@property` would be invisible to `model_dump`, which is
        how a derived field becomes a field that exists only in Python.
        """
        return str(self._report().status)

    def _report(self) -> GuardReport:
        """The S1 primitive, built once per read.

        Review finding, 2026-08-01: `loreweave_guard` was imported for its ENUM and its ranking
        function while `GuardReport` itself — the shape the whole package argues for — had zero
        production consumers, and `guard_status` / `coverage` were two hand-rolled restatements
        of `.status` / `.covered`. A primitive that exists only in its own tests is the same
        defect this file's S6 note names in the critic setting; it took a second reading to see
        it here. `raw_verdict` is `resolved`, which is what makes `verdict` below answerable.
        """
        return GuardReport(checks=dict(self.checks), raw_verdict=self.resolved)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verdict(self) -> bool | None:
        """`resolved`, but ONLY if something actually verified it — else None.

        `resolved` alone cannot carry this: it ships `True` on the `skipped_no_cast` early
        return, where nothing ran. Every consumer therefore has to remember to AND it with a
        status check, and `CanonGatePanel` was doing exactly that by hand in TypeScript
        (`checked && canon.resolved && …`) — the rule restated in a second language, where no
        Python test can hold it. This is that conjunction, computed once, on the side that has
        the tests.

        `resolved` stays untouched and keeps its legacy meaning: it is persisted and matched by
        SQL in `chapter_scene_gate`, and the gate deliberately blocks on a contradiction found
        during a DEGRADED run — a "did we find something" question, which is not the "did we
        pass" question this field answers.
        """
        return self._report().verdict


def canon_envelope(reflect: "ReflectResult") -> dict[str, Any]:
    """The `result.canon` block, built ONCE.

    Review finding, 2026-08-01: this dict was hand-written in SIX places — three in
    `worker/operations.py`, three in `routers/engine.py` — with identical keys and identical
    comments. The measured consequence is precise: S1's `guard_status` was added to all six,
    and the `verdict` field added minutes earlier reached NONE of them, so a live run showed
    `guard_status='checked'` beside an EMPTY verdict while `CanonGatePanel` had already been
    changed to read it.

    SIX, not four: the first sweep found four, and `test_there_is_no_FIFTH_hand_built_canon_
    envelope` immediately red-flagged two more that the pattern had missed. Counting copies by
    eye is how the count was wrong in the first place — hence the test, which is the real fix.

    Deliberately NOT `reflect.model_dump()`: `text` is the draft (it does not belong in a
    verdict envelope) and `revise_finish_reason` is ORed into the job's own `truncated` flag by
    the caller rather than nested here. The projection is the point — but it is one projection.
    """
    return {
        "violations": [v.model_dump() for v in reflect.violations],
        "resolved": reflect.resolved,
        # S1 — `resolved` AND something-actually-checked. The FE's green all-clear keys on this
        # so the rule lives on the side that has tests for it.
        "verdict": reflect.verdict,
        "iterations": reflect.iterations,
        # D-CANON-GUARD-SKIPPED-WHOLE-CHAPTER — WHAT RAN, and what it saw. `status` alone read
        # green on a book with no bound cast; the whole 8,116-word chapter that exposed this was
        # generated with `coverage` empty and nobody able to tell.
        "coverage": reflect.coverage,
        # S1 — the per-check block + its derived headline. Both ride the envelope:
        # `chapter_scene_gate` reads `guard_status` back out of `generation_job.result`.
        "checks": reflect.checks,
        "guard_status": reflect.guard_status,
        # S2 — the per-entity cast resolution + the count no layer could speak to.
        # `unresolved_cast_reference` in the eval was BLIND on this field.
        # The role axis rides the envelope for exactly the reason `unlinked_gone_refs` does
        # below: a consumer that cannot see what the guard failed to do will render its
        # silence as an all-clear.
        "role_check": reflect.role_check_status,
        "cast_liveness": reflect.cast_liveness,
        "unresolved_refs": reflect.unresolved_refs,
        # The plan-liveness check's own gap list. Rides the envelope for the same reason
        # `unresolved_refs` does: a FE that cannot see what the guard could not place will
        # render its silence as an all-clear.
        "unlinked_gone_refs": reflect.unlinked_gone_refs,
        "unanchored_names": reflect.unanchored_names,
        "name_near_misses": reflect.name_near_misses,
        "name_check_method": reflect.name_check_method,
        # LEGACY scalar, kept verbatim: it is persisted and matched by SQL.
        "status": reflect.status,
    }


def unguarded_envelope(reason: str) -> dict[str, Any]:
    """The `result.canon` block for a path that runs NO canon check — a DECLARATION.

    Why this exists, and why it is not "just leave the block out"
    ------------------------------------------------------------
    The two composition SSE generators hand user-visible prose to an author and mention
    `canon` zero times. That is a defensible design position on an interactive path — a
    multi-second judge pass between keystrokes is a different product — but the *silence* is
    not. A `done` frame with no canon block and a `done` frame from a fully-checked draft are
    the same bytes to a reader, so "nobody checked this" renders exactly like "checked, clean".
    Same shape as the Go KG sweep, the Rust zone narration, and every other finding this run.

    So the streams say so. `guard_status` is `not_run`, which the vocabulary added for this
    case precisely because `not_applicable` renders as NOTHING by design and would have
    re-created the silence under a new name.

    Every key `canon_envelope` produces is present, with its empty value, so a consumer reads
    ONE shape whichever path produced it. That parity is asserted by a test rather than trusted
    — the six-hand-written-copies defect this module's other builder was extracted from began
    as two dicts that agreed on the day they were written.

    `guard_reason` is the extra key: WHY the guard did not run, in the author's terms. A status
    with no reason is a badge nobody can act on.
    """
    return {
        "violations": [],
        "resolved": None,
        "verdict": None,
        "iterations": 0,
        "coverage": {},
        "checks": {},
        "guard_status": CheckStatus.NOT_RUN.value,
        "guard_reason": reason,
        "role_check": None,
        "cast_liveness": {},
        "unresolved_refs": [],
        "unlinked_gone_refs": [],
        "unanchored_names": [],
        "name_near_misses": [],
        "name_check_method": None,
        "status": None,
    }


async def reflect_revise(
    *,
    draft: str,
    check_fn: Callable[[str], Awaitable[list[CanonViolation]]],
    revise_fn: Callable[[str, list[CanonViolation]], Awaitable[str | None]],
    max_iters: int = 1,
) -> ReflectResult:
    """The §8.3 `reflect(N): loop[check → revise]`. `check_fn(draft)` returns the
    violations (already judge-confirmed); a violation is HARD when
    `confirmed is True`. While there are hard violations and budget remains,
    `revise_fn(draft, hard)` produces a repaired draft; re-check. Stops when no
    hard violations remain, the reviser returns None (give up → keep last), or
    `max_iters` is exhausted (→ escalate: caller hard-gates the remainder)."""
    current = draft
    last_checked = await check_fn(current)
    iterations = 0
    while iterations < max_iters:
        hard = [v for v in last_checked if v.confirmed is True]
        if not hard:
            break
        revised = await revise_fn(current, hard)
        iterations += 1
        if not revised or revised == current:
            break  # reviser gave up or no-op → stop, keep current + its violations
        current = revised
        last_checked = await check_fn(current)
    # Surface hard + advisory (drop only judge-CLEARED); the gate's `resolved`
    # depends on the HARD subset only (/review-impl #1).
    surfaced = [v for v in last_checked if v.confirmed is not False]
    has_hard = any(v.confirmed is True for v in last_checked)
    return ReflectResult(
        text=current, violations=surfaced, iterations=iterations,
        resolved=not has_hard,
    )
