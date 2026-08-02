"""composition-service's call-profile registry — one row per kind of LLM call it makes.

The SDK (`loreweave_llm.budget.call_budget`) owns the MECHANISM: what an output kind means,
how a target is sized, how reasoning eats the same allowance. The per-operation facts belong
here, with the code that knows them — the same split `PASS_REGISTRY` and
`_OPERATION_INSTRUCTIONS` already use.

Why every row carries an explicit `floor`
-----------------------------------------
The 18 call sites this replaces spanned 320 → 8000 tokens. The SDK's per-kind floors are a
safety net sized from a sample, and a straight adoption would have SILENTLY DOWNGRADED three
of them — `plan_forge_chat` 8000 → 4096 (halved), `propose_edits_direct` and
`propose_self_heal` 3000 → 2200 — inside a seam whose own docstring promised adoption "can
never truncate something that previously fit". The floor here is the measured minimum for
THIS call, so the promise is enforceable rather than asserted: see
`tests/unit/test_llm_budget_registry.py`, which fails if any row resolves below the literal
it replaced.

`was` is not decoration. It is the number the row must never go under, and the test reads it.

Why the KIND matters more than the number
-----------------------------------------
`truncation_is_fatal` follows the kind, and it is the thing a caller should branch on. A
clipped VERDICT is a shorter reason string; a clipped STRUCTURED response is unparseable —
`cast_plan` records that biting for real ("a full cast JSON is verbose — undersizing
truncates the array -> parse fails"). One flat integer could not express that difference,
which is why the ~40 literals were a bug and not merely untidy.
"""
from __future__ import annotations

from dataclasses import dataclass

from loreweave_llm.budget import CallBudget, OutputKind, call_budget

__all__ = ["CallProfile", "PROFILES", "budget_for", "profile_for"]


@dataclass(frozen=True)
class CallProfile:
    kind: OutputKind
    #: The measured minimum for this call — never below `was`.
    floor: int
    #: The budget ACTUALLY IN USE before this row existed — which is not always the signature
    #: default. `plan_forge_chat`'s default was 8000, but all five of its live callers
    #: (`elaborate`, `propose_llm`, `propose_llm_async` ×2, `refine`) pass 12000 explicitly,
    #: so the default was dead code and 12000 is the real number. Recording 8000 would have
    #: made this field describe a budget the system does not use — and the no-downgrade test
    #: reads it, so it would have validated against fiction.
    #:
    #: Load-bearing: the registry test asserts `budget_for(code) >= was` for every row, which
    #: is what makes "adoption is never a downgrade" a machine check instead of a sentence.
    was: int
    #: An upper bound for calls where the ceiling IS the length control. Rare and deliberate:
    #: see `compress`. `None` ⇒ the SDK's runaway guard.
    ceiling: int | None = None
    why: str = ""
    #: True ⇒ NO per-call signal can change this row's resolved budget, by construction.
    #:
    #: This exists because the no-signal ratchet was counting two different things as one.
    #: `call_budget` reads `language` ONLY on the PROSE and VERDICT branches, and MIRROR
    #: short-circuits before any sizing runs at all — so a call site can pass `language=` to a
    #: STRUCTURED row, satisfy a gate that greps kwargs, and change nothing. That is the
    #: "renamed constant" this seam's own docstring warns about, one level up: theatre that
    #: reads as progress.
    #:
    #: So the rule is: pass a kwarg only if the kind READS it, and a row where nothing can be
    #: read says so HERE rather than accumulating fake signal at its call sites. Same move as
    #: `OutputKind.MIRROR` itself — declaring the decision so silence and intent stop looking
    #: alike. `test_llm_budget_registry` PROBES every row against the mechanism and fails if
    #: this flag disagrees with it, in either direction, so it cannot drift into a comment.
    signal_inert: bool = False


#: code → profile. A code is the FUNCTION the call lives in, so a reader can go straight
#: from a budget question to the call it governs.
PROFILES: dict[str, CallProfile] = {
    # ── judges/critics: a bounded verdict + a short reason. Clipping costs a reason string.
    "judge_canon": CallProfile(OutputKind.VERDICT, 1536, 1024,
                               why="per-candidate verdicts + a one-line why"),
    # Its own key, not a reuse of judge_canon: this judge answers a DIFFERENT question (is the
    # death real and permanent, vs a feint/dream/prophecy) over a candidate set bounded by the
    # scene's cast, which is smaller than the gone-set judge_canon can face.
    "judge_plan_conflict": CallProfile(OutputKind.VERDICT, 1024, 768,
                                       why="one verdict + a short why per cast member"),
    "judge_prose": CallProfile(OutputKind.VERDICT, 1536, 1536, why="the critic's scored findings"),
    "pairwise_judge": CallProfile(OutputKind.VERDICT, 1536, 1024, why="A/B verdict + rationale"),
    "cross_scene_check": CallProfile(
        OutputKind.VERDICT, 2048, 2048,
        why="a contradiction list across one scene seam — usually EMPTY, but each entry quotes both sides, so a chapter that really did drift needs room to say so"),
    "judge_motif_conformance": CallProfile(OutputKind.VERDICT, 1536, 512,
                                           why="did the draft realize its motif"),
    "select_score": CallProfile(OutputKind.VERDICT, 1536, 512, why="retrieval scoring"),
    "self_heal_verify": CallProfile(OutputKind.VERDICT, 1536, 320,
                                    why="did the proposed edit actually fix the finding"),
    # A `{recommended, reasoning}` object read by REGEX, not json.loads — a clipped reason
    # string still yields a usable answer, so VERDICT and not STRUCTURED. Its 400 was the
    # last flat literal left in self_heal, hiding behind a helper whose other callers were
    # already on the registry.
    "self_heal_rerank": CallProfile(OutputKind.VERDICT, 1536, 400,
                                    why="is this edit a rule fix (auto-tickable) or craft"),
    # Replaces a HAND-ROLLED sizer, `_max_tokens_for(n) = 128 + 24n`, which is the exact thing
    # this seam exists to absorb: a second sizing model, in a module, with no floor and no
    # window clamp. `was=152` is that formula at n=1 — the smallest budget it ever produced,
    # so the no-downgrade assertion is true for every batch it ever ran. The VERDICT floor
    # (1536) exceeds the old formula for any batch under 58 edges, and a scene's succession
    # candidates are bounded by its cast.
    "succession_entailment": CallProfile(OutputKind.VERDICT, 1536, 152,
                                         why="one entailed/not verdict per candidate edge"),
    # The outline judge's findings list. STRUCTURED: `parse_plan_findings` reads a JSON array
    # and a clipped array is unparseable, not short.
    "plan_judge": CallProfile(OutputKind.STRUCTURED, 4096, 2000,
                              why="per-scene plan findings (chapter/scene/type/issue/fix)"),

    # ── structured plans: a clipped array is UNPARSEABLE, not short. Headroom is deliberate.
    "propose_cast": CallProfile(OutputKind.STRUCTURED, 4096, 4000,
                                why="the full cast JSON — the site where truncation already bit"),
    "propose_world": CallProfile(OutputKind.STRUCTURED, 4096, 4000, why="world/setting JSON"),
    "plan_character_arcs": CallProfile(OutputKind.STRUCTURED, 4096, 2000, why="per-character arcs"),
    "select_arc_motifs": CallProfile(OutputKind.STRUCTURED, 4096, 1200,
                                     why="chosen motif codes + rationale"),
    "detect_and_update_threads": CallProfile(OutputKind.STRUCTURED, 4096, 1024,
                                             why="narrative threads opened/advanced/closed"),
    "audit_promises": CallProfile(OutputKind.STRUCTURED, 4096, 1500, why="promise audit rows"),
    # L1 of the planning pipeline: one beat-role row per chapter. The count is known BEFORE
    # the call (it is `len(chapters)`), which is what makes this a real `target` rather than
    # an invented one — contrast `audit_promises`, whose length IS the output.
    "chapter_beat_map": CallProfile(OutputKind.STRUCTURED, 4096, 2048,
                                    why="one beat-role mapping per chapter"),
    # plan-forge material search: at most `max_candidates` VERBATIM lines copied out of the
    # author's document, so the caller's own bound is the target.
    "material_search": CallProfile(OutputKind.STRUCTURED, 4096, 1500,
                                   why="up to max_candidates verbatim document lines"),
    "extract_tracked_promises": CallProfile(OutputKind.STRUCTURED, 4096, 800,
                                            why="promises stated in the prose"),
    "score_promise_coverage": CallProfile(OutputKind.STRUCTURED, 4096, 1500,
                                          why="per-promise coverage scores"),
    # 12000, not the kind's 4096: plan-forge emits a WHOLE planning package in one response.
    # This is the row that proves the `floor` override was necessary — the straight adoption
    # would have cut it to 4096, and a clipped plan JSON does not come back short, it comes
    # back unparseable.
    #
    # 12000 and not the 8000 signature default, because the default was DEAD: every one of the
    # five live callers passed 12000 explicitly. A row saying 8000 would have described a
    # budget nothing uses, and the no-downgrade test would have proved it against fiction.
    "plan_forge_chat": CallProfile(OutputKind.STRUCTURED, 12000, 12000,
                                   why="a whole planning package in one response"),

    # ── edits: proportional to the span being rewritten; the edit is lost on truncation.
    "propose_edits_direct": CallProfile(OutputKind.EDIT, 3000, 3000, why="direct span edits"),
    "propose_self_heal": CallProfile(OutputKind.EDIT, 3000, 3000, why="self-heal edit proposals"),
    # One rewritten synopsis line, not a chapter — hence far below the sibling EDIT rows.
    "plan_heal_edit": CallProfile(OutputKind.EDIT, 2200, 700,
                                  why="one scene synopsis rewritten in place"),
    # One author-marked block rewritten. Its 1200 was a SIGNATURE DEFAULT, evaluated once at
    # import, so no caller could ever size it to the block actually being edited.
    "error_block_heal_edit": CallProfile(OutputKind.EDIT, 2200, 1200,
                                         why="one author-marked block, rewritten"),

    # ── prose-shaped: compression output. Stops mid-sentence; recoverable.
    #
    # `ceiling=512` is the point of this row, not an afterthought. `compress` produces a
    # summary the packer injects IN PLACE OF raw prose, specifically so a long chapter does
    # not blow the prompt budget — and its prompt carries NO length directive, so
    # `max_tokens` was the de-facto size control. Adopting the PROSE floor (1024) would have
    # let the summary grow to twice the size of the thing whose size it exists to reduce.
    #
    # That is the `scene_output_budget` lesson running backwards: there, the guidance asked
    # for 900 words while the wire allowed 1024 tokens, so capability lagged guidance. Here
    # there is no guidance at all, so raising capability silently raises the output. Guidance
    # and capability must move as ONE signal — and when only one of them exists, the budget
    # is not free to move.
    # NOT `signal_inert`, and the reason is worth keeping because the first version of this
    # row claimed it was. The argument looked airtight — `ceiling == floor == 512`, and the
    # ceiling is applied last, so nothing can move it. The registry PROBE disagreed: the
    # window clamp runs after the floor and pushes DOWN, so `context_length=8` resolves this
    # row to 4, not 512. A ceiling bounds one direction only.
    #
    # So `target` and `language` really are inert here (the ceiling eats them), and
    # `context_length` really is not. The call site does not know the model's window today, so
    # this row stays honest backlog rather than a declared exemption — the difference being
    # that backlog is something the ratchet still counts.
    "compress": CallProfile(OutputKind.PROSE, 512, 512, ceiling=512,
                            why="compressed running context — re-injected, so its SIZE is "
                                "the feature; the prompt states no length, so this bounds it"),
}


def profile_for(code: str) -> CallProfile:
    """The row for `code`. Raises on an unknown one rather than defaulting — a silent
    fallback would re-create the unattributed budget this registry exists to remove."""
    if code not in PROFILES:
        raise KeyError(
            f"unknown composition call profile {code!r} — add a row to PROFILES in "
            f"app/llm_budget.py rather than passing a literal at the call site"
        )
    return PROFILES[code]


def budget_for(code: str, *, target: int | None = None, language: str | None = None,
               reasoning=None, context_length: int | None = None) -> CallBudget:
    """Resolve `code`'s budget, threading whatever per-call signal the caller holds.

    `target`/`language`/`reasoning`/`context_length` are optional and default to the row's
    floor — but passing them is the entire point of the seam. A future scored policy adapts
    on exactly these; a call site that passes none gets a constant with extra steps.
    """
    p = profile_for(code)
    kw = {} if p.ceiling is None else {"ceiling": p.ceiling}
    return call_budget(
        p.kind, target=target, language=language, reasoning=reasoning,
        context_length=context_length, floor=p.floor, **kw,
    )


def max_tokens_for(code: str, **kw) -> int:
    """The `max_tokens` value for the wire. Convenience over `budget_for(...)` for the many
    call sites that only need the integer."""
    return budget_for(code, **kw).max_output_tokens
