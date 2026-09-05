"""CP-3 · **the executor** — where the plan stops informing and starts SUPPLYING.

Brick 4's sentence is *"the executor supplies the identifier the model already saw."* Until this
module existed, `resolve_arguments` had **zero production callers**: the plan reached the model as a
system message and the model **retyped** the identifier out of it. That is a better carrier than a
conversation which evicts the value entirely — measured 20/20 against 0/20 — but it is not the
claim. Retyping is exactly what fails: `entity_id:019fafa2-…` at step 12, `"0"` at step 16.

WHAT THIS DOES, IN ORDER
------------------------
1. **Before dispatch** — if the call names the current step's declaration, the arguments are
   *replaced* by `resolve_arguments`. Not merged, not defaulted: replaced.
2. **After dispatch** — the declared `emits` paths are read out of the real result and appended as a
   `step_emitted` event, so the next step's binding has something to resolve against.
3. **On failure** — a `step_failed` event carrying C-7's error class, because a failure nobody
   classified is one recovery cannot act on (§0.5).

🔴 **REPLACED, NOT MERGED.** A merge would let the model's retyped value win whenever the plan had
nothing to say, which is precisely the condition under which the carrier had already failed. The
plan either owns the parameter or it does not, and `check_bindings` decided that when the plan was
built.

🔴 **AND IT NEVER GUESSES WHICH STEP IS RUNNING.** The current step is the first one with no terminal
event. If the model calls something else — a declaration that is not the current step — this module
does nothing at all and the legacy path handles it unchanged. A plan that quietly re-pointed itself
at whatever the model happened to call would be a plan that cannot be wrong, which is the same as
one that cannot be checked.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from app.agentruntime.observation import UNCLASSIFIABLE
from app.agentruntime.plan import (
    EmitPathError,
    Event,
    Spec,
    State,
    extract_emit,
    resolve_arguments,
)

logger = logging.getLogger(__name__)

#: Terminal for the purposes of "which step is current".
_TERMINAL_EVENTS = frozenset({"step_emitted", "step_failed", "step_skipped"})


def current_step(spec: Spec, state: State) -> int | None:
    """The first step with no terminal event, or None when the plan has run out of steps.

    Deliberately derived from STATE rather than stored as a cursor. A cursor is a second source of
    truth about position, and this repository has recorded what happens when two things that must
    agree are written in two places.
    """
    done: set[int] = {e.step_index for e in state.events if e.kind in _TERMINAL_EVENTS}
    for i in range(len(spec.steps)):
        if i not in done:
            return i
    return None


def bound_arguments(spec: Spec, state: State, declaration: str) -> dict | None:
    """The arguments the PLAN supplies for this call, or None when the plan does not own it.

    None means *the plan has nothing to say about this call* — a different declaration, or no step
    left. It never means *the plan wanted to supply something and could not*: that raises, because a
    binding the plan owns and cannot fill is a recovery decision, not a reason to let the model
    improvise the value it already got wrong once.
    """
    i = current_step(spec, state)
    if i is None:
        return None
    step = spec.steps[i]
    if step.declaration != declaration:
        return None
    if not step.accepts:
        return {}
    return resolve_arguments(spec, state, i)


def emitted_values(spec: Spec, step_index: int, result) -> dict:
    """Read this step's declared `emits` out of a real tool result, by the declared paths.

    Raises `EmitPathError` naming the path and the segment that failed. **A miss is a step failure,
    never a `None` bound forward** — see `extract_emit`.
    """
    step = spec.steps[step_index]
    return {name: extract_emit(result, path) for name, path in sorted(step.emits.items())}


def observe_call(spec: Spec, state: State, declaration: str, *, ok: bool, result,
                 error_class: str = UNCLASSIFIABLE) -> Event | None:
    """The event this call produced, or None when the plan does not own the call.

    Returns the `Event` rather than appending it, because STATE has exactly one writer and it is not
    this function (§0.11). The caller persists it.
    """
    i = current_step(spec, state)
    if i is None or spec.steps[i].declaration != declaration:
        return None
    if not ok:
        return Event(kind="step_failed", step_index=i, error_class=error_class)
    step = spec.steps[i]
    if not step.emits:
        # A step that declares no `emits` still has to record that it RAN, or `current_step` would
        # return it forever and the plan would stall on a call that succeeded.
        return Event(kind="step_skipped", step_index=i)
    try:
        values = emitted_values(spec, i, result)
    except EmitPathError as exc:
        # 🔴 The declared path did not match the real result. That is a FAILED step, not a silent
        # skip: the plan named a location and the location was not there, so the next step's binding
        # cannot be satisfied and somebody has to know why.
        # `terminal_permanent` and not a retry class: the plan named a location the result does not
        # have, so the identical call produces the identical miss. C-7's fail-closed direction, and
        # the reason it matters here is the measured 74% byte-identical repeat calls.
        logger.warning("CP-3 executor: step %d (%s) emitted nothing — %s", i, declaration, exc)
        return Event(kind="step_failed", step_index=i, error_class=UNCLASSIFIABLE)
    return Event(kind="step_emitted", step_index=i, values=MappingProxyType(values))
