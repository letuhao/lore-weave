"""The call-budget seam — adopting it must never be a downgrade.

The seam exists so a future adaptive policy lands in ONE place instead of ~40 literals.
That only holds if two things are true, and both are testable today:

1. **Adopting it at a call site cannot shrink that site's budget.** Otherwise the
   migration itself introduces truncation, and every regression afterwards is ambiguous.
2. **It carries signal.** A budget function whose output does not move with the facts the
   caller knows (length, language, reasoning, window) is a renamed constant, and the
   future adaptive version would have nothing to adapt on.

The equivalence check against `scene_output_budget` — the measured implementation this
generalises — lives in composition-service's suite instead, because an SDK test must not
import a service package (and could not: `app` only resolves with that service as CWD,
so it passed there and failed from the repo root).
"""
from __future__ import annotations

import pytest

from loreweave_llm.budget import (
    DEFAULT_CEILING,
    CallBudget,
    OutputKind,
    call_budget,
)
from loreweave_llm.reasoning import ReasoningDirective


def _directive(effort: str | None) -> ReasoningDirective:
    return ReasoningDirective(effort=effort, passthrough=False, source="test")


# ── 1 · adopting the seam is never a downgrade ──────────────────────────────

#: The flat literals in the repo today, by the kind of call that uses them. A budget below
#: any of these would truncate a call that currently fits.
_TODAYS_LITERALS = [
    (OutputKind.VERDICT, 512, "motif_conformance — a bounded reason string"),
    (OutputKind.VERDICT, 1024, "canon_check / eval_judge"),
    (OutputKind.VERDICT, 1536, "critic — 4 dims + per-violation"),
    (OutputKind.STRUCTURED, 2048, "plan L1"),
    (OutputKind.STRUCTURED, 2560, "plan L2"),
    (OutputKind.STRUCTURED, 4000, "cast_plan — the site whose comment records a truncation"),
    (OutputKind.EDIT, 1200, "error_block_heal"),
    (OutputKind.EDIT, 2200, "self_heal"),
]


@pytest.mark.parametrize("kind,literal,where", _TODAYS_LITERALS)
def test_the_default_policy_is_at_least_as_generous_as_todays_literal(kind, literal, where):
    """With NO size signal at all — the worst case for the seam — the floor must still
    clear the literal it replaces."""
    got = call_budget(kind).max_output_tokens
    assert got >= literal, (
        f"{kind.value} floor {got} < the {literal} used at {where}: adopting the seam "
        "there would truncate a call that fits today"
    )


# ── 2 · it carries signal (or it is just a constant) ────────────────────────

class TestTheBudgetMovesWithWhatTheCallerKnows:
    """Each of these is a fact a call site holds today and currently discards into a
    literal. If any of them fails to move the number, that parameter is decoration and a
    future adaptive policy gains nothing from it."""

    def test_length(self):
        assert (call_budget(OutputKind.PROSE, target=2000).max_output_tokens
                > call_budget(OutputKind.PROSE, target=500).max_output_tokens)

    def test_language_density(self):
        """The whole reason a word target is not a token target: Vietnamese and CJK
        tokenize far denser, so the same ask costs more output room."""
        vi = call_budget(OutputKind.PROSE, target=1500, language="vi").max_output_tokens
        en = call_budget(OutputKind.PROSE, target=1500, language="en").max_output_tokens
        assert vi > en, "a word target must cost more tokens in Vietnamese than in English"

    def test_reasoning_effort(self):
        """Thinking tokens are spent BEFORE the output and drawn from the same allowance.
        Not accounting for them is how a reasoning model returns text="" and bills it as a
        success — a failure this repo has already shipped once."""
        none = call_budget(OutputKind.PROSE, target=1500,
                           reasoning=_directive("none")).max_output_tokens
        high = call_budget(OutputKind.PROSE, target=1500,
                           reasoning=_directive("high")).max_output_tokens
        assert high > none

    def test_item_count_for_structured_output(self):
        assert (call_budget(OutputKind.STRUCTURED, target=60).max_output_tokens
                > call_budget(OutputKind.STRUCTURED, target=5).max_output_tokens)


# ── 3 · the properties a flat literal cannot express ────────────────────────

def test_structured_truncation_is_marked_fatal_and_prose_is_not():
    """A grammar cannot stop early in a valid place, so a clipped JSON object is
    UNRECOVERABLE — a different failure from a short scene. No `max_tokens` literal
    anywhere in the repo records this distinction, which is why callers treat a truncated
    plan as a short answer."""
    assert call_budget(OutputKind.STRUCTURED, target=10).truncation_is_fatal is True
    assert call_budget(OutputKind.PROSE, target=900).truncation_is_fatal is False
    assert call_budget(OutputKind.VERDICT).truncation_is_fatal is False


def test_the_window_clamp_applies_and_is_visible():
    """Two SDK sites clamp output against the model's context window and two do not,
    which is why one worker's distiller is unclamped while its extractor is not."""
    b = call_budget(OutputKind.PROSE, target=100_000, language="zh", context_length=8192)
    assert b.max_output_tokens <= 4096
    assert b.clamped_to_window == 4096


def test_an_unsupplied_window_is_visible_rather_than_silently_unclamped():
    """`None` means "the caller did not say", not "no clamp needed" — the difference is
    what makes an audit of unclamped call sites possible later."""
    assert call_budget(OutputKind.PROSE, target=900).clamped_to_window is None


def test_the_ceiling_is_a_runaway_guard_not_a_budget():
    b = call_budget(OutputKind.PROSE, target=10_000_000, language="zh")
    assert b.max_output_tokens == DEFAULT_CEILING


def test_the_source_is_never_blank():
    """A budget whose origin is unknown is exactly what this seam removes. When a scored
    policy lands this reads "scored:<name>" and the call sites do not change.

    NOT "adaptive:<name>" — `ReasoningControl="adaptive"` already means *the model
    self-orchestrates* (Anthropic, Gemini 2.5+), which is a different decision entirely.
    One name for one concept."""
    for kind in OutputKind:
        b: CallBudget = call_budget(kind, target=10)
        assert b.source, f"{kind} produced a budget with no recorded source"


# ── MIRROR — "deliberately unbounded" must be sayable ─────────────────────────────────────

def test_mirror_resolves_to_the_wire_omit_sentinel():
    """0 is not "no budget", it is this platform's EXISTING convention for "omit the cap"
    (`provider/adapters.go`: *"Policy: max_tokens=0 means omit (let the model decide)"*).
    Reusing it rather than inventing a second spelling is the one-name-one-concept rule."""
    b = call_budget(OutputKind.MIRROR)
    assert b.max_output_tokens == 0
    assert b.source == "default"


def test_mirror_truncation_is_not_fatal():
    """A model reaching its natural stop is the intended END of a translation, not a clip."""
    assert call_budget(OutputKind.MIRROR).truncation_is_fatal is False


@pytest.mark.parametrize("kwargs", [
    {"target": 5000},
    {"language": "vi"},
    {"context_length": 8192},
    {"target": 100_000, "language": "zh", "context_length": 4096},
])
def test_no_clamp_can_turn_a_deliberate_no_cap_into_a_cap(kwargs):
    """Every other kind runs floor → headroom → window share → ceiling. Any one of those
    applied to MIRROR would silently re-introduce the truncation the omission avoids — the
    window clamp especially, since a translation's input is LARGE by construction."""
    b = call_budget(OutputKind.MIRROR, **kwargs)
    assert b.max_output_tokens == 0, f"{kwargs} clamped a deliberate no-cap to {b.max_output_tokens}"
    assert b.clamped_to_window is None


def test_mirror_is_the_only_kind_that_may_resolve_to_zero():
    """A zero from any other kind would be a bug that reads as a policy — the whole reason
    "absent" and "deliberate" had to stop looking alike."""
    for kind in OutputKind:
        got = call_budget(kind, target=0).max_output_tokens
        if kind is OutputKind.MIRROR:
            assert got == 0
        else:
            assert got > 0, f"{kind} resolved to {got} on an unknown target"


# ── `floor`: the service's measured minimum ───────────────────────────────────────────────

def test_a_service_floor_raises_the_budget_above_the_kinds_net():
    """The kind floors were sized from a SAMPLE, and the full inventory falsified the module's
    own promise that adoption "can never truncate something that previously fit":
    `plan_forge` uses 8000 against a STRUCTURED net of 4096 (halved), and both self-heal
    proposers use 3000 against an EDIT net of 2200. Three silent downgrades."""
    assert call_budget(OutputKind.STRUCTURED, floor=8000).max_output_tokens >= 8000
    assert call_budget(OutputKind.EDIT, floor=3000).max_output_tokens >= 3000


def test_a_service_floor_can_never_LOWER_the_kinds_net():
    """`max` of both, never a replacement — otherwise a registry row could quietly drop a
    call under the safety floor its kind guarantees."""
    for kind in (OutputKind.PROSE, OutputKind.STRUCTURED, OutputKind.VERDICT, OutputKind.EDIT):
        bare = call_budget(kind).max_output_tokens
        assert call_budget(kind, floor=1).max_output_tokens == bare, f"{kind} was lowered"


def test_floor_does_not_defeat_the_runaway_ceiling():
    assert call_budget(OutputKind.PROSE, floor=10**9).max_output_tokens == DEFAULT_CEILING


def test_floor_is_ignored_for_mirror_because_zero_means_unbounded():
    """The numeric `0 < floor` comparison is the trap: MIRROR's 0 is the omit sentinel, which
    already exceeds any minimum. Pinned so a future edit does not "fix" it into a cap."""
    assert call_budget(OutputKind.MIRROR, floor=8000).max_output_tokens == 0
