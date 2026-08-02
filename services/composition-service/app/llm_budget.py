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

__all__ = ["CallProfile", "unusable", "PROFILES", "budget_for", "profile_for"]


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
    #: ESCALATE the truncation cost above what the KIND implies. Only escalates —
    #: `False` here can never turn off a STRUCTURED row's fatality.
    #:
    #: For a row whose output is a LIST that truncation destroys, while its SIZING is
    #: verdict-shaped. `cross_scene_check` is the case that proved the two are separate
    #: questions: forcing it to STRUCTURED for the fatality would drag in that kind's
    #: 4096 floor for a call MEASURED at 499 output tokens.
    truncation_fatal: bool = False
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
    # MISLABELLED until 2026-08-03, and the label was the smaller half of the problem.
    # Its two call sites (`compress._cast_state`, `cross_scene_check._extract_one`) emit a
    # cast ROSTER — one row per person, capped at 40 by `extract_people` — not a
    # contradiction list. Measured live on a 14-person passage: 499 output tokens, 14
    # rows, **35.6 tokens/row**, so the 40-row worst case needs ~1424 and 2048 holds.
    #
    # The budget was never the bug. The KIND was: VERDICT means truncation is mild, and
    # for a roster it is total. At a 120-token cap the same call returned
    # `finish_reason=length` and `extract_people` parsed **0 rows** — an EMPTY roster,
    # which is not the `None` both callers degrade on. `compare_people` turns an empty
    # roster into `status="checked"`, zero contradictions: a CLEAN verdict on a scene
    # whose cast it never read.
    "cross_scene_check": CallProfile(
        OutputKind.VERDICT, 2048, 2048, truncation_fatal=True,
        why="a cast ROSTER for one passage — one row per person, capped at 40. Sizes like a verdict (short, bounded) and truncates like a list (unparseable), which is why the fatality is declared rather than inherited from the kind"),
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
    # A free-text deconstruction of ONE source chunk. PROSE: it stops mid-sentence rather
    # than becoming unparseable, and its length tracks the chunk it is reading.
    "motif_deconstruct": CallProfile(OutputKind.PROSE, 2048, 2048,
                                     why="one chunk deconstructed into motif prose"),
    # A json_schema-constrained abstraction object — STRUCTURED by the response_format the
    # call site already sends, not by a guess about its shape.
    "motif_abstraction": CallProfile(OutputKind.STRUCTURED, 4096, 1024,
                                     why="one abstracted motif spec per mined pattern"),
    "motif_mine_judge": CallProfile(OutputKind.VERDICT, 1536, 256,
                                    why="a binary keep/drop score for one candidate"),

    # ── glossary-build (app/services/glossary_build) ──────────────────────────────────────
    # Every one of these was a POSITIONAL literal, invisible to both detectors.
    "glossary_build_plan": CallProfile(OutputKind.STRUCTURED, 4096, 1600,
                                       why="the planner's list of entities to build"),
    "glossary_build_entity": CallProfile(OutputKind.STRUCTURED, 4096, 2200,
                                         why="one entity's full attribute object"),
    "glossary_build_batch": CallProfile(OutputKind.STRUCTURED, 4096, 2600,
                                        why="a batch of entity objects of one kind"),
    "glossary_build_outline": CallProfile(OutputKind.STRUCTURED, 4096, 900,
                                          why="the section outline for a profile write-up"),
    # PROSE: one section of an entity profile, written free-text and appended to a
    # conversation. It stops mid-sentence rather than becoming unparseable.
    "glossary_build_section": CallProfile(OutputKind.PROSE, 1024, 800,
                                          why="one written section of an entity profile"),
    "glossary_build_distill": CallProfile(OutputKind.STRUCTURED, 4096, 2200,
                                          why="the profile distilled back into an object"),

    # ── intent-FSM (app/services/intent_fsm) ──────────────────────────────────────────────
    # One row, three call sites (ask / retry / repair) — they are the same call and the same
    # 700, so giving them three codes would invent a distinction the code does not make.
    "intent_fsm_ask": CallProfile(OutputKind.STRUCTURED, 4096, 700,
                                  why="one slot's candidate set, grammar-constrained"),

    # ── self-heal's two entry budgets ─────────────────────────────────────────────────────
    # `run_self_heal(judge_max_tokens=2200, edit_max_tokens=1200)` were SIGNATURE DEFAULTS
    # that no detector could see: the gate matched the parameter name EXACTLY, and naming a
    # parameter after which call it sizes — the natural thing when one function drives two —
    # put both outside the check. `sigs` read 0 repo-wide while these sat in the open.
    "self_heal_judge": CallProfile(OutputKind.STRUCTURED, 4096, 2200,
                                   why="the judge's findings list over one chapter"),
    "self_heal_edit": CallProfile(OutputKind.EDIT, 2200, 1200,
                                  why="one satellite edit to one flagged span"),
    # The chapter stitch: scene drafts merged into one continuous chapter. PROSE, and the
    # router still sizes it proportionally to the draft count — this row is the floor under
    # that, and the budget a caller that supplies nothing now gets.
    "stitch_chapter": CallProfile(OutputKind.PROSE, 2048, 2048,
                                  why="the scene drafts merged into one chapter"),
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
        context_length=context_length, floor=p.floor,
        truncation_is_fatal=p.truncation_fatal, **kw,
    )


def narrowed_by_request(computed: int, requested: int | None) -> int:
    """`computed`, narrowed by a caller-supplied `requested` — never raised by it.

    The one place a REQUEST FIELD is allowed to touch an output budget, and the reason it is
    a function rather than an idiom is that the idiom was `body.max_output_tokens or
    <computed>`, repeated at four call sites, where the request won OUTRIGHT. It beat the
    service's own sizing, and — the part that matters — it beat the DEPLOY CEILING
    (`chapter_gen_max_tokens`, `stitch_max_tokens`). Nothing bad happened yet only because
    `SCENE_OUTPUT_CEILING` and both of those settings are all 32768 today; lower either
    setting for a small-context deployment and a request could walk straight past it.

    A deploy ceiling a request can exceed is not a ceiling. Per the settings standard the
    effective value is `AND(deploy_allows, user_asks)` — the user narrows WITHIN the ceiling,
    never through it. A request asking for MORE than the service computed is honoured as
    "no narrowing", not as an override: the model stops when the passage is done, so a bigger
    cap would not have produced more text anyway — it would only have removed the guard.
    """
    if not requested or requested <= 0:
        return computed
    return min(computed, requested)


def max_tokens_for(code: str, **kw) -> int:
    """The `max_tokens` value for the wire. Convenience over `budget_for(...)` for the many
    call sites that only need the integer."""
    return budget_for(code, **kw).max_output_tokens


def unusable(job, code: str) -> str | None:
    """Why this job's output must not be used — or ``None`` when it is fine.

    Folds TWO questions, and every call site here already asked one of them. ``status !=
    "completed"`` was checked everywhere; ``finish_reason == "length"`` was checked almost
    nowhere — measured 2026-08-03, **2 of 28** STRUCTURED call sites, while the spec's S7
    asked for exactly this ("and on a missing ``finish_reason == 'length'`` check").

    They are the same question. The SDK already decides which kinds care —
    ``truncation_is_fatal = (kind is OutputKind.STRUCTURED)`` — because a JSON or
    grammar-constrained response **cannot stop early in a valid place**: a clipped array is
    either unparseable or, worse, parseable with items silently missing. For those kinds a
    truncated job is exactly as unusable as one that never completed, so it takes the branch
    the site already wrote and needs no new judgement.

    NOT fatal for PROSE / EDIT / VERDICT / MIRROR, and that is deliberate rather than lenient.
    A clipped paragraph is short, not wrong. A clipped verdict fails to parse into a verdict
    the caller already treats as absent, and `judge_plan_conflicts` reports that absence
    through its `judged` flag — the fix for the incident that motivated all of this. Making
    those fatal would convert working degradations into outages.

    Returns a SHORT reason (``"status=failed"`` / ``"truncated"``) rather than a bool, because
    several call sites fold it into a log line or an error code — a sentence there would turn an
    error code into a paragraph. The long explanation belongs here, not in every caller.
    """
    status = getattr(job, "status", None)
    if status != "completed":
        # The bare status, not `f"status={status}"`. Two call sites fold this straight into an
        # error CODE (`error=f"audit_{why}"`), and a test pinned `audit_failed` — so the
        # prefixed form silently renamed a code that something downstream may key on. The new
        # state simply joins the same vocabulary as `audit_truncated`.
        return str(status or "unknown")
    # The RESOLVED budget, not the kind. The kind is only the default: a row may ESCALATE
    # (`truncation_fatal=True`) when its output is a LIST that truncation destroys while its
    # sizing is verdict-shaped. Asking the kind here left `cross_scene_check` uncovered after
    # its row had already declared the fatality — one rule, two places, and they disagreed
    # within an hour. `budget_for` is pure arithmetic, so resolving it here is free.
    if getattr(job, "finish_reason", None) == "length" and budget_for(code).truncation_is_fatal:
        return "truncated"
    return None
