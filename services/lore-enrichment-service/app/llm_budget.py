"""lore-enrichment-service's call-profile registry — one row per kind of LLM call it makes.

Same split as composition-service's registry and `PASS_REGISTRY` before it: the SDK
(`loreweave_llm.budget.call_budget`) owns the MECHANISM — what an output kind means, how a
target is sized, how reasoning eats the same allowance — and the per-operation facts live here,
next to the code that knows them.

Why this file exists at all
---------------------------
This service had two hand-rolled `POST /internal/llm/stream` bodies, and the budget gate did
not parse that shape. It said so in its PASS line rather than pretending otherwise, which was
honest — and still hid a live defect for as long as the surface stayed unscanned: the eval
judge in `app/eval/judge_binding.py` sent **no `max_tokens` key at all**. Uncapped, on a call
whose consumer parses strict JSON.

An excluded surface with an accurate label is still an excluded surface.

Two rows, and they are not the same shape
-----------------------------------------
`generate_gap_completion` is an ADOPTION: it had a real number (4000) and this row must never
resolve below it, which the registry test checks against `was`.

`eval_judge_usefulness` is a NARROWING: it had no cap, so there is no previous number for a
no-downgrade test to compare against and `was=None` says so. A row that recorded `was=0` would
satisfy `budget_for(code) >= was` for every conceivable value — a test that cannot fail,
dressed as coverage. The exemption instead carries `narrowing_why`, and the registry test
requires it to be non-empty, so the escape hatch has to state its own reason.
"""
from __future__ import annotations

from dataclasses import dataclass

from loreweave_llm.budget import CallBudget, OutputKind, call_budget

__all__ = ["CallProfile", "PROFILES", "budget_for", "max_tokens_for", "profile_for"]


@dataclass(frozen=True)
class CallProfile:
    kind: OutputKind
    #: The measured minimum for this call.
    floor: int
    #: The budget ACTUALLY IN USE before this row existed. `None` ⇒ the call was UNCAPPED, so
    #: this row narrows rather than adopts and the no-downgrade assertion does not apply.
    #: A `None` here obliges `narrowing_why`.
    was: int | None
    why: str = ""
    #: Required exactly when `was is None`: why capping a previously uncapped call is safe.
    narrowing_why: str = ""


#: code → profile. A code is the FUNCTION the call lives in.
PROFILES: dict[str, CallProfile] = {
    # ── the gap-completion prose seam (app/generation/complete.py).
    #
    # PROSE, so `language` is a signal the kind actually reads — the caller holds it on
    # `StrategyContext.profile.language`, and a CJK completion needs materially more tokens
    # for the same prose than a Latin-script one.
    "generate_gap_completion": CallProfile(
        OutputKind.PROSE, floor=4000, was=4000,
        why="one entity's enriched profile/bio prose; matches wiki's per-article budget"),

    # ── the C15 eval judge ensemble (app/eval/judge_binding.py).
    #
    # STRUCTURED and not VERDICT, which is the judgement in this row. The kind is decided by
    # what TRUNCATION COSTS, not by how the call is described, and `parse_judge_verdict`
    # accepts a JSON object or nothing: a clipped `{"verdict": "hi` is not a shorter answer,
    # it is no answer, and the proposal silently drops out of that judge's denominator. That
    # is STRUCTURED's definition — and it is why this row's adoption also puts a
    # finish_reason check at the call site, which the contract requires of a fatal kind.
    "eval_judge_usefulness": CallProfile(
        OutputKind.STRUCTURED, floor=4096, was=None,
        why="one `{verdict, ...}` object per proposal",
        narrowing_why=(
            "The call was UNCAPPED. The judge's whole output is a small JSON verdict object "
            "and STRUCTURED's 4096 floor is roughly two orders of magnitude more than one "
            "needs, so the cap cannot clip a well-formed answer; what it does bound is a "
            "judge that ignores the rubric and rambles — which today burns tokens and then "
            "fails to parse anyway. Uncapped was never the intent, only the default."),
    ),
}


def profile_for(code: str) -> CallProfile:
    try:
        return PROFILES[code]
    except KeyError:
        raise KeyError(
            f"no call profile for {code!r} — add a row to app/llm_budget.py rather than "
            f"passing a literal max_tokens"
        ) from None


def budget_for(code: str, *, target: int | None = None, language: str | None = None,
               reasoning=None, context_length: int | None = None) -> CallBudget:
    """Resolve `code`'s budget, threading whatever per-call signal the caller holds."""
    p = profile_for(code)
    return call_budget(
        p.kind, target=target, language=language, reasoning=reasoning,
        context_length=context_length, floor=p.floor,
    )


def max_tokens_for(code: str, **kw) -> int:
    """The `max_tokens` value for the wire."""
    return budget_for(code, **kw).max_output_tokens
