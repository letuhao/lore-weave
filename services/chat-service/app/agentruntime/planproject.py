"""CP-3.3 · the projection — what the model sees of the plan, **generated with a gate**.

§0.11. The context window is a lossy carrier: a pin-blind `LIMIT 50`, tool results evicted beyond the
newest 3, arguments dropped entirely by the transcript renderer. RT3 measured it. So the complete
plan lives where the context cannot truncate it, and what goes INTO the context is this projection —
which therefore has to be honest about being a summary.

FOUR OBLIGATIONS, AND EACH ONE IS A MEASURED FAILURE SOMEWHERE ELSE
-------------------------------------------------------------------
1. **Generated, never hand-maintained.** Kiro does not trust the spec and the work to stay aligned —
   it runs a hook that flags divergence. A hand-written projection is a second copy of the plan that
   drifts, and this repository has thirteen recorded instances of a pair fixed at one end.
2. **It declares its own lossiness.** A summary that does not say it is one gets read as complete.
3. **Stable between plan events.** If the projection changes when nothing happened, it churns the
   prompt prefix and every cached block below it — and a model re-reading a *different* plan for the
   same state has no way to tell a real change from noise.
4. **It NEVER compresses an identifier.** This is the whole point. §0.11's never-compressed set is
   *step list + position* from SPEC and *every emitted value + the effects ledger* from STATE — and
   **the identifiers all come from STATE**, which is the concrete reason STATE is re-presented
   losslessly while SPEC prose may be summarised.

🔴 **OBLIGATION 4 IS NOT "TRY NOT TO TRUNCATE".** `project()` takes no budget, no max-length and no
`limit`, because a projection that can be asked to fit a size is one that will silently drop the
`entity_id` the next step binds to — which is the 61.8% failure with an extra step in front of it.
The SPEC prose is the only thing summarisable, and `summarise_goal` is the only place that happens.
"""
from __future__ import annotations

from .plan import Spec, State

#: How much of the goal survives when the goal is long. Prose only — never applied to a value.
GOAL_CHARS = 240


def summarise_goal(goal: str) -> tuple[str, bool]:
    """The ONLY lossy operation in this module. Returns `(text, was_truncated)`.

    The flag is returned rather than inferred by the caller comparing lengths, because obligation 2
    is that the projection *declares* its lossiness — and a caller that has to re-derive the fact is
    a caller that can forget to.
    """
    if len(goal) <= GOAL_CHARS:
        return goal, False
    return goal[:GOAL_CHARS].rstrip() + "…", True


def project(spec: Spec, state: State) -> str:
    """The plan as the model sees it. **Deterministic in `(spec, state)` and nothing else.**

    No clock, no ordering over a set, no truncation of anything from STATE. Obligation 3 is a
    property of this function's inputs: called twice with the same arguments it returns the same
    string, so an unchanged plan cannot churn the prefix.
    """
    goal, lossy = summarise_goal(spec.goal)
    emitted = state.emitted()
    lines: list[str] = []

    lines.append(f"PLAN v{spec.version} · {len(spec.steps)} steps")
    lines.append(f"goal: {goal}")
    if spec.done_when:
        lines.append(f"done when: {spec.done_when}")

    for i, step in enumerate(spec.steps):
        status = state.status_of(i)
        mark = {"done": "x", "running": ">", "failed": "!", "skipped": "-"}.get(status, " ")
        gate = " [needs approval]" if step.gated else ""
        lines.append(f"[{mark}] {i}. {step.declaration}{gate}")
        # 🔴 EVERY emitted value, in full. This is the never-compressed set: these are the
        # identifiers a later step binds to, and the reason the conversation could not be trusted
        # to carry them is that it truncated exactly here.
        for name, value in sorted(emitted.get(i, {}).items()):
            lines.append(f"      {name} = {value!r}")

    live = state.committed_effects()
    if live:
        # The effects ledger, also never compressed — §0.5 feeds it to a replan, and silent exit #1
        # is exactly this list being absent when a failure lands on top of it.
        lines.append(f"committed effects ({len(live)}):")
        for e in live:
            lines.append(f"      step {e.step_index}: undo with {e.undo_hint}")

    # Obligation 2, and it names WHAT was dropped rather than saying "summarised". A reader who
    # cannot tell which part is lossy has to distrust all of it.
    lines.append(
        "note: the goal above is abridged; every step, position, emitted value and committed "
        "effect is complete." if lossy else
        "note: this is the complete plan — no field above is abridged.")
    return "\n".join(lines)
