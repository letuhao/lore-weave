"""translation-service's call-profile registry — one row per kind of LLM call it makes.

The per-operation knowledge belongs to the SERVICE (`_OPERATION_INSTRUCTIONS`, `PASS_REGISTRY`
are the precedent); the SDK owns only the mechanism (`loreweave_llm.budget.call_budget`). This
module is the seam between them for this service: every LLM call site here resolves its output
budget from a row below, never from a literal at the call site.

Why every row is MIRROR
-----------------------
Translation output length is dictated by the SOURCE text, not chosen. The chapter is already
chunked upstream (`split_chapter`), and a translation is a fidelity contract — clipping one
mid-sentence is worse than any overspend a cap would prevent. So the model's natural stop is
the correct bound, and `OutputKind.MIRROR` resolves to `0`, this platform's existing wire
sentinel for *omit the cap* (`provider/adapters.go`; the SDK drops a 0 in `models.py:179`, and
Anthropic — which 400s on a missing cap — substitutes 8192).

That was ALREADY the behaviour: all four sites sent `input={"messages": …}` with no cap. What
was missing is that nothing distinguished "we decided the model should run to its natural
stop" from "nobody set a budget here". Those look identical at a call site and read identically
in review — the same shape as a skipped test reading as a passing one. Declaring it changes
nothing on the wire and makes the decision greppable, reviewable, and gate-checkable.

If a row ever needs a real cap, change it HERE — not at a call site.
"""
from __future__ import annotations

from loreweave_llm.budget import CallBudget, OutputKind, call_budget

__all__ = ["TranslationCall", "budget_for", "PROFILES"]

#: The kinds of LLM call this service makes.
TranslationCall = str

#: code → the resolved budget. Evaluated once at import; `call_budget` is pure.
PROFILES: dict[TranslationCall, CallBudget] = {
    # A chapter chunk translated in a stateless request.
    "translate_chunk": call_budget(OutputKind.MIRROR),
    # The session-translator's stateful per-chunk call (carries history + memo).
    "translate_session_chunk": call_budget(OutputKind.MIRROR),
    # The decoupled worker's compaction step: it rewrites the running memo, so its length
    # tracks the memo it is compacting rather than a figure we pick.
    "compact_memo": call_budget(OutputKind.MIRROR),
}


def budget_for(call: TranslationCall) -> int:
    """The `max_tokens` value to put on the wire for `call`.

    Raises on an unknown code rather than defaulting: a silent fallback here would
    re-introduce exactly the unattributed budget this registry removes.
    """
    if call not in PROFILES:
        raise KeyError(
            f"unknown translation call profile {call!r} — add a row to PROFILES in "
            f"app/llm_budget.py rather than passing a literal at the call site"
        )
    return PROFILES[call].max_output_tokens
