"""C27 (dị bản M4) — the delta flywheel: approved-derivative-chapter extraction.

When a writer APPROVES a chapter of a DERIVATIVE (dị bản) Work, this module
dispatches the EXISTING knowledge extraction trigger
(`/internal/extraction/extract-item`) scoped to the derivative's OWN
`project_id` — its delta partition (G2). That closes the flywheel: what the dị
bản itself establishes lands in the delta graph, and the NEXT scene's pack (C25)
merges those new delta facts into grounding.

LOCKED invariants this module enforces (OPEN_QUESTIONS_LOCKED §G2 + arch-review):

  • DELTA-ONLY WRITE (G2): extraction targets the derivative's OWN project_id —
    NEVER the source/base partition, NEVER null. The source graph stays untouched
    (COW). A canon/greenfield (non-derivative) Work does NOT flywheel here.
  • PROJECT-SCOPE GUARD: `assert_delta_extraction_scoped` asserts a non-null
    derivative project_id BEFORE dispatch (the cross-project grounding leak C23's
    NOT-NULL guard exists for — a null project_id widens a knowledge read to ALL of
    a user's projects). Refuse rather than dispatch into "all projects".
  • FORWARD-FROM-BRANCH WRITE-ORDER: a derivative is written forward from its
    `branch_point`; only chapters at/after the branch belong to the delta. An
    out-of-order (pre-branch) approval yields a THINNER delta (we SKIP its
    extraction) — graceful degradation, NOT a correctness break / error.
  • REUSE the existing extraction trigger — no new extraction engine. We just point
    the existing `extract-item` at the delta project_id.

AI-FREE (LOCKED): composition has NO AI imports. The extraction LLM call happens
inside knowledge-service (via the internal endpoint); composition only dispatches
the trigger with a caller-supplied (provider-registry-resolved) model ref — no
provider SDK, no hardcoded model name here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

logger = logging.getLogger(__name__)


class DeltaScopeError(Exception):
    """The delta-extraction project-scope GUARD failed: the target project_id is
    null (or not the derivative's own delta partition). Raised BEFORE any dispatch
    so a derivative chapter can NEVER extract into null/all-projects/the source.
    The router maps this to a 409/422 — never a silent dispatch."""


def assert_delta_extraction_scoped(
    delta_project_id: UUID | None, source_project_id: UUID | None
) -> None:
    """C27 PROJECT-SCOPE GUARD (LOCKED) — refuse to dispatch delta extraction
    unless BOTH the delta (the derivative's own project) and the base (the source
    project, proving this really IS a derivative) are present + non-null.

    A null `delta_project_id` would let the extraction trigger write into a null /
    all-projects scope (cross-project leak). A null `source_project_id` means the
    Work is NOT a derivative — the flywheel is delta-only and must not fire for a
    canon/greenfield Work (which uses the normal event-driven canon extraction).

    Raises DeltaScopeError when either is None (refuse to proceed)."""
    if delta_project_id is None:
        raise DeltaScopeError(
            "C27 delta scoping: the derivative's delta project_id is null — refusing "
            "to dispatch extraction (a null project would widen the write to ALL of "
            "the user's projects, the cross-project grounding leak)."
        )
    if source_project_id is None:
        raise DeltaScopeError(
            "C27 delta scoping: no base/source project — this Work is not a "
            "derivative; the delta flywheel is delta-only and must not fire for a "
            "canon/greenfield Work."
        )


def is_forward_of_branch(chapter_sort_order: int | None, branch_point: int | None) -> bool:
    """FORWARD-FROM-BRANCH (LOCKED) — is this chapter part of the derivative's
    delta (written forward from the branch_point)?

    A derivative diverges at `branch_point` (chapter-level, G3) and is authored
    FORWARD from there; the delta is the at-or-after-branch chapters. A chapter
    BEFORE the branch is inherited base (COW reference spine) — approving it does
    NOT belong in the delta, so we SKIP its extraction (a THINNER delta, graceful —
    NOT an error).

    Degrade-safe unknowns:
      • `branch_point is None` → diverges from the start → EVERY chapter is delta
        (forward of an unbounded branch). Returns True.
      • `chapter_sort_order is None` (unplaceable chapter) → we can't prove it is
        pre-branch, so we DON'T skip it (conservative include — a thinner delta is
        the failure mode we avoid, but an unplaceable chapter shouldn't silently
        drop). Returns True.
    """
    if branch_point is None:
        return True
    if chapter_sort_order is None:
        return True
    return chapter_sort_order >= branch_point


@dataclass
class FlywheelDecision:
    """The resolved plan for an approved-derivative-chapter flywheel dispatch.

    `dispatch` is the go/no-go; `reason` documents a skip (non-derivative, or an
    out-of-order pre-branch chapter → thinner delta). `delta_project_id` is the
    derivative's OWN project (the extraction target) — only meaningful when
    `dispatch` is True."""
    dispatch: bool
    delta_project_id: UUID | None
    source_project_id: UUID | None
    branch_point: int | None
    reason: str


@dataclass(frozen=True)
class CanonDecision:
    """Whether an approved chapter of a NON-derivative Work should extract into its own graph."""

    dispatch: bool
    project_id: UUID | None
    reason: str


def plan_canon_dispatch(
    *, project_id: UUID | None, source_project_id: UUID | None,
) -> CanonDecision:
    """The GREENFIELD half — a canon Work's approved chapter extracts into its OWN project.

    Deliberately NOT a loosening of `plan_flywheel_dispatch`. That function's invariants are
    LOCKED and they exist to stop a DERIVATIVE writing into the SOURCE graph; a canon book
    writing into its own project is not that leak, it is the intended behaviour, and blurring
    one decision to cover both would put a delta rule in charge of a canon question.

    WHY THIS EXISTS AT ALL. `plan_flywheel_dispatch`'s own docstring says a greenfield Work
    "uses the event-driven path". MEASURED 2026-08-01: there is no such path. `extract-item` has
    exactly one caller in the repo — the derivative branch of `approve_chapter` — so a book
    written from scratch is NEVER extracted, its knowledge graph stays empty, and the canon
    guard checks every scene against nothing. On the dogfood book: 15 chapters, 4 published,
    a knowledge project that exists and shares the composition project's id, and **0**
    `:EntityStatus` nodes. The guard, the judge and the publish gate were all built over a
    store that nothing fills.

    A null `project_id` is refused for the same reason the delta guard refuses one: a null
    scope widens a knowledge write to ALL of a user's projects (the C23 leak).
    """
    if source_project_id is not None:
        return CanonDecision(dispatch=False, project_id=project_id, reason="is_a_derivative")
    if project_id is None:
        return CanonDecision(dispatch=False, project_id=None, reason="unscoped_project")
    return CanonDecision(dispatch=True, project_id=project_id, reason="canon_dispatch")


def plan_flywheel_dispatch(
    *,
    delta_project_id: UUID | None,
    source_project_id: UUID | None,
    branch_point: int | None,
    chapter_sort_order: int | None,
) -> FlywheelDecision:
    """Decide whether an approved derivative chapter should flywheel into the delta.

    Order of checks (matters):
      1. NON-DERIVATIVE (no source project) → no dispatch (canon/greenfield uses the
         event-driven path). This is NOT an error — a normal Work approval is a clean
         no-op for the flywheel.
      2. FORWARD-FROM-BRANCH — a pre-branch chapter is inherited base, not delta →
         skip (thinner delta, graceful). Checked BEFORE the scope guard so an
         out-of-order approval degrades rather than tripping the guard.
      3. PROJECT-SCOPE GUARD — `assert_delta_extraction_scoped` (raises
         DeltaScopeError on a null delta project). Only reached for a real,
         forward-of-branch derivative chapter.

    Returns a FlywheelDecision; raises DeltaScopeError only at step 3 (a derivative
    that should dispatch but has a null delta project — a real defect, never a
    silent wrong-partition write)."""
    # A DECLINED decision carries NO target. It used to echo `delta_project_id` back on every
    # branch, which reads harmless and is not: a caller that reaches for the target of a decision
    # that chose not to dispatch gets a real, writable project id instead of None, so a
    # wrong-partition write is indistinguishable from a right one — including to a test. That is
    # the C23 leak shape this module exists to prevent, sitting inside the module itself.
    # (Found 2026-08-01 when injecting `target_project = decision.delta_project_id` into the
    # canon path left the router's whole test file GREEN.)
    if source_project_id is None:
        return FlywheelDecision(
            dispatch=False, delta_project_id=None,
            source_project_id=None, branch_point=branch_point,
            reason="not_a_derivative",
        )
    if not is_forward_of_branch(chapter_sort_order, branch_point):
        return FlywheelDecision(
            dispatch=False, delta_project_id=None,
            source_project_id=source_project_id, branch_point=branch_point,
            reason="pre_branch_thinner_delta",
        )
    # Real derivative, forward-of-branch chapter → the scope guard MUST hold before
    # we dispatch the extraction trigger.
    assert_delta_extraction_scoped(delta_project_id, source_project_id)
    return FlywheelDecision(
        dispatch=True, delta_project_id=delta_project_id,
        source_project_id=source_project_id, branch_point=branch_point,
        reason="delta_dispatch",
    )
