"""The Context Budget Law **Planner** (POLICY) — the swappable seam where optimization
hypotheses live (task_weight computation, compaction aggressiveness). Given the turn's
signals + budget + config, it emits a `CompilePlan` the Compiler then materializes.

T3.2 owns the compaction policy (grounding_needed → task_weight → soft compaction target).
Grounding DETECTION (entity-presence over the book's known entities) stays I/O-adjacent in
the consumer; the Planner takes the resolved `grounding_needed` as input. Later slices fold
in retrieval-mode (D1) and block-inclusion policy. Pure — no I/O, no provider SDK.

To A/B a policy, swap `Planner.plan` (or subclass) and run the quality-gate harness; keep the
winner by flipping the consumer's config (as T2 did).
"""
from __future__ import annotations

from dataclasses import dataclass

from loreweave_context.budget import compute_target


@dataclass(frozen=True)
class CompilePlan:
    """The policy decisions for one turn (the Compiler's input)."""

    grounding: bool                 # pull the expensive build_context grounding this turn?
    task_weight: float              # D3: [0,1] lean→roomy content allowance
    compact_target: int | None      # the task-elastic soft compaction trigger (None = flat)


class Planner:
    """Default Context Budget policy. Subclass / swap `plan` to test an optimization
    hypothesis; the return type (CompilePlan) is the stable contract."""

    def plan(
        self,
        *,
        grounding_needed: bool,
        context_length: int | None,
        task_elastic_enabled: bool,
        light_task_weight: float,
    ) -> CompilePlan:
        """Compaction policy: a grounding turn stays roomy (task_weight 1.0 → surface_max);
        a non-grounding (status-op / smalltalk) turn uses `light_task_weight` (leaner, so it
        compacts sooner). When task-elastic is off, `compact_target` is None (the consumer
        keeps its flat 0.75×window trigger) and task_weight is the neutral 1.0."""
        if task_elastic_enabled:
            task_weight = 1.0 if grounding_needed else light_task_weight
            compact_target = compute_target(context_length, task_weight=task_weight)
        else:
            task_weight = 1.0
            compact_target = None
        return CompilePlan(
            grounding=grounding_needed,
            task_weight=task_weight,
            compact_target=compact_target,
        )
