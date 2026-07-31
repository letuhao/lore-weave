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
