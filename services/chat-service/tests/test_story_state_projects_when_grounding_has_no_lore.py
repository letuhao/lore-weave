"""D-STORY-STATE-STOOD-DOWN-ON-INSTRUCTIONS — "non-empty" is not "carries the lore".

MEASURED LIVE 2026-08-14 on every turn of three batches, read from the context-history
breakdown the FE itself renders:

    story_state       = 0 tokens
    memory_knowledge  = {"total": 50, "sections": {"instructions": 32}}

So the live grounding was NON-EMPTY, the safety net's emptiness test said "live lore is present,
stand down" — and the turn ended up with NEITHER live lore NOR the cached bible. The only thing
in context was 32 tokens of project instructions.

That is the whole failure. `story_state` exists so "the follow-up 'make it darker' never loses
the entities the rewrite needs", and a grounding response carrying nothing but instructions
satisfies the emptiness test while providing exactly none of them.

Measured consequence, same batch: asked "What do we know about Mira Solene so far?" on a book
that held her as a seeded glossary entity, the reply was "I don't have any information about
Mira Solene". The turn had no lore in context and no bible projected.

THE INVARIANT: a safety net must key on whether the thing it protects is PRESENT, not on whether
the payload is non-empty.

The W1 `sections` split is the honest signal and has been on the wire the whole time.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.db.session_blocks import _LORE_SECTIONS, _carries_lore  # noqa: E402


def test_instructions_only_is_not_lore():
    """THE FALSIFIER. This is the exact payload measured on every live turn."""
    assert _carries_lore({"instructions": 32}, "project instructions text") is False, (
        "a build returning only `instructions` carries no lore, so the cached bible must be "
        "projected — this is the shape that left three batches of turns with neither"
    )


def test_real_lore_stands_the_block_down():
    """The multi_project concern the original docstring names: when live lore IS present it is
    already in the prompt, so projecting would DUPLICATE it."""
    assert _carries_lore({"instructions": 32, "glossary_entities": 400}, "x") is True
    assert _carries_lore({"facts": 120}, "") is True


def test_an_older_build_without_sections_behaves_exactly_as_before():
    """`sections` is an additive contract (defaults {}). When it is absent the old string test
    must still govern, or an older knowledge-service would suddenly project on every turn."""
    assert _carries_lore(None, "live grounding text") is True
    assert _carries_lore(None, "") is False
    assert _carries_lore({}, "") is False


def test_zeroed_lore_sections_count_as_no_lore():
    """A section present but zero is not lore — the sum is what matters, not the key."""
    assert _carries_lore({"glossary_entities": 0, "instructions": 32}, "x") is False


def test_the_lore_set_names_story_content_only():
    """`instructions` is guidance ABOUT the project, not lore FROM it, and must never be counted
    — that miscount is the entire defect."""
    assert "instructions" not in _LORE_SECTIONS
    assert {"glossary_entities", "facts", "passages"} <= _LORE_SECTIONS


def test_the_projection_uses_the_predicate_not_the_string():
    """Call-site guard: the pure predicate above would stay green even if project_story_state
    never used it."""
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "db" / "session_blocks.py").read_text(encoding="utf-8")
    assert "if not _carries_lore(sections, full_context)" in src
    assert 'if not (full_context or "").strip() and cached' not in src, (
        "the old emptiness test must be gone, not merely bypassed"
    )
