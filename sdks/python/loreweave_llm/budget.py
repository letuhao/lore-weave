"""The call-budget seam — one place that decides how much an LLM call may think and produce.

## What this is (and what it is not)

It is **not** "the effort enum" and **not** "max_tokens". It is the function that produces
BOTH, because they are not independent: reasoning tokens are spent BEFORE the visible
output and drawn from the SAME allowance. Setting one without the other is how this repo
once shipped a reasoning model that spent its whole budget on hidden thinking and returned
``text=""``, billed as a success.

``composition.engine.cowrite.scene_output_budget`` already proved the shape for ONE kind of
call (prose): it takes the resolved ``ReasoningDirective`` as an *input* to computing
``max_tokens``. This generalises that to every kind of call, in every service.

## Why the enum is OUTPUT KIND, not effort

What actually differs between call sites is the **sizing model** and **what truncation
costs** — not how hard the model should think:

===============  ====================================  =======================================
kind             sizing model                          truncation
===============  ====================================  =======================================
``PROSE``        words x language density              stops mid-sentence; paid for, recoverable
``STRUCTURED``   expected items x per-item size        **unparseable** — a grammar cannot stop
                                                       early in a valid place, so a clipped
                                                       JSON object is unrecoverable, not short
``VERDICT``      a bounded short answer                mild — a clipped reason string
``EDIT``         proportional to the input span        the edit is lost
===============  ====================================  =======================================

``composition.engine.cast_plan`` records the STRUCTURED case biting for real:
*"a full cast JSON is verbose — undersizing truncates the array -> parse fails"*. That is a
different failure from a short scene, and a single flat number cannot express both.

## The one rule that decides whether this seam is worth anything

**A seam that carries no signal is a renamed constant.**

If a call site calls ``call_budget(OutputKind.VERDICT)`` with no arguments, a future
adaptive policy has nothing to adapt on and this file is ceremony. The VALUE is in the
parameters: how much output is expected, in what language, against what context window,
with which reasoning directive. Those are facts the call sites already hold and currently
throw away into a literal.

So: pass what you know. An unknown ``target`` is fine and falls back to the kind's default —
but passing it is what makes the future version able to do better than today's.

## Half of this already exists — for the OTHER axis

The effort axis is **already adaptive**. The chat GUI's ``auto`` reasoning mode is
``UserReasoningPref = "auto"`` → ``resolve_reasoning(auto_effort=score_effort(signals))``,
and ``score_effort`` (``composition.app.reasoning.policy``) scores real per-call signals —
operation, canon-rule count, present-entity count, reveal gate, tension — into a level.

The budget axis has no equivalent: ~40 flat literals. **The two draw from the same token
allowance**, so having one that adapts and one that is a constant is the actual defect,
not an omission.

So this module is deliberately **mechanism, not policy** — the same split that already
exists for reasoning, where the SDK holds ``resolve_reasoning`` and the service holds
``score_effort``. A future scored budget belongs next to ``score_effort``, consuming the
SAME ``ReasoningSignals``, and feeding its result in here. That is why the parameters below
mirror facts a call site already computes rather than inventing a new vocabulary.

## Naming — ``adaptive`` is taken, and means something else

``ReasoningControl = "adaptive"`` already means *the MODEL self-orchestrates* (Anthropic,
Gemini 2.5+) — send nothing, do not run a classifier. It is NOT "we chose cleverly".
A scored budget policy therefore reports ``source="scored:<name>"``; reusing ``adaptive``
would be one name for two concepts, which is the drift this repo's contract rules exist to
prevent.

## Today's behaviour

Returns the DEFAULT policy. Adopting it must never truncate something that previously fit —
but that is a property of each SERVICE's registry rows, not something this module can promise
on its own: the kind floors below are a safety net sized from a sample, and the full inventory
contained three call sites above their kind's floor. So the guarantee is enforced where it can
be checked — a registry row declares the measured minimum via ``floor``, and the service's own
test asserts no row resolves below the literal it replaced. ``CallBudget.source`` says
``"default"``. When a scored policy lands, every call site that
already passes its signals benefits without an edit — which is the entire point of
introducing the seam before the policy.

Mirrors ``ReasoningDirective``'s convention (a resolved value + a ``source`` string that
explains it) so a budget is as inspectable as a reasoning decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from loreweave_llm.reasoning import ReasoningDirective

__all__ = [
    "OutputKind",
    "CallBudget",
    "call_budget",
    "DEFAULT_CEILING",
    "TOKENS_PER_WORD",
]


class OutputKind(str, Enum):
    """What the call produces. Determines the sizing model AND the cost of truncation."""

    PROSE = "prose"
    STRUCTURED = "structured"
    VERDICT = "verdict"
    EDIT = "edit"
    #: The output's length is dictated by the INPUT and the model's natural stop is the
    #: correct bound — translation, transcription, OCR. Resolves to ``0``, which is this
    #: platform's existing wire convention for "omit the cap, let the model decide"
    #: (``provider/adapters.go``: *"Policy: max_tokens=0 means omit"*; Anthropic, which
    #: rejects a missing cap with a 400, substitutes 8192).
    #:
    #: This kind exists because translation-service's four LLM call sites send
    #: ``input={"messages": …}`` with no cap at all, and that is DELIBERATE — a translation
    #: is a fidelity contract, so a cap that clips a chapter mid-sentence is worse than no
    #: cap. The problem was never the behaviour; it was that "deliberately unbounded" and
    #: "someone forgot" looked identical at the call site. Same shape as a skipped test
    #: reading as a passing one. Declaring it makes the decision greppable and lets the
    #: gate tell the two apart.
    MIRROR = "mirror"


#: Hard runaway guard, not a budget. Sized so no legitimate call can reach it, so hitting
#: it is a bug report rather than a quiet truncation.
DEFAULT_CEILING = 32768

#: Output tokens per word, by language. Vietnamese/Thai and CJK tokenize far denser than
#: English, so a word target means very different token counts across books. Lifted from
#: the measured composition values rather than re-derived.
TOKENS_PER_WORD: dict[str, float] = {
    "vi": 2.6, "th": 2.6, "zh": 3.2, "ja": 3.2, "ko": 3.0,
}
_TOKENS_PER_WORD_DEFAULT = 1.7

#: Headroom over the computed need. Deliberately loose for creative output: `max_tokens`
#: cannot make prose shorter, only make it STOP — mid-sentence, tokens already paid for.
#: Length is governed by the prompt's own directive, which the model can weigh against the
#: passage it is actually writing. The ceiling's only job is to be too big to matter.
_HEADROOM: dict[OutputKind, float] = {
    OutputKind.PROSE: 2.0,
    # STRUCTURED gets MORE headroom, not less: a clipped array is unparseable, so the
    # asymmetry between "spent too much" and "lost the whole response" is severe.
    OutputKind.STRUCTURED: 2.5,
    OutputKind.VERDICT: 1.5,
    OutputKind.EDIT: 2.0,
    OutputKind.MIRROR: 1.0,   # unused — MIRROR returns before the sizing model runs
}

#: Reasoning tokens come out of the same allowance, so scale by effort rather than adding a
#: flat number — that is how the cost actually grows.
_REASONING_ALLOWANCE: dict[str, float] = {
    "none": 0.0, "off": 0.0, "low": 0.6, "medium": 1.2, "high": 2.0,
}
_REASONING_ALLOWANCE_UNKNOWN = 1.2

#: Floors per kind — a SAFETY NET, not a per-call size.
#:
#: These were originally described as ">= the flat literal each kind's call sites use today,
#: so adopting the seam is never a downgrade". That was measured against the handful of sites
#: this module was written from, and the full inventory falsified it: `plan_forge/llm.chat`
#: uses 8000 (STRUCTURED floor 4096 — it would have been HALVED) and
#: `self_heal.propose_edits_direct`/`propose_self_heal` use 3000 (EDIT floor 2200). Three
#: silent downgrades, in a seam whose docstring promised there could be none.
#:
#: Raising the floors to cover the maximum would over-budget every small call instead, so the
#: floor stays a net and the per-call minimum belongs where the per-call knowledge is: the
#: service's own call-profile registry, via the `floor` argument below. `PASS_REGISTRY` is the
#: precedent — mechanism in the SDK, per-operation facts in the service.
_FLOOR: dict[OutputKind, int] = {
    OutputKind.PROSE: 1024,
    OutputKind.STRUCTURED: 4096,   # >= cast_plan's 4000, the site truncation already bit
    OutputKind.VERDICT: 1536,      # >= critic's 1536
    OutputKind.EDIT: 2200,         # >= self_heal's 2200
    OutputKind.MIRROR: 0,          # 0 == "omit the cap" on the wire; see OutputKind.MIRROR
}

#: Default per-item cost for a STRUCTURED call when the caller knows the item count. A
#: glossary/cast/beat row with a few short string fields lands around here.
_TOKENS_PER_ITEM = 220

#: Fraction of the model's context window an output may claim. Both this and the ceiling
#: apply; the tighter wins. Two SDK sites clamp against the window today and two do not,
#: which is why one worker's distiller is unclamped while its extractor is not.
_MAX_WINDOW_SHARE = 0.5


@dataclass(frozen=True)
class CallBudget:
    """A resolved budget for ONE LLM call, plus why it looks like this."""

    max_output_tokens: int
    reasoning: ReasoningDirective | None
    #: Whether a `finish_reason == "length"` on this call destroys the result rather than
    #: shortening it. STRUCTURED output cannot stop early in a valid place, so a clipped
    #: response is unrecoverable — callers should treat it as an error, not a short answer.
    truncation_is_fatal: bool
    #: "default" today; a scored policy will say "scored:<name>". NOT "adaptive" — that
    #: word already means "the model self-orchestrates" (ReasoningControl). Never blank:
    #: a budget whose origin is unknown is the thing this seam exists to remove.
    source: str
    #: The window share the output may claim, if the caller supplied a context length.
    #: None means the caller did not say, so no window clamp could be applied — visible
    #: rather than silently unclamped.
    clamped_to_window: int | None = None


def _reasoning_multiplier(reasoning: ReasoningDirective | None) -> float:
    effort = (getattr(reasoning, "effort", None) or "none")
    effort = str(getattr(effort, "value", effort)).lower()
    return _REASONING_ALLOWANCE.get(effort, _REASONING_ALLOWANCE_UNKNOWN)


def call_budget(
    kind: OutputKind,
    *,
    target: int | None = None,
    language: str | None = None,
    reasoning: ReasoningDirective | None = None,
    context_length: int | None = None,
    floor: int | None = None,
    ceiling: int = DEFAULT_CEILING,
) -> CallBudget:
    """Resolve the output budget for one LLM call.

    :param kind: what the call produces — picks the sizing model and the truncation cost.
    :param target: the size signal, interpreted per kind:
        ``PROSE`` target words · ``STRUCTURED`` expected item count ·
        ``EDIT`` input characters · ``VERDICT`` unused.
        ``None`` falls back to the kind's floor — allowed, but it is exactly the
        information a future adaptive policy needs, so pass it when you have it.
    :param language: the OUTPUT language (``"vi"``, ``"zh"``, …). A word target means a very
        different token count per language; omitting it under-budgets non-Latin output.
    :param reasoning: the already-resolved directive. Deliberately not a bare effort
        string — threading a loose effort through call sites is how sixteen drifting
        copies of the reasoning decision came about, and the caller already holds it.
    :param context_length: the model's window, for clamping. Omitted means no window clamp
        is applied and ``clamped_to_window`` stays ``None`` so the gap is visible.
    :param floor: a per-call minimum the SERVICE has measured, overriding the kind's floor
        when it is larger. This is how a call that genuinely needs more than its kind's net
        (``plan_forge``'s 8000-token plan JSON) keeps it without inflating every sibling —
        and it is what makes "adopting this is never a downgrade" enforceable instead of
        merely stated. Belongs in the service's call-profile registry, never at a call site.
    :param ceiling: hard runaway guard.
    """
    # MIRROR short-circuits the whole sizing model: there is no target to size FROM, and
    # every clamp below (floor, headroom, window share, ceiling) would turn a deliberate
    # "no cap" into a cap. Returns 0 = the wire's omit sentinel, and never fatal — a model
    # stopping naturally is the intended end of the call, not a truncation.
    #
    # `floor` is deliberately ignored here rather than raising: 0 means UNBOUNDED, which
    # already satisfies any minimum. The numeric 0 < floor comparison is the trap, so the
    # rule is stated instead of left to be inferred, and pinned by a test.
    if kind is OutputKind.MIRROR:
        return CallBudget(
            max_output_tokens=0,
            reasoning=reasoning,
            truncation_is_fatal=False,
            source="default",
            clamped_to_window=None,
        )

    lang = (language or "auto").lower()
    per_word = TOKENS_PER_WORD.get(lang, _TOKENS_PER_WORD_DEFAULT)

    if kind is OutputKind.PROSE:
        base = (target or 0) * per_word
    elif kind is OutputKind.STRUCTURED:
        base = (target or 0) * _TOKENS_PER_ITEM
    elif kind is OutputKind.EDIT:
        # `target` is input characters; the edit is roughly the same size back out.
        base = (target or 0) / 3.0
    else:  # VERDICT — bounded by construction, the floor IS the model
        base = 0.0

    need = base * _HEADROOM[kind]
    need += need * _reasoning_multiplier(reasoning)
    # The service's measured minimum wins over the kind's net when it is larger; the net still
    # applies when the service has none. `max` of both, never a replacement — a registry row
    # must not be able to lower a kind's safety floor.
    resolved = max(_FLOOR[kind], floor or 0, int(need))

    window_cap: int | None = None
    if context_length and context_length > 0:
        window_cap = max(1, int(context_length * _MAX_WINDOW_SHARE))
        resolved = min(resolved, window_cap)

    resolved = max(1, min(ceiling, resolved))
    return CallBudget(
        max_output_tokens=resolved,
        reasoning=reasoning,
        truncation_is_fatal=(kind is OutputKind.STRUCTURED),
        source="default",
        clamped_to_window=window_cap,
    )
