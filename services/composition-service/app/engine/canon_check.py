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

from loreweave_guard import GuardReport

from loreweave_canon_check import (
    CanonCandidateBase,
    apply_verdicts,
    build_judge_request,
    extract_judge_text,
    gone_entities_referenced,
    parse_judge_verdicts,
)
from app.llm_budget import max_tokens_for

logger = logging.getLogger(__name__)

__all__ = [
    "EVENT_ORDER_CHAPTER_STRIDE",
    "scene_at_order",
    "CanonViolation",
    "gone_cast_in_draft",
    "judge_canon",
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
    max_tokens: int = max_tokens_for("judge_canon"), trace_id: str | None = None,
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
    max_tokens: int = max_tokens_for("judge_plan_conflict"), trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[CanonViolation]:
    """Promote plan-liveness candidates from ADVISORY to HARD — or clear them.

    The author's decision, verbatim: *judge confirms ⇒ HARD, no judge ⇒ advisory*. So this is
    the only thing that may set `confirmed=True` on a `plan_liveness_conflict`, and the caller
    must only reach it with a DISTINCT judge model (invariant 2 — no model is silently its own
    judge; the drafter that wrote the death must not be the one that certifies it).

    CC4: every LLM/parse failure leaves `confirmed=None`, i.e. the candidate stays advisory.
    A judge that is down must not be able to BLOCK a publish, and must not clear one either.
    """
    if not candidates:
        return []
    from loreweave_llm.errors import LLMError

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
        return candidates
    if getattr(job, "status", None) != "completed":
        logger.info("judge_plan_conflict status=%s → advisory",
                    getattr(job, "status", None))
        return candidates
    apply_verdicts(candidates, parse_judge_verdicts(extract_judge_text(job.result)))
    return candidates


async def check_canon(
    draft: str, snapshot: dict[str, Any] | None, *,
    judge=None, user_id: str = "", model_source: str = "", model_ref: str = "",
    source_language: str = "auto", trace_id: str | None = None,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> list[CanonViolation]:
    """Full canon check on a draft: SCORE symbolic pre-filter → (if any
    candidates AND a distinct judge is configured) LLM-judge confirmation.
    Returns ALL candidates with `confirmed` set (True/False by the judge, or
    None when no judge ran). The caller treats `confirmed is True` as HARD."""
    candidates = gone_cast_in_draft(draft, snapshot)
    if not candidates or judge is None or not model_ref:
        return candidates
    return await judge_canon(
        judge, user_id=user_id, model_source=model_source, model_ref=model_ref,
        draft=draft, candidates=candidates, source_language=source_language,
        trace_id=trace_id, cancel_check=cancel_check,
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
