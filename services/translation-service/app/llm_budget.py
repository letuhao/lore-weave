"""translation-service's call-profile registry — one row per kind of LLM call it makes.

The per-operation knowledge belongs to the SERVICE (`_OPERATION_INSTRUCTIONS`, `PASS_REGISTRY`
are the precedent); the SDK owns only the mechanism (`loreweave_llm.budget.call_budget`). This
module is the seam between them for this service: every LLM call site here resolves its output
budget from a row below, never from a literal at the call site.

Why the TRANSLATION rows are MIRROR (and the extraction row is not)
-------------------------------------------------------------------
Translation output length is dictated by the SOURCE text, not chosen. The chapter is already
chunked upstream (`split_chapter`), and a translation is a fidelity contract — clipping one
mid-sentence is worse than any overspend a cap would prevent. So the model's natural stop is
the correct bound, and `OutputKind.MIRROR` resolves to `0`, this platform's existing wire
sentinel for *omit the cap* (`provider/adapters.go`; the SDK drops a 0 in `models.py:179`).

**With one real exception, and it is not hypothetical: Anthropic rejects a missing cap with a
400, so the adapter substitutes 8192.** "The model's natural stop" is therefore a guarantee
this registry cannot make on that provider — a chunk needing more than 8192 output tokens
comes back clipped. Saying otherwise here would be a guarantee asserted in prose with nothing
in code behind it, which is the exact class this repo keeps finding. What IS in code:
`_parse_sdk_response` now logs `finish_reason == "length"`, so the loss is reported rather
than silent. Rejecting or re-chunking a truncated translation is a separate design decision.

That was ALREADY the behaviour: all four sites sent `input={"messages": …}` with no cap. What
was missing is that nothing distinguished "we decided the model should run to its natural
stop" from "nobody set a budget here". Those look identical at a call site and read identically
in review — the same shape as a skipped test reading as a passing one. Declaring it changes
nothing on the wire and makes the decision greppable, reviewable, and gate-checkable.

**The glossary SWEEP is the exception, and it is a different kind of call entirely.** It
emits a JSON list of entity mentions, so it is ``STRUCTURED``: a clipped response is not a
short one, it is an unparseable one, and the salvage path drops every mention after the cut.
``truncation_is_fatal`` is therefore ``True`` for that row, which is the fact a caller should
branch on — and the sweep call site now does (it refuses to CACHE a truncated response, the
same rule the batch path already applied, so a re-run can still recover the lost mentions).

If a row ever needs a real cap, change it HERE — not at a call site.
"""
from __future__ import annotations

from dataclasses import dataclass

from loreweave_llm.budget import CallBudget, OutputKind, call_budget

__all__ = ["TranslationCall", "CallProfile", "PROFILES",
           "profile_for", "budget_obj_for", "budget_for"]

#: The kinds of LLM call this service makes.
TranslationCall = str


@dataclass(frozen=True)
class CallProfile:
    """One row: the KIND of output, plus the measured bounds for THIS call.

    Mirrors composition-service's registry (`app/llm_budget.py` there) rather than inventing
    a second shape — `was` is the literal the row replaced and the test reads it, so
    "adopting the seam never truncates something that previously fit" is enforceable rather
    than asserted.
    """

    kind: OutputKind
    floor: int | None = None
    ceiling: int | None = None
    #: The flat literal this row replaced, or None if the call never had one.
    was: int | None = None


#: code → its profile. Resolution happens per call so a call site can thread the signals it
#: holds; the rows themselves stay declarative.
PROFILES: dict[TranslationCall, CallProfile] = {
    # A chapter chunk translated in a stateless request.
    "translate_chunk": CallProfile(OutputKind.MIRROR),
    # The session-translator's stateful per-chunk call (carries history + memo).
    "translate_session_chunk": CallProfile(OutputKind.MIRROR),
    # The decoupled worker's compaction step: it rewrites the running memo, so its length
    # tracks the memo it is compacting rather than a figure we pick.
    "compact_memo": CallProfile(OutputKind.MIRROR),
    # Stage 1 of the two-stage (EDC-cited) extraction shape: one call per window returning
    # `[{"name","evidence"}, …]`. STRUCTURED, not MIRROR — nothing about the source text sets
    # this length, and a clipped array is unparseable rather than short. The floor is the
    # `_EXTRACTION_OUTPUT_CEILING = 8000` literal it replaces, declared rather than left to
    # the kind's 4096 default, which would have HALVED it on adoption.
    "glossary_sweep": CallProfile(OutputKind.STRUCTURED, floor=8000, ceiling=8000, was=8000),
}


def profile_for(call: TranslationCall) -> CallProfile:
    """The row for `call`.

    Raises on an unknown code rather than defaulting: a silent fallback here would
    re-introduce exactly the unattributed budget this registry removes.
    """
    if call not in PROFILES:
        raise KeyError(
            f"unknown translation call profile {call!r} — add a row to PROFILES in "
            f"app/llm_budget.py rather than passing a literal at the call site"
        )
    return PROFILES[call]


def budget_obj_for(call: TranslationCall, *, target: int | None = None,
                   language: str | None = None, reasoning=None,
                   context_length: int | None = None,
                   ceiling: int | None = None) -> CallBudget:
    """Resolve `call`'s budget, threading whatever per-call signal the caller holds.

    A MIRROR row short-circuits every signal by design (`call_budget` returns the omit
    sentinel before any sizing runs) — passing them there is harmless and keeps one call
    shape across the registry.

    `ceiling` is a caller-measured HARDER bound, and it can only LOWER the row's: the
    extraction worker knows this chapter's real input size and therefore how much output the
    context still has room for, which the row cannot. Allowing it to raise the row's ceiling
    would let a call site quietly overrule the registry, which is the thing the registry
    exists to stop. `call_budget` applies the ceiling LAST, so it wins over the floor — a
    small-context model gets the smaller cap rather than the row's measured minimum.
    """
    p = profile_for(call)
    eff = ceiling if p.ceiling is None else min(p.ceiling, ceiling or p.ceiling)
    kw = {} if eff is None else {"ceiling": eff}
    return call_budget(p.kind, target=target, language=language, reasoning=reasoning,
                       context_length=context_length, floor=p.floor, **kw)


def budget_for(call: TranslationCall, **kw) -> int:
    """The `max_tokens` value to put on the wire for `call`."""
    return budget_obj_for(call, **kw).max_output_tokens
