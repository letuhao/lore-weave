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
    #: The literal this row replaced. Load-bearing: the registry test asserts
    #: `budget_for(code) >= was` for every row, which is what makes "adoption is never a
    #: downgrade" a machine check instead of a sentence.
    was: int
    why: str = ""


#: code → profile. A code is the FUNCTION the call lives in, so a reader can go straight
#: from a budget question to the call it governs.
PROFILES: dict[str, CallProfile] = {
    # ── judges/critics: a bounded verdict + a short reason. Clipping costs a reason string.
    "judge_canon": CallProfile(OutputKind.VERDICT, 1536, 1024,
                               "per-candidate verdicts + a one-line why"),
    "judge_prose": CallProfile(OutputKind.VERDICT, 1536, 1536, "the critic's scored findings"),
    "pairwise_judge": CallProfile(OutputKind.VERDICT, 1536, 1024, "A/B verdict + rationale"),
    "judge_motif_conformance": CallProfile(OutputKind.VERDICT, 1536, 512,
                                           "did the draft realize its motif"),
    "select_score": CallProfile(OutputKind.VERDICT, 1536, 512, "retrieval scoring"),
    "self_heal_verify": CallProfile(OutputKind.VERDICT, 1536, 320,
                                    "did the proposed edit actually fix the finding"),

    # ── structured plans: a clipped array is UNPARSEABLE, not short. Headroom is deliberate.
    "propose_cast": CallProfile(OutputKind.STRUCTURED, 4096, 4000,
                                "the full cast JSON — the site where truncation already bit"),
    "propose_world": CallProfile(OutputKind.STRUCTURED, 4096, 4000, "world/setting JSON"),
    "plan_character_arcs": CallProfile(OutputKind.STRUCTURED, 4096, 2000, "per-character arcs"),
    "select_arc_motifs": CallProfile(OutputKind.STRUCTURED, 4096, 1200,
                                     "chosen motif codes + rationale"),
    "detect_and_update_threads": CallProfile(OutputKind.STRUCTURED, 4096, 1024,
                                             "narrative threads opened/advanced/closed"),
    "audit_promises": CallProfile(OutputKind.STRUCTURED, 4096, 1500, "promise audit rows"),
    "extract_tracked_promises": CallProfile(OutputKind.STRUCTURED, 4096, 800,
                                            "promises stated in the prose"),
    "score_promise_coverage": CallProfile(OutputKind.STRUCTURED, 4096, 1500,
                                          "per-promise coverage scores"),
    # 8000, not the kind's 4096: plan-forge emits a WHOLE planning package in one response.
    # This is the row that proves the `floor` override was necessary — the straight adoption
    # would have halved it, and a halved plan JSON does not come back short, it comes back
    # unparseable.
    "plan_forge_chat": CallProfile(OutputKind.STRUCTURED, 8000, 8000,
                                   "a whole planning package in one response"),

    # ── edits: proportional to the span being rewritten; the edit is lost on truncation.
    "propose_edits_direct": CallProfile(OutputKind.EDIT, 3000, 3000, "direct span edits"),
    "propose_self_heal": CallProfile(OutputKind.EDIT, 3000, 3000, "self-heal edit proposals"),

    # ── prose-shaped: compression output. Stops mid-sentence; recoverable.
    "compress": CallProfile(OutputKind.PROSE, 1024, 512, "compressed running context"),
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
    return call_budget(
        p.kind, target=target, language=language, reasoning=reasoning,
        context_length=context_length, floor=p.floor,
    )


def max_tokens_for(code: str, **kw) -> int:
    """The `max_tokens` value for the wire. Convenience over `budget_for(...)` for the many
    call sites that only need the integer."""
    return budget_for(code, **kw).max_output_tokens
