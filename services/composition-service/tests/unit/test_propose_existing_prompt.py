"""P3 — the EXISTING STATE prompt block + CONTINUITY rule (LLM/async propose grounding)."""

from __future__ import annotations

from app.engine.plan_forge.existing_state import (
    ArcSummary,
    CastMember,
    ChapterBrief,
    ExistingState,
    render_existing_state_prompt,
)
from app.engine.plan_forge import prompts


def _state(**kw) -> ExistingState:
    base = dict(chapter_count=0, recent_chapters=[], cast=[], arcs=[], variables=[], motifs=[],
                notes={}, grounded_fingerprint="fp")
    base.update(kw)
    return ExistingState(**base)


def test_empty_state_renders_no_block_and_prompts_are_byte_identical():
    assert render_existing_state_prompt(_state()) == ""
    # analyze/materialize with an empty block == the blind prompt
    assert prompts.analyze_user_prompt("MD", "") == prompts.analyze_user_prompt("MD")
    assert prompts.materialize_user_prompt("AJ", "cs", "") == prompts.materialize_user_prompt("AJ", "cs")


def test_populated_state_renders_cast_arcs_and_chapter_count():
    st = _state(
        chapter_count=42,
        recent_chapters=[ChapterBrief(story_order=42000, title="Ch42", synopsis="the reckoning begins")],
        cast=[CastMember(name="Ling Wei", glossary_entity_id="e1"),
              CastMember(name="Bo", glossary_entity_id="e2")],
        arcs=[ArcSummary(title="The Iron Court", one_line="intrigue")],
        variables=["PA"], motifs=["打脸"],
        notes={"spine": "42 chapter(s), showing last 1"},
    )
    block = render_existing_state_prompt(st)
    assert "EXISTING STATE" in block
    assert "42" in block                       # chapter count
    assert "Ling Wei" in block and "Bo" in block  # cast referenced by name
    assert "The Iron Court" in block           # arc referenced by title
    assert "PA" in block and "打脸" in block     # systems in play


def test_the_block_is_wrapped_in_the_prompt_when_present():
    block = "EXISTING STATE — foo"
    a = prompts.analyze_user_prompt("MD", block)
    m = prompts.materialize_user_prompt("AJ", "cs", block)
    assert "<existing_state>" in a and "EXISTING STATE — foo" in a
    assert "<existing_state>" in m and "EXISTING STATE — foo" in m


def test_CONTINUITY_rule_present_in_both_system_prompts():
    # the rule that tells the model to reference (not re-invent) the EXISTING STATE section
    assert "CONTINUITY" in prompts.ANALYZE_SYSTEM
    assert "CONTINUITY" in prompts.MATERIALIZE_SYSTEM
    # and it is conditional — "when no EXISTING STATE section is present, ignore this rule"
    assert "when no" in prompts.ANALYZE_SYSTEM.lower()
    # ARC COVERAGE (the pre-existing highest-priority rule) is untouched
    assert "ARC COVERAGE" in prompts.ANALYZE_SYSTEM and "ARC COVERAGE" in prompts.MATERIALIZE_SYSTEM
